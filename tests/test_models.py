"""
Unit tests for SQLAlchemy models.
"""
import uuid
import numpy as np
from datetime import datetime, date
from models.worker import Worker, FaceEncoding
from models.guest import Guest
from models.attendance import AttendanceEvent
from models.user import User
from auth import Role


class TestWorkerModel:
    """Test Worker + FaceEncoding models."""

    def test_create_worker(self, db_session):
        worker = Worker(
            worker_id="W001",
            name="John Doe",
            department="Engineering",
            position="Developer",
            is_active=1,
        )
        db_session.add(worker)
        db_session.commit()

        saved = db_session.query(Worker).filter(Worker.worker_id == "W001").first()
        assert saved is not None
        assert saved.name == "John Doe"
        assert saved.department == "Engineering"
        assert saved.position == "Developer"
        assert saved.is_active == 1
        assert saved.registered_at is not None

    def test_worker_id_unique(self, db_session):
        w1 = Worker(worker_id="W001", name="Alice", is_active=1)
        db_session.add(w1)
        db_session.commit()

        w2 = Worker(worker_id="W001", name="Bob", is_active=1)
        db_session.add(w2)
        with pytest.raises(Exception):
            db_session.commit()
        db_session.rollback()

    def test_face_encoding_relationship(self, db_session):
        worker = Worker(worker_id="W001", name="Test", is_active=1)
        db_session.add(worker)
        db_session.flush()

        enc = FaceEncoding(
            worker_id=worker.id,
            encoding=np.zeros(128, dtype=np.float64).tolist(),
            quality_score="0.9",
        )
        db_session.add(enc)
        db_session.commit()

        # Verify cascade / relationship
        saved = db_session.query(Worker).filter(Worker.worker_id == "W001").first()
        assert len(saved.encodings) == 1
        assert len(saved.encodings[0].encoding) == 128

    def test_cascade_delete(self, db_session):
        worker = Worker(worker_id="W001", name="Test", is_active=1)
        db_session.add(worker)
        db_session.flush()

        enc = FaceEncoding(worker_id=worker.id, encoding=[0.1, 0.2])
        db_session.add(enc)
        db_session.commit()

        db_session.delete(worker)
        db_session.commit()

        # FaceEncoding should be deleted
        count = db_session.query(FaceEncoding).count()
        assert count == 0

    def test_worker_repr(self):
        w = Worker(worker_id="W001", name="Test", is_active=1)
        assert "W001" in repr(w)
        assert "Test" in repr(w)


class TestGuestModel:
    """Test Guest model."""

    def test_create_guest(self, db_session):
        guest = Guest(
            guest_id="guest_001",
            encodings=[[0.1, 0.2], [0.3, 0.4]],
            promoted=0,
        )
        db_session.add(guest)
        db_session.commit()

        saved = db_session.query(Guest).filter(Guest.guest_id == "guest_001").first()
        assert saved is not None
        assert len(saved.encodings) == 2
        assert saved.promoted == 0
        assert saved.registered_at is not None
        assert saved.last_seen is not None

    def test_guest_promoted_default(self, db_session):
        guest = Guest(guest_id="guest_001", encodings=[], promoted=0)
        db_session.add(guest)
        db_session.commit()
        assert guest.promoted == 0


class TestAttendanceEventModel:
    """Test AttendanceEvent model."""

    def test_create_event(self, db_session, sample_worker):
        event = AttendanceEvent(
            worker_id=sample_worker.id,
            event_type="in",
        )
        db_session.add(event)
        db_session.commit()

        saved = db_session.query(AttendanceEvent).first()
        assert saved is not None
        assert saved.event_type == "in"
        assert saved.event_time is not None
        assert saved.event_date is not None

    def test_event_worker_relationship(self, db_session, sample_worker):
        event = AttendanceEvent(
            worker_id=sample_worker.id,
            event_type="in",
        )
        db_session.add(event)
        db_session.commit()

        saved = db_session.query(AttendanceEvent).first()
        assert saved.worker is not None
        assert saved.worker.worker_id == "W001"

    def test_event_types(self, db_session, sample_worker):
        for etype in ["in", "out"]:
            event = AttendanceEvent(
                worker_id=sample_worker.id,
                event_type=etype,
            )
            db_session.add(event)
        db_session.commit()

        events = db_session.query(AttendanceEvent).all()
        assert len(events) == 2
        assert {e.event_type for e in events} == {"in", "out"}


class TestUserModel:
    """Test User model."""

    def test_create_user(self, db_session):
        user = User(
            username="admin",
            email="admin@example.com",
            hashed_password="hashed_pw_here",
            role=Role.ADMIN,
        )
        db_session.add(user)
        db_session.commit()

        saved = db_session.query(User).filter(User.username == "admin").first()
        assert saved is not None
        assert saved.email == "admin@example.com"
        assert saved.role == Role.ADMIN
        assert saved.is_active == 1

    def test_username_unique(self, db_session):
        u1 = User(username="user1", hashed_password="pw", role=Role.VIEWER)
        db_session.add(u1)
        db_session.commit()

        u2 = User(username="user1", hashed_password="pw", role=Role.VIEWER)
        db_session.add(u2)
        with pytest.raises(Exception):
            db_session.commit()
        db_session.rollback()

    def test_user_repr(self):
        u = User(username="test_user", hashed_password="pw", role=Role.OPERATOR)
        assert "operator" in repr(u)
        assert "test_user" in repr(u)

    def test_default_role_is_viewer(self, db_session):
        user = User(username="new_user", hashed_password="pw")
        db_session.add(user)
        db_session.commit()
        assert user.role == Role.VIEWER


import pytest  # needed for test_models.py fixtures with pytest.raises
