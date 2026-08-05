"""
Guest Model - Unknown faces (temporary storage)
Compatible with both SQLite and PostgreSQL
"""
from sqlalchemy import Column, String, DateTime, Text, Index, Integer, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from models.base import Base, GUID


# Guests older than this are purged automatically.
GUEST_RETENTION_DAYS = 14


class Guest(Base):
    """Unknown face - temporary storage for potential registration."""
    __tablename__ = "guests"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    guest_id = Column(String(20), unique=True, nullable=False)  # guest_001, guest_002, ...
    encodings = Column(JSON, nullable=False)  # JSON array of face encodings
    registered_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    promoted = Column(Integer, default=0)  # 1 = promoted to worker
    promoted_to_worker_id = Column(GUID(), nullable=True)  # UUID of worker if promoted

    __table_args__ = (
        Index("ix_guests_promoted", "promoted"),
    )

    def __repr__(self):
        return f"<Guest {self.guest_id}>"