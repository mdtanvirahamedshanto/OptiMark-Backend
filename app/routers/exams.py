"""Exam and OMR scan endpoints."""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import User, Exam, AnswerKey, Result
from app.schemas import ExamCreate, ExamResponse, ScanResultResponse
from app.dependencies import get_current_user
from app.utils.omr_engine import process_omr_image, grade_omr_result, OMRResult
from app.config import get_settings

router = APIRouter(prefix="/exams", tags=["exams"])
settings = get_settings()


@router.post("/create", response_model=ExamResponse)
async def create_exam(
    exam_data: ExamCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create an exam and upload its answer key."""
    exam = Exam(
        teacher_id=current_user.id,
        name=exam_data.name,
        subject_code=exam_data.subject_code,
        total_questions=exam_data.total_questions,
    )
    db.add(exam)
    await db.flush()

    for item in exam_data.answer_key:
        answer_key = AnswerKey(
            exam_id=exam.id,
            set_code=item.set_code.upper(),
            question_no=item.question_no,
            correct_option=item.correct_option,
        )
        db.add(answer_key)

    await db.refresh(exam)
    return exam


@router.post("/{exam_id}/scan", response_model=ScanResultResponse)
async def scan_omr(
    exam_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload OMR image, process via engine, compare with answer key,
    save to Result table, and return JSON response.
    """
    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image (JPEG, PNG, etc.)",
        )

    # Fetch exam
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = result.scalar_one_or_none()
    if not exam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exam not found",
        )
    if exam.teacher_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to scan this exam",
        )

    # Fetch answer key
    ak_result = await db.execute(
        select(AnswerKey).where(AnswerKey.exam_id == exam_id)
    )
    answer_keys = ak_result.scalars().all()
    answer_key_dict = {
        (ak.set_code, ak.question_no): ak.correct_option for ak in answer_keys
    }

    if not answer_key_dict:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Exam has no answer key configured",
        )

    # Create upload directory and save file
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "image").suffix or ".jpg"
    filename = f"{uuid.uuid4()}{ext}"
    filepath = upload_dir / filename

    try:
        contents = await file.read()
        if len(contents) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File too large. Max size: {settings.MAX_UPLOAD_SIZE_MB}MB",
            )
        with open(filepath, "wb") as f:
            f.write(contents)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {str(e)}",
        )

    try:
        # Process OMR image
        omr_result = process_omr_image(
            filepath,
            num_questions=exam.total_questions,
        )

        if not omr_result.success:
            return ScanResultResponse(
                roll_number=omr_result.roll_number,
                set_code=omr_result.set_code or "?",
                marks_obtained=0,
                wrong_answers=0,
                percentage=0.0,
                class_code=omr_result.class_code,
                subject_code=omr_result.subject_code,
                answers=omr_result.answers,
                success=False,
                message=omr_result.error_message,
            )

        # Grade against answer key
        marks_obtained, wrong_answers, percentage = grade_omr_result(
            omr_result,
            answer_key_dict,
        )

        # Save to Result table
        image_url = f"/{settings.UPLOAD_DIR}/{filename}"
        result_record = Result(
            exam_id=exam_id,
            roll_number=omr_result.roll_number or "unknown",
            set_code=omr_result.set_code or "?",
            marks_obtained=marks_obtained,
            wrong_answers=wrong_answers,
            percentage=percentage,
            uploaded_image_url=image_url,
        )
        db.add(result_record)

        return ScanResultResponse(
            roll_number=omr_result.roll_number,
            set_code=omr_result.set_code,
            marks_obtained=marks_obtained,
            wrong_answers=wrong_answers,
            percentage=percentage,
            class_code=omr_result.class_code,
            subject_code=omr_result.subject_code,
            answers=omr_result.answers,
            success=True,
            message="OMR processed successfully",
        )
    finally:
        # Keep file on disk for audit; optionally delete after processing
        pass
