"""Admin-only endpoints."""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models import User, Exam, Result, PendingPayment
from app.schemas import PendingPaymentApprove
from app.dependencies import get_current_user, get_current_admin

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats")
async def admin_stats(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Dashboard stats for admin."""
    users_result = await db.execute(select(func.count(User.id)))
    total_users = users_result.scalar() or 0

    exams_result = await db.execute(select(func.count(Exam.id)))
    total_exams = exams_result.scalar() or 0

    results_result = await db.execute(select(func.count(Result.id)))
    total_results = results_result.scalar() or 0

    pending_result = await db.execute(
        select(func.count(PendingPayment.id)).where(PendingPayment.status == "pending")
    )
    pending_payments = pending_result.scalar() or 0

    return {
        "total_users": total_users,
        "total_exams": total_exams,
        "total_results": total_results,
        "pending_payments": pending_payments,
    }


@router.get("/pending-payments")
async def list_pending_payments(
    status_filter: str | None = None,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all pending payments (or filter by status)."""
    q = select(PendingPayment, User.email).join(
        User, PendingPayment.user_id == User.id
    ).order_by(PendingPayment.created_at.desc())
    if status_filter:
        q = q.where(PendingPayment.status == status_filter)
    result = await db.execute(q)
    rows = result.all()
    return {
        "payments": [
            {
                "id": p.id,
                "user_id": p.user_id,
                "user_email": email,
                "plan_id": p.plan_id,
                "amount": p.amount,
                "payment_method": p.payment_method,
                "transaction_id": p.transaction_id,
                "sender_name": p.sender_name,
                "sender_phone": p.sender_phone,
                "sender_email": p.sender_email,
                "status": p.status,
                "admin_notes": p.admin_notes,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p, email in rows
        ],
    }


@router.post("/pending-payments/{payment_id}/approve")
async def approve_payment(
    payment_id: int,
    body: PendingPaymentApprove,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Approve a pending payment and activate user subscription."""
    result = await db.execute(
        select(PendingPayment).where(PendingPayment.id == payment_id)
    )
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status != "pending":
        raise HTTPException(status_code=400, detail=f"Payment already {payment.status}")

    user_result = await db.execute(select(User).where(User.id == payment.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_subscribed = True
    user.subscription_plan = payment.plan_id
    payment.status = "approved"
    payment.admin_notes = body.admin_notes
    payment.reviewed_by = current_user.id
    payment.reviewed_at = datetime.utcnow()
    return {"message": "Payment approved. User subscription activated."}


@router.post("/pending-payments/{payment_id}/reject")
async def reject_payment(
    payment_id: int,
    body: PendingPaymentApprove,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Reject a pending payment."""
    result = await db.execute(
        select(PendingPayment).where(PendingPayment.id == payment_id)
    )
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.status != "pending":
        raise HTTPException(status_code=400, detail=f"Payment already {payment.status}")

    payment.status = "rejected"
    payment.admin_notes = body.admin_notes
    payment.reviewed_by = current_user.id
    payment.reviewed_at = datetime.utcnow()
    return {"message": "Payment rejected."}


@router.get("/users")
async def list_users(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all users (teachers)."""
    result = await db.execute(
        select(User).order_by(User.created_at.desc())
    )
    users = result.scalars().all()
    return {
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "role": u.role,
                "is_subscribed": u.is_subscribed,
                "subscription_plan": u.subscription_plan,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ],
    }


@router.get("/exams")
async def list_all_exams(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all exams across all teachers."""
    result = await db.execute(
        select(Exam, User.email)
        .join(User, Exam.teacher_id == User.id)
        .order_by(Exam.date_created.desc())
    )
    rows = result.all()
    return {
        "exams": [
            {
                "id": e.id,
                "title": e.title,
                "subject_code": e.subject_code,
                "teacher_email": email,
                "total_questions": e.total_questions,
                "date_created": e.date_created.isoformat() if e.date_created else None,
            }
            for e, email in rows
        ],
    }
