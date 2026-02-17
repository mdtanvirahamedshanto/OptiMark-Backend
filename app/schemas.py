"""Pydantic schemas for request/response validation."""

from datetime import datetime
from typing import Optional, Dict, List, Union

from pydantic import BaseModel, EmailStr, Field, model_validator


# --- Auth Schemas ---
class UserCreate(BaseModel):
    """Schema for user registration."""

    email: EmailStr
    password: str = Field(..., min_length=6)


class UserResponse(BaseModel):
    """Schema for user in responses."""

    id: int
    email: str
    role: Optional[str] = "teacher"
    is_subscribed: bool
    subscription_plan: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class ManualPaymentSubmit(BaseModel):
    """Manual payment submission (bKash, Nagad, Bank Transfer)."""

    plan: str
    amount: str
    payment_method: str = Field(..., pattern="^(bkash|nagad|bank_transfer)$")
    transaction_id: str
    sender_name: str
    sender_phone: Optional[str] = None
    sender_email: Optional[str] = None


class PendingPaymentResponse(BaseModel):
    """Pending payment in admin list."""

    id: int
    user_id: int
    user_email: str
    plan_id: str
    amount: float
    payment_method: str
    transaction_id: str
    sender_name: str
    sender_phone: Optional[str]
    sender_email: Optional[str]
    status: str
    admin_notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class PendingPaymentApprove(BaseModel):
    """Admin approve/reject request."""

    admin_notes: Optional[str] = None


class Token(BaseModel):
    """JWT token response."""

    access_token: str
    token_type: str = "bearer"
    role: Optional[str] = None


class LoginRequest(BaseModel):
    """Schema for login request."""

    email: EmailStr
    password: str


# --- Exam Schemas ---
# Answer key as JSON: {"1": 0, "2": 2, "3": 1, ...} question_no -> correct_option (0-3)
AnswerKeyDict = Dict[str, int]


class AnswerKeySet(BaseModel):
    """Answer key for one set (e.g., ক, খ). answers: question_no (str) -> correct_option (0-3)."""

    set_code: str = Field(..., min_length=1, max_length=10)
    answers: Dict[str, int] = Field(
        ...,
        description='{"1": 0, "2": 2, "3": 1, ...}',
        examples=[{"1": 2, "2": 0, "3": 1}],
    )


class ExamCreate(BaseModel):
    """Schema for creating an exam with answer keys."""

    title: str = Field(..., min_length=1, max_length=255)
    subject_code: str = Field(..., min_length=1, max_length=50)
    total_questions: int = Field(default=60, ge=1, le=100)
    answer_keys: Optional[list[AnswerKeySet]] = None
    # Frontend format: single answer_key as {question_no: "A"|"B"|"C"|"D"}
    answer_key: Optional[Dict[Union[str, int], str]] = None

    @model_validator(mode="after")
    def ensure_answer_keys(self):
        if not self.answer_keys and not self.answer_key:
            raise ValueError("Either answer_keys or answer_key must be provided")
        return self

    def get_answer_keys_list(self) -> list[AnswerKeySet]:
        """Convert to list of AnswerKeySet."""
        if self.answer_keys:
            return self.answer_keys
        if self.answer_key:
            opt_map = {"A": 0, "B": 1, "C": 2, "D": 3}
            answers = {str(k): opt_map.get(str(v).upper(), 0) for k, v in self.answer_key.items()}
            return [AnswerKeySet(set_code="A", answers=answers)]
        return []


class ExamResponse(BaseModel):
    """Schema for exam in responses."""

    id: int
    teacher_id: int
    title: str
    subject_code: str
    total_questions: int
    date_created: datetime

    class Config:
        from_attributes = True


class ResultsWithAnalytics(BaseModel):
    """Results list with class-wide statistics."""

    results: List["ResultResponse"]
    total_count: int
    average_percentage: float
    highest_marks: int
    lowest_marks: int
    total_marks: int


# --- Result Schemas ---
class ScanResultResponse(BaseModel):
    """Response from OMR scan endpoint."""

    roll_number: str
    set_code: str
    marks_obtained: int
    wrong_answers: List[int]
    percentage: float
    answers: List[int]
    success: bool
    message: str = ""


class ResultResponse(BaseModel):
    """Schema for result in responses."""

    id: int
    exam_id: int
    roll_number: str
    set_code: str
    marks_obtained: int
    wrong_answers: List[int]
    percentage: float
    image_url: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
