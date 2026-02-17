"""SQLAlchemy database models for OptiMark."""

from datetime import datetime
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    """User model for teachers/admins."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="teacher")  # 'admin' | 'teacher'
    is_subscribed = Column(Boolean, default=False)
    subscription_plan = Column(String(50), nullable=True)  # e.g., '1month', '6month', '1year'
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    exams = relationship("Exam", back_populates="teacher")
    pending_payments = relationship("PendingPayment", back_populates="user")


class PendingPayment(Base):
    """Manual payment submissions awaiting admin approval."""

    __tablename__ = "pending_payments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    plan_id = Column(String(50), nullable=False)  # 1month, 6month, 1year
    amount = Column(Float, nullable=False)
    payment_method = Column(String(30), nullable=False)  # bkash, nagad, bank_transfer
    transaction_id = Column(String(100), nullable=False)
    sender_name = Column(String(255), nullable=False)
    sender_phone = Column(String(50), nullable=True)  # For bKash/Nagad
    sender_email = Column(String(255), nullable=True)
    status = Column(String(20), default="pending")  # pending, approved, rejected
    admin_notes = Column(String(500), nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="pending_payments", foreign_keys=[user_id])


class Exam(Base):
    """Exam model - represents an OMR exam with metadata."""

    __tablename__ = "exams"

    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    subject_code = Column(String(50), nullable=False)
    total_questions = Column(Integer, default=60)
    date_created = Column(DateTime, default=datetime.utcnow)

    # Relationships
    teacher = relationship("User", back_populates="exams")
    answer_keys = relationship("AnswerKey", back_populates="exam", cascade="all, delete-orphan")
    results = relationship("Result", back_populates="exam", cascade="all, delete-orphan")


class AnswerKey(Base):
    """
    Answer key for each exam set (e.g., 'ক', 'খ' for Bengali or 'A', 'B' for English).
    answers: JSON object mapping question numbers to correct options.
    Example: {"1": 2, "2": 0, "3": 1} -> Q1=option 2, Q2=option 0, Q3=option 1
    """

    __tablename__ = "answer_keys"

    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    set_code = Column(String(10), nullable=False)  # 'ক', 'খ', 'A', 'B', etc.
    answers = Column(JSONB, nullable=False)  # {"1": 0, "2": 2, "3": 1, ...}

    # Relationships
    exam = relationship("Exam", back_populates="answer_keys")


class Result(Base):
    """Grading result for a scanned OMR sheet."""

    __tablename__ = "results"

    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    roll_number = Column(String(50), nullable=False)
    set_code = Column(String(10), nullable=False)
    marks_obtained = Column(Integer, default=0)
    wrong_answers = Column(JSONB, default=lambda: [])  # [2, 5, 12] - list of wrong question numbers
    percentage = Column(Float, default=0.0)
    image_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    exam = relationship("Exam", back_populates="results")
