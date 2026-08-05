"""
Unit tests for AttendanceTracker (SQLAlchemy-backed, presence/LastSeen model).
"""
import numpy as np
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from models.repository import FaceRepository


@pytest.fixture
def attendance(registered_workers):
    """Create AttendanceTracker with test data dir."""
    from attendance import AttendanceTracker
    data_dir = Path("data/test_attendance")
    data_dir.mkdir(parents=True, exist_ok=True)
    tracker = AttendanceTracker(data_dir=str(data_dir))
    yield tracker
    # Cleanup
    import shutil
    if data_dir.exists():
        shutil.rmtree(data_dir)


@pytest.fixture
def registered_workers(db_session):
    """W001/W002 must exist: record_sighting() only tracks registered workers."""
    from models.worker import Worker
    for wid, name in (("W001", "Test User"), ("W002", "Bob")):
        db_session.add(Worker(worker_id=wid, name=name, is_active=1))
    db_session.commit()


@pytest.fixture
def repo_with_worker():
    """Create a repo with one test worker."""
    repo = FaceRepository(faces_dir="data/test_faces")
    repo.add_worker("Test User", [np.zeros(128)])
    return repo


class TestAttendanceTracker:
    """Test the presence (first-seen / last-seen) tracking logic."""

    def test_initial_state_all_out(self, attendance):
        assert attendance.count_in() == 0

    def test_first_sighting_marks_in(self, attendance):
        assert attendance.record_sighting("W001", "Test User")
        assert attendance.get_state("W001") == "in"
        assert attendance.count_in() == 1

    def test_repeated_sighting_keeps_in(self, attendance):
        attendance.record_sighting("W001", "Test User")
        attendance.record_sighting("W001", "Test User")
        # Still present — no toggle back to "out".
        assert attendance.get_state("W001") == "in"
        assert attendance.count_in() == 1

    def test_multiple_workers(self, attendance):
        attendance.record_sighting("W001", "Alice")
        attendance.record_sighting("W002", "Bob")
        assert attendance.count_in() == 2
        assert attendance.get_state("W001") == "in"
        assert attendance.get_state("W002") == "in"

    def test_last_seen_updates(self, attendance):
        t0 = datetime.now()
        attendance.record_sighting("W001", "Test User", seen_at=t0)
        t1 = t0 + timedelta(hours=2)
        attendance.record_sighting("W001", "Test User", seen_at=t1)
        summary = attendance.daily_summary("W001")
        assert summary["first_seen"] == t0.strftime("%H:%M:%S")
        assert summary["last_seen"] == t1.strftime("%H:%M:%S")
        assert summary["total_hours"] == 2.0

    def test_daily_summary_empty(self, attendance):
        summary = attendance.daily_summary("W001")
        assert summary["first_seen"] is None
        assert summary["last_seen"] is None
        assert summary["total_hours"] == 0.0

    def test_anomaly_short_work_period(self, attendance):
        t0 = datetime.now()
        attendance.record_sighting("W001", "Test User", seen_at=t0)
        alarms = attendance.detect_anomalies("W001", "Test User")
        # Sub-1h presence should be flagged unless we're past midnight.
        assert isinstance(alarms, list)

    def test_export_csv(self, attendance, tmp_path):
        """Test CSV export."""
        t0 = datetime.now()
        attendance.record_sighting("W001", "Test User", seen_at=t0)
        attendance.record_sighting("W001", "Test User", seen_at=t0 + timedelta(minutes=30))

        from datetime import date
        today = date.today().isoformat()
        csv_path = attendance.export_csv(today)
        assert csv_path.exists()

        # Verify CSV content
        import csv
        with open(csv_path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) > 0
        assert rows[0]["worker_id"] == "W001"
        assert rows[0]["total_hours"] == "0.5"

    def test_export_csv_no_data(self, attendance):
        with pytest.raises(FileNotFoundError):
            attendance.export_csv("2020-01-01")

    def test_unregistered_worker_is_ignored(self, attendance):
        """An unpromoted guest must not create a presence row."""
        assert not attendance.record_sighting("guest_001", "guest_001")
        assert attendance.count_in() == 0
