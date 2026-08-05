"""
Attendance Tracker - SQLAlchemy ORM backed presence tracking.

A worker's "clock-in" is the first time their face is seen in a day and
"clock-out" is the last time it is seen. The pipeline calls `record_sighting`
every time a recognised worker appears on camera; this updates `last_seen` on
the day's row and creates one the first time. Working hours are simply
`last_seen - first_seen`.
"""
import csv
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Optional

from sqlalchemy import func

from models.attendance import FaceSighting
from models.worker import Worker
from models.base import SessionLocal

# Anomaly detection thresholds
MIN_WORK_HOURS = 1          # less than this → flagged as anomaly
MAX_WORK_HOURS = 16         # more than this → flagged as anomaly
EARLY_CLOCK_IN = 5          # hour before which clock-in is suspicious (5 AM)
LATE_CLOCK_OUT = 2          # hour after which clock-out is suspicious (2 AM)


class AttendanceTracker:
    def __init__(self, data_dir: str = "data/attendance"):
        self.attendance_dir = Path(data_dir)
        self.attendance_dir.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._today = date.today().isoformat()
        # presence: worker_id -> {"name", "first_seen": dt, "last_seen": dt}
        self._presence: dict[str, dict] = {}
        self._load_presence_from_db()

    # ── database helpers ──

    def _load_presence_from_db(self):
        """Load today's sightings from database into in-memory cache."""
        db = SessionLocal()
        try:
            today = date.today()
            rows = (
                db.query(FaceSighting, Worker)
                .join(Worker, FaceSighting.worker_id == Worker.id)
                .filter(func.date(FaceSighting.event_date) == today)
                .all()
            )
            self._presence = {}
            for sighting, worker in rows:
                self._presence[worker.worker_id] = {
                    "name": worker.name,
                    "first_seen": sighting.first_seen,
                    "last_seen": sighting.last_seen,
                }
        finally:
            db.close()

    def drop_worker(self, worker_id: str) -> None:
        """Forget a worker from the in-memory presence cache (after removal)."""
        with self._lock:
            self._presence.pop(worker_id, None)

    def _check_rollover(self):
        today = date.today().isoformat()
        if today != self._today:
            # Yesterday's rows are final: export the CSV, then load today.
            try:
                self.export_csv(self._today)
            except Exception:
                pass
            self._today = today
            self._load_presence_from_db()

    # ── core: record a sighting ──

    def record_sighting(self, worker_id: str, worker_name: str, seen_at: Optional[datetime] = None) -> bool:
        """Record that a worker's face was seen.

        First sighting of the day creates the presence row (clock-in = first
        seen); every later sighting just extends `last_seen` (clock-out = last
        seen). Returns False if the worker is not registered/active.
        """
        now = seen_at or datetime.now()
        with self._lock:
            self._check_rollover()
            db = SessionLocal()
            try:
                worker = (
                    db.query(Worker)
                    .filter(Worker.worker_id == worker_id, Worker.is_active == 1)
                    .first()
                )
                if worker is None:
                    return False

                # Upsert today's row.
                sighting = (
                    db.query(FaceSighting)
                    .filter(
                        FaceSighting.worker_id == worker.id,
                        func.date(FaceSighting.event_date) == now.date(),
                    )
                    .first()
                )
                if sighting is None:
                    sighting = FaceSighting(
                        worker_id=worker.id,
                        event_date=now,
                        first_seen=now,
                        last_seen=now,
                    )
                    db.add(sighting)
                else:
                    sighting.last_seen = now
                db.commit()
            finally:
                db.close()

            # Update in-memory cache.
            entry = self._presence.get(worker_id)
            if entry is None:
                self._presence[worker_id] = {
                    "name": worker_name,
                    "first_seen": now,
                    "last_seen": now,
                }
            else:
                entry["last_seen"] = now
                entry["name"] = worker_name

            # Log anomaly check silently.
            alarms = self.detect_anomalies(worker_id, worker_name)
            if alarms:
                print(f"[!] Anomaly detected for {worker_name} ({worker_id}):")
                for a in alarms:
                    print(f"      \u26a0 {a}")

            return True

    # ── smart analytics ──

    def daily_summary(self, worker_id: str) -> dict:
        """Return structured summary for a worker today (first/last seen)."""
        with self._lock:
            entry = self._presence.get(worker_id)
            if entry is None:
                return {
                    "worker_id": worker_id,
                    "first_seen": None,
                    "last_seen": None,
                    "total_hours": 0.0,
                    "num_sightings": 0,
                }
            total_sec = max(0.0, (entry["last_seen"] - entry["first_seen"]).total_seconds())
            return {
                "worker_id": worker_id,
                "first_seen": entry["first_seen"].strftime("%H:%M:%S"),
                "last_seen": entry["last_seen"].strftime("%H:%M:%S"),
                "total_hours": round(total_sec / 3600, 2),
                "num_sightings": 1,
            }

    def detect_anomalies(self, worker_id: str, worker_name: str) -> list[str]:
        """Detect suspicious attendance patterns per worker."""
        alarms: list[str] = []
        with self._lock:
            entry = self._presence.get(worker_id)

        if entry is None:
            return alarms

        first = entry["first_seen"]
        last = entry["last_seen"]

        # 1. early / late clock-in
        hour = first.hour
        if hour < EARLY_CLOCK_IN:
            alarms.append(f"Early clock-in at {first:%H:%M:%S} (before {EARLY_CLOCK_IN}:00)")
        elif hour >= 23:
            alarms.append(f"Late clock-in at {first:%H:%M:%S} (after 23:00)")

        # 2. late clock-out (after midnight)
        if last.hour < LATE_CLOCK_OUT:
            alarms.append(f"Late clock-out at {last:%H:%M:%S} (after midnight)")

        # 3. total hours anomaly
        total_hours = max(0.0, (last - first).total_seconds()) / 3600
        if 0 < total_hours < MIN_WORK_HOURS:
            alarms.append(
                f"Very short work period: {total_hours:.1f}h (min {MIN_WORK_HOURS}h)"
            )
        elif total_hours > MAX_WORK_HOURS:
            alarms.append(
                f"Overly long work period: {total_hours:.1f}h (max {MAX_WORK_HOURS}h)"
            )

        return alarms

    # ── status helpers ──

    def get_state(self, worker_id: str) -> str:
        """'in' if the worker has been seen today, else 'out'."""
        with self._lock:
            return "in" if worker_id in self._presence else "out"

    def count_in(self) -> int:
        with self._lock:
            return len(self._presence)

    def get_all_states(self) -> dict[str, str]:
        """Return a copy of all current in/out states for the admin page."""
        with self._lock:
            return {wid: "in" for wid in self._presence}

    def export_csv(self, target_date: str | None = None) -> Path:
        if target_date is None:
            with self._lock:
                target_date = self._today

        # Query database for the requested date.
        db = SessionLocal()
        try:
            target_date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
            rows_data = (
                db.query(FaceSighting, Worker)
                .join(Worker, FaceSighting.worker_id == Worker.id)
                .filter(func.date(FaceSighting.event_date) == target_date_obj)
                .order_by(FaceSighting.first_seen)
                .all()
            )
        finally:
            db.close()

        if not rows_data:
            raise FileNotFoundError(f"No attendance data for {target_date}")

        rows = []
        for sighting, worker in rows_data:
            total_sec = max(
                0.0, (sighting.last_seen - sighting.first_seen).total_seconds()
            )
            rows.append({
                "date": target_date,
                "worker_id": worker.worker_id,
                "name": worker.name,
                "first_in": sighting.first_seen.strftime("%H:%M:%S"),
                "last_out": sighting.last_seen.strftime("%H:%M:%S"),
                "total_hours": round(total_sec / 3600, 2),
            })

        rows.sort(key=lambda r: r["worker_id"])

        csv_path = self.attendance_dir / f"{target_date}.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["date", "worker_id", "name", "first_in", "last_out", "total_hours"],
            )
            writer.writeheader()
            writer.writerows(rows)

        return csv_path
