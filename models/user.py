"""
User Model - System users for authentication
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Index, Integer, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from models.base import Base, GUID
from auth import Role


class User(Base):
    """System user for authentication."""
    __tablename__ = "users"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=True)
    full_name = Column(String(100), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(SQLEnum(Role, name="user_role"), default=Role.VIEWER, nullable=False)
    is_active = Column(Integer, default=1)  # 1=active, 0=inactive
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_users_active", "is_active"),
    )

    def __repr__(self):
        return f"<User {self.username} ({self.role.value})>"
