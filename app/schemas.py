"""Pydantic schemas for request/response validation."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# --- Auth Schemas ---
class UserCreate(BaseModel):
    """Schema for user registration."""

    email: EmailStr
    password: str = Field(..., min_length=6)


class UserResponse(BaseModel):
    """Schema for user in responses."""

    id: int
    email: str
    is_subscribed: bool
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    """JWT token response."""

    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    """Schema for login request."""

    email: EmailStr
    password: str


# --- Exam Schemas ---
class AnswerKeyItem(BaseModel):
    """Single answer key entry."""

    set_code: str = Field(..., min_length=1, max_length=10)
    question_no: int = Field(..., ge=1, le=60)
    correct_option: int = Field(..., ge=0, le=3)


class ExamCreate(BaseModel):
    """Schema for creating an exam with answer key."""

    name: str = Field(..., min_length=1, max_length=255)
    subject_code: str = Field(..., min_length=1, max_length=50)
    total_questions: int = Field(default=60, ge=1, le=100)
    answer_key: list[AnswerKeyItem] = Field(..., min_length=1)


class ExamResponse(BaseModel):
    """Schema for exam in responses."""

    id: int
    teacher_id: int
    name: str
    subject_code: str
    total_questions: int
    created_at: datetime

    class Config:
        from_attributes = True


# --- Result Schemas ---
class ScanResultResponse(BaseModel):
    """Response from OMR scan endpoint."""

    roll_number: str
    set_code: str
    marks_obtained: int
    wrong_answers: int
    percentage: float
    class_code: str
    subject_code: str
    answers: list[int]
    success: bool
    message: str = ""


class ResultResponse(BaseModel):
    """Schema for result in responses."""

    id: int
    exam_id: int
    roll_number: str
    set_code: str
    marks_obtained: int
    wrong_answers: int
    percentage: float
    uploaded_image_url: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
