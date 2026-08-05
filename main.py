"""
main.py — CLI ورود به سیستم

دستورات:
  run      اجرای دوربین مستقیم (CLI)
  web      اجرای داشبورد وب
  list     لیست کارگران
  remove   حذف کارگر
  guests   مدیریت مهمان‌ها
  export   خروجی CSV
"""

import argparse
import sys
from datetime import datetime, timedelta

from attendance import AttendanceTracker
from models.repository import FaceRepository, DuplicateNameError
from face_recognizer import FaceRecognizer

COOLDOWN_SEC = 10


def cmd_run(_args):
    """دوربین مستقیم: تشخیص چهره + ثبت تردد در ترمینال"""
    db = FaceRepository()
    attendance = AttendanceTracker()
    recognizer = FaceRecognizer(db)
    cooldowns: dict[str, datetime] = {}

    print("=== CV Attendance (CLI) ===")
    print(f"Workers: {db.worker_count()}")

    def on_known(pid: str, name: str):
        now = datetime.now()
        if now < cooldowns.get(pid, datetime.min):
            return
        if not attendance.record_sighting(pid, name, now):
            return
        cooldowns[pid] = now + timedelta(seconds=COOLDOWN_SEC)
        print(f"[{now.strftime('%H:%M:%S')}] → SEEN {name} ({pid})")

    def on_unknown(enc, crop):
        print("\n[!] New face detected")
        encodings = recognizer.capture_encodings(enc)
        gid = db.add_guest(encodings, face_image=crop)
        print(f"    Saved as '{gid}' ({len(encodings)} samples)")
        answer = _prompt("    Register as worker? (y/n): ")
        if answer in ("y", "yes"):
            while True:
                name = _prompt("    Full name: ").strip()
                if not name:
                    print("    Skipped.")
                    break
                try:
                    pid = db.promote_guest_to_worker(gid, name)
                    print(f"    Registered: {name} ({pid})\n")
                    break
                except DuplicateNameError:
                    print(f"    '{name}' already exists.")
        else:
            print(f"    Kept as '{gid}'.\n")

    def hud():
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return [now, f"Workers: {db.worker_count()} | In: {attendance.count_in()}"]

    recognizer.run(on_unknown=on_unknown, on_known=on_known, hud=hud)


def cmd_list(_args):
    db = FaceRepository()
    workers = db.list_workers()
    if not workers:
        print("No workers.")
        return
    print(f"\n{'ID':<6} {'Name':<30} Registered")
    print("-" * 56)
    for w in workers:
        print(f"{w['id']:<6} {w['name']:<30} {w['registered_at'][:10]}")
    print(f"\nTotal: {len(workers)}")


def cmd_remove(args):
    db = FaceRepository()
    identifier = " ".join(args.identifier)
    ok, name = db.remove_worker(identifier)
    if ok:
        print(f"Removed: {name}")
    else:
        print(f"Not found: '{identifier}'")
        sys.exit(1)


def cmd_guests(args):
    db = FaceRepository()
    if args.guests_command == "list" or not args.guests_command:
        guests = db.list_guests()
        if not guests:
            print("No guests.")
            return
        print(f"\n{'ID':<14} Registered")
        print("-" * 40)
        for g in guests:
            print(f"{g['id']:<14} {g['registered_at'][:10]}")
        print(f"\nTotal: {len(guests)}")
    elif args.guests_command == "remove":
        if db.remove_guest(args.guest_id):
            print(f"Removed: {args.guest_id}")
        else:
            print(f"Not found: {args.guest_id}")
            sys.exit(1)


def cmd_export(args):
    try:
        path = AttendanceTracker().export_csv(args.date or None)
        print(f"CSV: {path}")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)


def cmd_web(args):
    import uvicorn
    uvicorn.run("main_fastapi:app", host=args.host, port=args.port)


def _prompt(msg: str) -> str:
    try:
        return input(msg).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return ""


def main():
    p = argparse.ArgumentParser(prog="python main.py", description="CV Attendance System")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("run", help="CLI camera mode (default)")
    sub.add_parser("list", help="List workers")

    rm = sub.add_parser("remove", help="Remove worker")
    rm.add_argument("identifier", nargs="+", help="ID or name")

    g = sub.add_parser("guests", help="Manage guests")
    gs = g.add_subparsers(dest="guests_command")
    gs.add_parser("list", help="List guests")
    gr = gs.add_parser("remove", help="Remove guest")
    gr.add_argument("guest_id", help="Guest ID")

    e = sub.add_parser("export", help="Export CSV")
    e.add_argument("date", nargs="?", help="YYYY-MM-DD (default: today)")

    w = sub.add_parser("web", help="Web dashboard")
    w.add_argument("--host", default="0.0.0.0")
    w.add_argument("--port", type=int, default=5000)

    args = p.parse_args()

    dispatch = {
        None: cmd_run, "run": cmd_run,
        "list": cmd_list, "remove": cmd_remove,
        "guests": cmd_guests, "export": cmd_export,
        "web": cmd_web,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
