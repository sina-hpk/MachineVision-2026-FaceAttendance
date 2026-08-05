"""
Shared fixtures for all tests.
Uses SQLite in-memory database with transaction rollback per test.
"""
import os
import sys
import pytest
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Override settings BEFORE any model imports
os.environ["DATABASE_URL"] = "sqlite:///data/test_cv_attendance.db"
os.environ["REDIS_URL"] = "redis://localhost:6379/1"
os.environ["LOG_LEVEL"] = "ERROR"
os.environ["METRICS_ENABLED"] = "false"

from sqlalchemy.orm import Session
from models.base import Base, engine, init_db
from models.repository import FaceRepository
from models.worker import Worker, FaceEncoding
from models.guest import Guest
from models.attendance import AttendanceEvent
from models import user as user_model
from config import settings

# Create all tables once at module load
init_db()


@pytest.fixture(autouse=True)
def setup_db():
    """Clean all tables before each test using table truncation."""
    # Delete all rows from each table (faster than drop/create)
    for table in reversed(Base.metadata.sorted_tables):
        with engine.begin() as conn:
            conn.execute(table.delete())
    yield


@pytest.fixture
def db_session():
    """Provide a fresh DB session."""
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def repo():
    """Provide a fresh FaceRepository with test faces dir."""
    faces_dir = Path("data/test_faces")
    faces_dir.mkdir(parents=True, exist_ok=True)
    repo_instance = FaceRepository(faces_dir=str(faces_dir))
    yield repo_instance
    # Cleanup test faces
    import shutil
    if faces_dir.exists():
        shutil.rmtree(faces_dir)


@pytest.fixture
def sample_worker(db_session) -> Worker:
    """Create a sample worker with face encoding."""
    import numpy as np
    worker = Worker(
        worker_id="W001",
        name="Test Worker",
        is_active=1,
    )
    db_session.add(worker)
    db_session.flush()

    fe = FaceEncoding(
        worker_id=worker.id,
        encoding=np.zeros(128, dtype=np.float64).tolist(),
        quality_score="0.8",
    )
    db_session.add(fe)
    db_session.commit()
    db_session.refresh(worker)
    return worker


@pytest.fixture
def sample_guest(db_session) -> Guest:
    """Create a sample guest."""
    import numpy as np
    guest = Guest(
        guest_id="guest_001",
        encodings=[np.zeros(128, dtype=np.float64).tolist()],
        promoted=0,
    )
    db_session.add(guest)
    db_session.commit()
    db_session.refresh(guest)
    return guest
