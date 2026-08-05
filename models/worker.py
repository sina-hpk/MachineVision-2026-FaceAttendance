"""
Worker Model - Registered employees with face encodings
Compatible with both SQLite and PostgreSQL
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, DateTime, JSON, Text, ForeignKey, Index
from sqlalchemy.orm import relationship

from models.base import Base, GUID


class Worker(Base):
    """Registered worker/employee."""
    __tablename__ = "workers"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    worker_id = Column(String(10), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=True)
    department = Column(String(50), nullable=True)
    position = Column(String(50), nullable=True)
    is_active = Column(Integer, default=1)  # 1=active, 0=inactive
    registered_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    encodings = relationship("FaceEncoding", back_populates="worker", cascade="all, delete-orphan")
    attendance_events = relationship("AttendanceEvent", back_populates="worker")

    __table_args__ = (
        Index("ix_workers_name", "name"),
        Index("ix_workers_active", "is_active"),
    )

    def __repr__(self):
        return f"<Worker {self.worker_id}: {self.name}>"


class FaceEncoding(Base):
    """Stored face embeddings for workers."""
    __tablename__ = "face_encodings"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    worker_id = Column(GUID(), ForeignKey("workers.id", ondelete="CASCADE"), nullable=False)
    encoding = Column(JSON, nullable=False)  # JSON array of floats for cross-DB compatibility
    quality_score = Column(String, nullable=True)  # Store as string for precision
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    worker = relationship("Worker", back_populates="encodings")

    __table_args__ = (
        Index("ix_face_encodings_worker", "worker_id"),
    )

    def __repr__(self):
        return f"<FaceEncoding worker={self.worker_id}>"