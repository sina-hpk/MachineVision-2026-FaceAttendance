"""
Attendance Event Model - Check-in/Check-out events
Compatible with both SQLite and PostgreSQL
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum as SQLEnum, Index, Integer, JSON, Text
from sqlalchemy.orm import relationship
from datetime import datetime, date
import uuid

from models.base import Base, GUID


class AttendanceEvent(Base):
    """Single check-in or check-out event."""
    __tablename__ = "attendance_events"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    worker_id = Column(GUID(), ForeignKey("workers.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(SQLEnum("in", "out", name="event_type"), nullable=False)  # "in" or "out"
    event_time = Column(DateTime, default=datetime.utcnow, nullable=False)
    event_date = Column(DateTime, default=date.today, nullable=False)  # For daily grouping
    quality_score = Column(String, nullable=True)  # Face quality at time of event
    confidence = Column(String, nullable=True)     # Recognition confidence
    device_info = Column(Text, nullable=True)      # Camera/device info

    # Relationship
    worker = relationship("Worker", back_populates="attendance_events")

    __table_args__ = (
        Index("ix_attendance_events_worker_date", "worker_id", "event_date"),
        Index("ix_attendance_events_event_time", "event_time"),
        Index("ix_attendance_events_type", "event_type"),
    )

    def __repr__(self):
        return f"<AttendanceEvent {self.worker_id} {self.event_type} at {self.event_time}>"


class FaceSighting(Base):
    """A continuous presence period: the first and last time a worker's face
    was seen in a day.

    Instead of toggle-style in/out events, the pipeline records the earliest
    (`first_seen`) and latest (`last_seen`) detection. Working hours are simply
    `last_seen - first_seen`. `last_seen` is updated whenever the worker is
    recognised again.
    """
    __tablename__ = "face_sightings"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    worker_id = Column(GUID(), ForeignKey("workers.id", ondelete="CASCADE"), nullable=False)
    event_date = Column(DateTime, default=date.today, nullable=False)  # For daily grouping
    first_seen = Column(DateTime, nullable=False)
    last_seen = Column(DateTime, nullable=False)

    # Relationship
    worker = relationship("Worker")

    __table_args__ = (
        Index("ix_face_sightings_worker_date", "worker_id", "event_date"),
        Index("ix_face_sightings_last_seen", "last_seen"),
    )

    def __repr__(self):
        return (
            f"<FaceSighting {self.worker_id} "
            f"{self.first_seen:%H:%M:%S}-{self.last_seen:%H:%M:%S}>"
        )