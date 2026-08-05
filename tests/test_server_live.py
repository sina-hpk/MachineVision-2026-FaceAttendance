"""
Live server test — starts uvicorn and tests endpoints (no Redis dependency).
Run with: python tests/test_server_live.py
"""
import os, sys, time, subprocess, requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ["DATABASE_URL"] = "sqlite:///data/test_cv_attendance.db"
os.environ["CAMERA_ENABLED"] = "false"
os.environ["CAMERA_INDEX"] = "-1"
os.environ["METRICS_ENABLED"] = "false"
os.environ["REDIS_URL"] = "redis://localhost:6379/1"
os.environ["LOG_LEVEL"] = "ERROR"

from models.base import init_db, Base, engine
init_db()
for table in reversed(Base.metadata.sorted_tables):
    with engine.begin() as conn:
        conn.execute(table.delete())

PORT = 9891
proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "main_fastapi:app",
     "--host", "127.0.0.1", "--port", str(PORT)],
    cwd=Path(__file__).parent.parent,
    env=os.environ,
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)

try:
    # Wait for server
    for i in range(15):
        try:
            r = requests.get(f"http://127.0.0.1:{PORT}/healthz", timeout=5)
            if r.status_code == 200:
                print(f"[OK] Server started")
                break
        except Exception:
            time.sleep(1)
    else:
        raise RuntimeError("Server failed to start")

    tests = [
        # (name, method, path, expected_status, json_body or None)
        ("healthz",        "GET",    "/healthz",           200),
        ("metrics",        "GET",    "/metrics",           404),  # Returns 404 when disabled
        ("dashboard HTML", "GET",    "/",                  200),
        ("dashboard API",  "GET",    "/api/dashboard",     200),
        ("attendance rpt", "GET",    "/api/attendance/report", 200),
        ("camera status",  "GET",    "/camera/status",     200),
        ("cam toggle off", "POST",  "/api/camera/toggle",  200, {"enabled": False}),
        ("cam toggle on",  "POST",  "/api/camera/toggle",  200, {"enabled": True}),
        ("swagger",        "GET",    "/docs",              200),
        ("redoc",          "GET",    "/redoc",             200),
        ("del W999",       "DELETE", "/api/workers/W999",  404),
        ("workers noauth", "GET",    "/workers",           401),
        ("auth/me noauth", "GET",    "/auth/me",           401),
        ("login bad",      "POST",  "/auth/login",         401, {"username":"x","password":"x"}),
        ("capture wkr",    "POST",  "/api/workers/capture",(200,400,503)),
    ]

    passed = 0
    failed = 0
    for test in tests:
        name, method, path, expected = test[0], test[1], test[2], test[3]
        body = test[4] if len(test) > 4 else None
        kwargs = {"timeout": 30}
        if body is not None:
            kwargs["json"] = body

        try:
            resp = requests.request(method, f"http://127.0.0.1:{PORT}{path}", **kwargs)
            ok = resp.status_code == expected if isinstance(expected, int) else resp.status_code in expected
            status = "PASS" if ok else f"FAIL(got={resp.status_code}, exp={expected})"
            if ok: passed += 1
            else: failed += 1
            print(f"  [{status}] {name}")
        except Exception as e:
            failed += 1
            print(f"  [ERROR] {name} -> {e}")

    print(f"\n{'='*40}")
    print(f"Result: {passed} passed, {failed} failed out of {len(tests)}")
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
