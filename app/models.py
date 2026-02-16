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
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    """User model for teachers/admins."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_subscribed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    exams = relationship("Exam", back_populates="teacher")


class Exam(Base):
    """Exam model - represents an OMR exam with metadata."""

    __tablename__ = "exams"

    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)
    subject_code = Column(String(50), nullable=False)
    total_questions = Column(Integer, default=60)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    teacher = relationship("User", back_populates="exams")
    answer_keys = relationship("AnswerKey", back_populates="exam", cascade="all, delete-orphan")
    results = relationship("Result", back_populates="exam", cascade="all, delete-orphan")


class AnswerKey(Base):
    """Answer key for each exam set (A, B, C, etc.)."""

    __tablename__ = "answer_keys"

    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    set_code = Column(String(10), nullable=False)  # 'A', 'B', 'C', etc.
    question_no = Column(Integer, nullable=False)
    correct_option = Column(Integer, nullable=False)  # 0-3 for circles (A, B, C, D)

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
    wrong_answers = Column(Integer, default=0)
    percentage = Column(Float, default=0.0)
    uploaded_image_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    exam = relationship("Exam", back_populates="results")
