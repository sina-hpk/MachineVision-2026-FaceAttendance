"""
Unit tests for FaceRepository (SQLAlchemy-backed, replacing FaceDatabase).
"""
import numpy as np
import pytest
from models.repository import FaceRepository, DuplicateNameError
from models.worker import Worker


class TestFaceRepository:
    """Test the unified SQLAlchemy repository."""

    def test_add_worker(self, repo):
        wid = repo.add_worker("Alice", [np.zeros(128)])
        assert wid == "W001"
        assert repo.worker_count() == 1

    def test_add_worker_auto_increment_id(self, repo):
        w1 = repo.add_worker("Alice", [np.zeros(128)])
        w2 = repo.add_worker("Bob", [np.zeros(128)])
        assert w1 == "W001"
        assert w2 == "W002"

    def test_add_worker_duplicate_name_raises(self, repo):
        repo.add_worker("Alice", [np.zeros(128)])
        with pytest.raises(DuplicateNameError):
            repo.add_worker("Alice", [np.zeros(128)])

    def test_list_workers(self, repo):
        repo.add_worker("Alice", [np.zeros(128)])
        repo.add_worker("Bob", [np.zeros(128)])
        workers = repo.list_workers()
        assert len(workers) == 2
        names = [w["name"] for w in workers]
        assert "Alice" in names
        assert "Bob" in names

    def test_remove_worker_by_id(self, repo):
        repo.add_worker("Alice", [np.zeros(128)])
        ok, name = repo.remove_worker("W001")
        assert ok
        assert name == "Alice"
        assert repo.worker_count() == 0

    def test_remove_worker_by_name(self, repo):
        repo.add_worker("Alice", [np.zeros(128)])
        ok, name = repo.remove_worker("Alice")
        assert ok
        assert name == "Alice"

    def test_remove_nonexistent_worker(self, repo):
        ok, name = repo.remove_worker("W999")
        assert not ok
        assert name == ""

    # ── Per-sample crop images (admin panel) ──

    def test_sample_image_saved_with_worker(self, repo):
        img = np.full((60, 60, 3), 128, dtype=np.uint8)
        repo.add_worker("Alice", [np.zeros(128)], sample_images=[img])
        samples = repo.list_workers_detailed()[0]["samples"]
        assert samples[0]["has_image"] is True
        assert repo.sample_image_path("W001", samples[0]["id"]).exists()

    def test_sample_without_image_is_flagged(self, repo):
        repo.add_worker("Alice", [np.zeros(128)])
        assert repo.list_workers_detailed()[0]["samples"][0]["has_image"] is False

    def test_manual_sample_image_saved(self, repo):
        repo.add_worker("Alice", [np.zeros(128)])
        img = np.full((60, 60, 3), 200, dtype=np.uint8)
        assert repo.add_encoding_to_worker("W001", np.ones(128), sample_image=img)
        samples = repo.list_workers_detailed()[0]["samples"]
        assert [s["has_image"] for s in samples] == [False, True]

    def test_deleting_sample_removes_its_image(self, repo):
        img = np.full((60, 60, 3), 128, dtype=np.uint8)
        repo.add_worker("Alice", [np.zeros(128)], sample_images=[img])
        repo.add_encoding_to_worker("W001", np.ones(128), sample_image=img)
        sid = repo.list_workers_detailed()[0]["samples"][1]["id"]
        path = repo.sample_image_path("W001", sid)
        assert path.exists()

        ok, _ = repo.remove_encoding("W001", sid)
        assert ok
        assert not path.exists()

    def test_removing_worker_deletes_sample_images(self, repo):
        img = np.full((60, 60, 3), 128, dtype=np.uint8)
        repo.add_worker("Alice", [np.zeros(128)], sample_images=[img])
        sample_dir = repo.samples_dir / "W001"
        assert sample_dir.exists()

        ok, _ = repo.remove_worker("W001")
        assert ok
        assert not sample_dir.exists()

    def test_removing_worker_deletes_encodings(self, repo):
        """Biometric vectors are personal data: removal must purge them
        (hard delete on disk/DB), not just soft-delete the worker row."""
        img = np.full((60, 60, 3), 128, dtype=np.uint8)
        repo.add_worker(
            "Alice",
            [np.zeros(128), np.ones(128), np.full(128, 0.5)],
            sample_images=[img, img, img],
        )
        enc_count = repo.count_encodings("W001")
        assert enc_count == 3

        ok, _ = repo.remove_worker("W001")
        assert ok
        # Worker row is gone entirely...
        assert repo.worker_count() == 0
        # ...every biometric vector is gone from the DB...
        assert repo.count_encodings("W001") == 0
        # ...and the worker cannot be found by name or ID anymore.
        assert repo.get_person("W001") is None
        assert repo.get_person("Alice") is None

    def test_removing_worker_deletes_sightings(self, repo):
        """A deleted worker must vanish from today's attendance report too."""
        from models.attendance import FaceSighting
        from models.base import SessionLocal
        from datetime import datetime

        repo.add_worker("Alice", [np.zeros(128)])
        db = SessionLocal()
        try:
            worker = db.query(Worker).filter(Worker.worker_id == "W001").first()
            db.add(FaceSighting(
                worker_id=worker.id,
                event_date=datetime.now(),
                first_seen=datetime.now(),
                last_seen=datetime.now(),
            ))
            db.commit()
        finally:
            db.close()

        ok, _ = repo.remove_worker("W001")
        assert ok

        db = SessionLocal()
        try:
            leftovers = (
                db.query(FaceSighting)
                .join(Worker, FaceSighting.worker_id == Worker.id)
                .filter(Worker.worker_id == "W001")
                .count()
            )
        finally:
            db.close()
        assert leftovers == 0

    def test_get_person_worker(self, repo):
        repo.add_worker("Alice", [np.zeros(128)])
        person = repo.get_person("W001")
        assert person is not None
        assert person["name"] == "Alice"
        assert person["type"] == "worker"

    def test_get_person_nonexistent(self, repo):
        person = repo.get_person("W999")
        assert person is None

    def test_add_encoding_to_worker(self, repo):
        repo.add_worker("Alice", [np.zeros(128)])
        result = repo.add_encoding_to_worker("W001", np.ones(128))
        assert result is True

    def test_add_encoding_to_nonexistent_worker(self, repo):
        result = repo.add_encoding_to_worker("W999", np.ones(128))
        assert result is False

    def test_get_all_known(self, repo):
        repo.add_worker("Alice", [np.zeros(128)])
        repo.add_worker("Bob", [np.ones(128)])
        repo.add_guest([np.full(128, 0.5)])

        ids, encs = repo.get_all_known()
        assert len(ids) >= 2  # 2 workers + 1 guest
        assert all(isinstance(e, np.ndarray) for e in encs)

    def test_add_guest(self, repo):
        gid = repo.add_guest([np.zeros(128)])
        assert gid.startswith("guest_")
        assert repo.guest_count() == 1

    def test_promote_guest_to_worker(self, repo):
        gid = repo.add_guest([np.zeros(128)])
        wid = repo.promote_guest_to_worker(gid, "Promoted")
        assert wid == "W001"
        # Guest should no longer be counted
        assert repo.guest_count() == 0
        # Worker should exist
        person = repo.get_person("W001")
        assert person["name"] == "Promoted"

    def test_promote_guest_nonexistent_raises(self, repo):
        with pytest.raises(ValueError):
            repo.promote_guest_to_worker("guest_999", "Nobody")

    def test_list_guests(self, repo):
        repo.add_guest([np.zeros(128)])
        repo.add_guest([np.ones(128)])
        guests = repo.list_guests()
        assert len(guests) == 2

    def test_remove_guest(self, repo):
        gid = repo.add_guest([np.zeros(128)])
        result = repo.remove_guest(gid)
        assert result is True
        assert repo.guest_count() == 0

    def test_remove_nonexistent_guest(self, repo):
        result = repo.remove_guest("guest_999")
        assert result is False

    def test_worker_count(self, repo):
        assert repo.worker_count() == 0
        repo.add_worker("Alice", [np.zeros(128)])
        assert repo.worker_count() == 1

    def test_guest_count(self, repo):
        assert repo.guest_count() == 0
        repo.add_guest([np.zeros(128)])
        assert repo.guest_count() == 1

    def test_guest_id_not_reused_after_removal(self, repo):
        g1 = repo.add_guest([np.zeros(128)])
        g2 = repo.add_guest([np.ones(128)])
        assert (g1, g2) == ("guest_001", "guest_002")
        repo.remove_guest(g1)
        # Counting rows would hand out guest_002 again and hit the unique index
        assert repo.add_guest([np.full(128, 0.5)]) == "guest_003"

    def test_purge_expired_guests(self, repo, db_session):
        from datetime import datetime, timedelta
        from models.guest import Guest, GUEST_RETENTION_DAYS

        fresh = repo.add_guest([np.zeros(128)])
        stale = repo.add_guest([np.ones(128)])

        guest = db_session.query(Guest).filter(Guest.guest_id == stale).one()
        guest.last_seen = datetime.utcnow() - timedelta(days=GUEST_RETENTION_DAYS + 1)
        db_session.commit()

        assert repo.purge_expired_guests() == 1
        remaining = [g["id"] for g in repo.list_guests()]
        assert remaining == [fresh]
