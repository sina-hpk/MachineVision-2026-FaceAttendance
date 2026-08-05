"""
Unified Database Repository — replaces database.py (JSON) with SQLAlchemy.
Provides the same interface as FaceDatabase for backward compatibility.

Usage:
    from models.repository import FaceRepository
    repo = FaceRepository()
    known_ids, encodings = repo.get_all_known()
"""
import cv2
import numpy as np
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from models import (
    db_session,
    Worker,
    FaceEncoding,
    Guest,
    GUEST_RETENTION_DAYS,
)
from models.attendance import FaceSighting
from models.base import SessionLocal
from sqlalchemy.orm import Session, joinedload


class DuplicateNameError(Exception):
    pass


class FaceRepository:
    """
    SQLAlchemy-backed repository that mirrors the FaceDatabase (JSON) interface.
    Thread-safe via SQLAlchemy session-per-operation.
    """

    def __init__(self, faces_dir: str = "data/faces"):
        self.faces_dir = Path(faces_dir)
        self.faces_dir.mkdir(parents=True, exist_ok=True)
        # Per-sample crops live one level down, keyed by worker then encoding id,
        # so the admin panel can show what each stored embedding was made from.
        self.samples_dir = self.faces_dir / "samples"
        self.samples_dir.mkdir(parents=True, exist_ok=True)
        self._log = logging.getLogger("FaceRepository")

    def _get_session(self) -> Session:
        """Create a new session for this operation."""
        return SessionLocal()

    # ── Sample images ──

    def sample_image_path(self, worker_id: str, encoding_id: str) -> Path:
        """On-disk location of the crop a single embedding was built from."""
        return self.samples_dir / worker_id / f"{encoding_id}.jpg"

    def _save_sample_image(
        self, worker_id: str, encoding_id: str, image: Optional[np.ndarray]
    ) -> None:
        if image is None or image.size == 0:
            return
        path = self.sample_image_path(worker_id, encoding_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(path), image)

    # ── Encoding lookup ──

    def get_all_known(self) -> tuple[list[str], list[np.ndarray]]:
        """Return (ids, encodings) for all active workers and non-promoted guests."""
        db = self._get_session()
        try:
            ids: list[str] = []
            encodings: list[np.ndarray] = []

            # Workers
            workers = db.query(Worker).filter(Worker.is_active == 1).all()
            for w in workers:
                for fe in w.encodings:
                    ids.append(w.worker_id)  # e.g. "W001"
                    encodings.append(np.array(fe.encoding, dtype=np.float64))

            # Guests (non-promoted only)
            guests = db.query(Guest).filter(Guest.promoted == 0).all()
            for g in guests:
                for enc_data in g.encodings:
                    ids.append(g.guest_id)  # e.g. "guest_001"
                    encodings.append(np.array(enc_data, dtype=np.float64))

            return ids, encodings
        finally:
            db.close()

    # ── Worker CRUD ──

    def add_worker(
        self,
        name: str,
        encodings: list[np.ndarray],
        face_image: Optional[np.ndarray] = None,
        sample_images: Optional[list[np.ndarray]] = None,
    ) -> str:
        """Register a new worker. Returns worker_id (e.g. 'W001').

        `sample_images` is optional and positionally paired with `encodings`;
        each crop is stored so the admin panel can show what a given embedding
        was built from.
        """
        db = self._get_session()
        try:
            if self._name_taken(db, name):
                raise DuplicateNameError(f"A worker named '{name}' already exists")

            wid = self._next_worker_id(db)
            worker = Worker(
                worker_id=wid,
                name=name,
                is_active=1,
            )
            db.add(worker)
            db.flush()  # Get worker.id

            # Save face encodings
            crops = sample_images or []
            for i, enc in enumerate(encodings):
                fe = FaceEncoding(
                    worker_id=worker.id,
                    encoding=enc.tolist(),
                    quality_score="0.5",
                )
                db.add(fe)
                db.flush()  # need fe.id to name the crop file
                if i < len(crops):
                    self._save_sample_image(wid, str(fe.id), crops[i])

            # Save face image
            if face_image is not None and face_image.size > 0:
                cv2.imwrite(str(self.faces_dir / f"{wid}.jpg"), face_image)

            db.commit()
            return wid
        except DuplicateNameError:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def add_encoding_to_worker(
        self,
        worker_id: str,
        encoding: np.ndarray,
        max_encodings: int = 10,
        sample_image: Optional[np.ndarray] = None,
    ) -> bool:
        """Add encoding to an existing worker. Returns True on success."""
        db = self._get_session()
        try:
            worker = (
                db.query(Worker)
                .filter(Worker.worker_id == worker_id, Worker.is_active == 1)
                .first()
            )
            if not worker:
                return False
            if len(worker.encodings) >= max_encodings:
                return False

            fe = FaceEncoding(
                worker_id=worker.id,
                encoding=encoding.tolist(),
                quality_score="0.6",
            )
            db.add(fe)
            db.flush()  # need fe.id to name the crop file
            self._save_sample_image(worker_id, str(fe.id), sample_image)
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            self._log.warning("add_encoding_to_worker(%s): %s", worker_id, e)
            return False
        finally:
            db.close()

    def remove_worker(self, identifier: str) -> tuple[bool, str]:
        """Remove worker by ID ('W001') or name. Returns (success, name).

        Soft delete in the DB (so past attendance events keep their FK) but a
        hard delete on disk: leaving face crops behind would keep a person's
        biometric data after they were removed from the system.
        """
        db = self._get_session()
        try:
            # Try by worker_id first
            worker = (
                db.query(Worker)
                .filter(Worker.worker_id == identifier)
                .first()
            )
            if not worker:
                # Try by name
                worker = (
                    db.query(Worker)
                    .filter(Worker.name == identifier)
                    .first()
                )
            if not worker:
                return False, ""

            name = worker.name
            wid = worker.worker_id
            # Hard delete: the worker row, their biometric vectors and their
            # presence records are all removed. The user expects a deleted
            # worker to vanish everywhere (admin page AND today's report), so
            # nothing may survive. Attendance history for *kept* workers is
            # untouched; only this worker's rows go away.
            # NOTE: FK columns reference workers.id (a UUID), not the
            # human-facing worker_id string — filter by the PK.
            db.query(FaceSighting).filter(
                FaceSighting.worker_id == worker.id
            ).delete(synchronize_session=False)
            db.query(FaceEncoding).filter(
                FaceEncoding.worker_id == worker.id
            ).delete(synchronize_session=False)
            db.delete(worker)
            db.commit()

            # Remove face image
            img_path = self.faces_dir / f"{wid}.jpg"
            if img_path.exists():
                img_path.unlink()

            # Remove per-sample crops
            sample_dir = self.samples_dir / wid
            if sample_dir.exists():
                for f in sample_dir.glob("*.jpg"):
                    f.unlink()
                sample_dir.rmdir()

            return True, name
        except Exception as e:
            db.rollback()
            self._log.warning("remove_worker(%s): %s", identifier, e)
            return False, ""
        finally:
            db.close()

    def list_workers(self) -> list[dict]:
        """List all active workers."""
        db = self._get_session()
        try:
            workers = db.query(Worker).filter(Worker.is_active == 1).all()
            return [
                {
                    "id": w.worker_id,
                    "name": w.name,
                    "email": w.email or "",
                    "department": w.department or "",
                    "position": w.position or "",
                    "registered_at": w.registered_at.isoformat() if w.registered_at else "",
                }
                for w in sorted(workers, key=lambda x: x.worker_id)
            ]
        finally:
            db.close()

    def worker_count(self) -> int:
        """Count active workers."""
        db = self._get_session()
        try:
            return db.query(Worker).filter(Worker.is_active == 1).count()
        finally:
            db.close()

    def count_encodings(self, worker_id: str) -> int:
        """Count face vectors stored for a worker (active or not).

        `worker_id` is the human-facing string ('W001'); encodings key on the
        UUID PK, so join through Worker to resolve it.
        """
        db = self._get_session()
        try:
            return (
                db.query(FaceEncoding)
                .join(Worker, FaceEncoding.worker_id == Worker.id)
                .filter(Worker.worker_id == worker_id)
                .count()
            )
        finally:
            db.close()

    def list_workers_detailed(self) -> list[dict]:
        """Active workers with their face samples, for the admin page."""
        db = self._get_session()
        try:
            workers = (
                db.query(Worker)
                .filter(Worker.is_active == 1)
                .options(joinedload(Worker.encodings))
                .all()
            )
            return [
                {
                    "id": w.worker_id,
                    "name": w.name,
                    "department": w.department or "",
                    "position": w.position or "",
                    "registered_at": w.registered_at.isoformat() if w.registered_at else "",
                    "has_image": (self.faces_dir / f"{w.worker_id}.jpg").exists(),
                    "sample_count": len(w.encodings),
                    "samples": [
                        {
                            "id": str(fe.id),
                            "quality": fe.quality_score or "",
                            "created_at": fe.created_at.isoformat() if fe.created_at else "",
                            "dim": len(fe.encoding) if fe.encoding else 0,
                            # Samples stored before crops were saved have no
                            # image; the UI shows a placeholder for those.
                            "has_image": self.sample_image_path(
                                w.worker_id, str(fe.id)
                            ).exists(),
                        }
                        for fe in sorted(
                            w.encodings, key=lambda e: e.created_at or datetime.min
                        )
                    ],
                }
                for w in sorted(workers, key=lambda x: x.worker_id)
            ]
        finally:
            db.close()

    def remove_encoding(self, worker_id: str, encoding_id: str) -> tuple[bool, str]:
        """Delete one face sample. Refuses to remove a worker's last sample."""
        db = self._get_session()
        try:
            worker = (
                db.query(Worker)
                .filter(Worker.worker_id == worker_id, Worker.is_active == 1)
                .first()
            )
            if worker is None:
                return False, "Worker not found"

            target = next(
                (fe for fe in worker.encodings if str(fe.id) == encoding_id), None
            )
            if target is None:
                return False, "Sample not found"
            if len(worker.encodings) <= 1:
                return False, "Cannot delete the only sample — the worker would never be recognized"

            db.delete(target)
            db.commit()

            crop = self.sample_image_path(worker_id, encoding_id)
            if crop.exists():
                crop.unlink()
            return True, "deleted"
        except Exception as e:
            db.rollback()
            self._log.warning("remove_encoding(%s, %s): %s", worker_id, encoding_id, e)
            return False, str(e)
        finally:
            db.close()

    # ── Guest CRUD ──

    def add_guest(
        self,
        encodings: list[np.ndarray],
        face_image: Optional[np.ndarray] = None,
    ) -> str:
        """Register an unknown face as guest. Returns guest_id (e.g. 'guest_001')."""
        db = self._get_session()
        try:
            gid = self._next_guest_id(db)

            guest = Guest(
                guest_id=gid,
                encodings=[enc.tolist() for enc in encodings],
                promoted=0,
            )
            db.add(guest)
            db.commit()

            if face_image is not None and face_image.size > 0:
                cv2.imwrite(str(self.faces_dir / f"{gid}.jpg"), face_image)

            return gid
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def promote_guest_to_worker(self, guest_id: str, name: str) -> str:
        """Promote a guest to registered worker. Returns worker_id."""
        db = self._get_session()
        try:
            if self._name_taken(db, name):
                raise DuplicateNameError(f"A worker named '{name}' already exists")

            guest = db.query(Guest).filter(Guest.guest_id == guest_id).first()
            if not guest:
                raise ValueError(f"Guest '{guest_id}' not found")

            # Create worker
            wid = self._next_worker_id(db)
            worker = Worker(
                worker_id=wid,
                name=name,
                is_active=1,
            )
            db.add(worker)
            db.flush()

            # Copy encodings from guest
            for enc_data in guest.encodings:
                fe = FaceEncoding(
                    worker_id=worker.id,
                    encoding=enc_data,
                    quality_score="0.5",
                )
                db.add(fe)

            # Mark guest as promoted
            guest.promoted = 1
            guest.promoted_to_worker_id = str(worker.id)

            # Move face image
            old_img = self.faces_dir / f"{guest_id}.jpg"
            if old_img.exists():
                old_img.rename(self.faces_dir / f"{wid}.jpg")

            db.commit()
            return wid
        except DuplicateNameError:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def list_guests(self) -> list[dict]:
        """List non-promoted guests."""
        db = self._get_session()
        try:
            guests = db.query(Guest).filter(Guest.promoted == 0).all()
            return [
                {
                    "id": g.guest_id,
                    "registered_at": g.registered_at.isoformat() if g.registered_at else "",
                    "last_seen": g.last_seen.isoformat() if g.last_seen else "",
                }
                for g in guests
            ]
        finally:
            db.close()

    def remove_guest(self, guest_id: str) -> bool:
        """Remove a guest."""
        db = self._get_session()
        try:
            guest = db.query(Guest).filter(Guest.guest_id == guest_id).first()
            if not guest:
                return False
            db.delete(guest)
            db.commit()

            img_path = self.faces_dir / f"{guest_id}.jpg"
            if img_path.exists():
                img_path.unlink()
            return True
        except Exception as e:
            db.rollback()
            self._log.warning("remove_guest(%s): %s", guest_id, e)
            return False
        finally:
            db.close()

    def guest_count(self) -> int:
        """Count non-promoted guests."""
        db = self._get_session()
        try:
            return db.query(Guest).filter(Guest.promoted == 0).count()
        finally:
            db.close()

    def purge_expired_guests(self) -> int:
        """Delete guests not seen for GUEST_RETENTION_DAYS. Returns count removed."""
        cutoff = datetime.utcnow() - timedelta(days=GUEST_RETENTION_DAYS)
        db = self._get_session()
        try:
            expired = (
                db.query(Guest)
                .filter(Guest.promoted == 0, Guest.last_seen < cutoff)
                .all()
            )
            removed = 0
            for g in expired:
                img_path = self.faces_dir / f"{g.guest_id}.jpg"
                if img_path.exists():
                    img_path.unlink()
                db.delete(g)
                removed += 1
            db.commit()
            return removed
        except Exception as e:
            db.rollback()
            self._log.warning("purge_expired_guests: %s", e)
            return 0
        finally:
            db.close()

    # ── Person lookup ──

    def get_person(self, person_id: str) -> Optional[dict]:
        """Look up person by worker_id ('W001') or guest_id ('guest_001')."""
        db = self._get_session()
        try:
            # Try worker
            worker = (
                db.query(Worker)
                .filter(Worker.worker_id == person_id, Worker.is_active == 1)
                .first()
            )
            if worker:
                return {"name": worker.name, "type": "worker", "id": person_id}

            # Try guest
            guest = (
                db.query(Guest)
                .filter(Guest.guest_id == person_id, Guest.promoted == 0)
                .first()
            )
            if guest:
                return {"name": person_id, "type": "guest", "id": person_id}

            return None
        finally:
            db.close()

    # ── Helpers ──

    def _next_worker_id(self, db: Session) -> str:
        """Generate next available Wxxx ID using atomic SQL."""
        from sqlalchemy import func as sa_func
        max_num = db.query(
            sa_func.max(Worker.worker_id)
        ).filter(
            Worker.worker_id.like("W%")
        ).scalar()
        if not max_num:
            return "W001"
        # Extract numeric part and increment
        try:
            next_num = int(max_num[1:]) + 1
        except (ValueError, IndexError):
            return "W001"
        return f"W{next_num:03d}"

    @staticmethod
    def _next_guest_id(db: Session) -> str:
        """Generate next available guest_xxx ID from the current maximum."""
        from sqlalchemy import func as sa_func
        max_id = db.query(sa_func.max(Guest.guest_id)).filter(
            Guest.guest_id.like("guest_%")
        ).scalar()
        if not max_id:
            return "guest_001"
        try:
            next_num = int(max_id.rsplit("_", 1)[1]) + 1
        except (ValueError, IndexError):
            return "guest_001"
        return f"guest_{next_num:03d}"

    @staticmethod
    def _name_taken(db: Session, name: str) -> bool:
        """Check if a worker name is already taken."""
        return (
            db.query(Worker)
            .filter(Worker.name == name.strip(), Worker.is_active == 1)
            .first()
            is not None
        )

    @staticmethod
    def _parse_worker_id(s: str) -> Optional[int]:
        """Extract numeric ID from 'W001' -> 1."""
        if s.upper().startswith("W"):
            try:
                return int(s[1:])
            except ValueError:
                pass
        return None
