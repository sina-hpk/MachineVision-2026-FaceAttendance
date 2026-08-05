"""
Integration tests for FastAPI endpoints.
Starts uvicorn server in a subprocess, tests with requests.
"""
import os
import sys
import time
import pytest
import requests
import subprocess
import signal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

TEST_PORT = 9877
BASE_URL = f"http://127.0.0.1:{TEST_PORT}"
# Matches the admin_username/admin_password defaults in config.py.
ADMIN = ("admin", "admin")


@pytest.fixture(scope="module")
def server():
    """Start FastAPI server as subprocess."""
    env = os.environ.copy()
    env.update({
        "DATABASE_URL": "sqlite:///data/test_cv_attendance.db",
        "CAMERA_ENABLED": "false",
        "CAMERA_INDEX": "-1",
        "METRICS_ENABLED": "true",
        "REDIS_URL": "redis://localhost:6379/1",
        "LOG_LEVEL": "ERROR",
    })

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main_fastapi:app",
         "--host", "127.0.0.1", "--port", str(TEST_PORT),
         "--log-level", "error"],
        cwd=Path(__file__).parent.parent,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait for server to be ready
    for _ in range(30):
        try:
            r = requests.get(f"{BASE_URL}/healthz", timeout=1)
            if r.status_code == 200:
                break
        except requests.ConnectionError:
            time.sleep(0.5)
        except Exception:
            time.sleep(0.5)
    else:
        proc.kill()
        proc.wait()
        pytest.fail("Server failed to start")

    yield

    # Cleanup
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


# ── Health ──

class TestHealth:
    def test_healthz(self, server):
        r = requests.get(f"{BASE_URL}/healthz", timeout=5)
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

    def test_readyz(self, server):
        r = requests.get(f"{BASE_URL}/readyz", timeout=5)
        assert r.status_code == 200
        assert r.json()["status"] == "ready"

    def test_metrics(self, server):
        r = requests.get(f"{BASE_URL}/metrics", timeout=5)
        assert r.status_code == 200


# ── Dashboard ──

class TestDashboard:
    def test_dashboard_html(self, server):
        r = requests.get(f"{BASE_URL}/", timeout=5)
        assert r.status_code == 200

    def test_dashboard_api(self, server):
        r = requests.get(f"{BASE_URL}/api/dashboard", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "workers" in data
        assert "guests" in data
        assert "events_today" in data
        assert "currently_in" in data

    def test_attendance_report(self, server):
        r = requests.get(f"{BASE_URL}/api/attendance/report", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "workers" in data


# ── Worker ──

class TestWorkerAPI:
    def test_capture_worker_no_camera(self, server):
        r = requests.post(f"{BASE_URL}/api/workers/capture", timeout=5)
        assert r.status_code in (200, 400, 503)

    def test_remove_nonexistent(self, server):
        r = requests.delete(f"{BASE_URL}/api/workers/W999", timeout=5)
        assert r.status_code == 404

    def test_promote_unknown_no_guest(self, server):
        r = requests.post(f"{BASE_URL}/api/unknown/promote", json={"name": "X"}, timeout=5)
        assert r.status_code in (200, 400, 404)


# ── Auth ──

class TestAuthAPI:
    def test_login_fails_wrong_creds(self, server):
        r = requests.post(f"{BASE_URL}/auth/login", json={"username": "bad", "password": "bad"}, timeout=5)
        assert r.status_code == 401

    def test_auth_me_unauthorized(self, server):
        r = requests.get(f"{BASE_URL}/auth/me", timeout=5)
        assert r.status_code == 401

    def test_workers_auth_protected(self, server):
        r = requests.get(f"{BASE_URL}/workers", timeout=5)
        assert r.status_code == 401


# ── Admin panel (HTTP Basic) ──

class TestAdminPanelAuth:
    def test_admin_page_requires_auth(self, server):
        r = requests.get(f"{BASE_URL}/admin", timeout=5)
        assert r.status_code == 401
        # WWW-Authenticate must survive the custom JSON exception handler,
        # otherwise the browser never shows the Basic Auth dialog.
        assert r.headers.get("WWW-Authenticate") == "Basic"

    def test_admin_workers_requires_auth(self, server):
        r = requests.get(f"{BASE_URL}/api/admin/workers", timeout=5)
        assert r.status_code == 401

    def test_admin_rejects_wrong_password(self, server):
        r = requests.get(f"{BASE_URL}/api/admin/workers", auth=("admin", "wrong"), timeout=5)
        assert r.status_code == 401

    def test_admin_accepts_valid_credentials(self, server):
        r = requests.get(f"{BASE_URL}/api/admin/workers", auth=("admin", "admin"), timeout=5)
        assert r.status_code == 200
        assert "worker_count" in r.json()

    def test_delete_sample_requires_auth(self, server):
        r = requests.delete(f"{BASE_URL}/api/admin/workers/W001/samples/1", timeout=5)
        assert r.status_code == 401

    def test_delete_worker_requires_auth(self, server):
        r = requests.delete(f"{BASE_URL}/api/admin/workers/W001", timeout=5)
        assert r.status_code == 401

    def test_sample_image_requires_auth(self, server):
        r = requests.get(f"{BASE_URL}/api/admin/samples/W001/1", timeout=5)
        assert r.status_code == 401

    def test_upload_sample_requires_auth(self, server):
        r = requests.post(
            f"{BASE_URL}/api/admin/workers/W001/samples/upload",
            files={"file": ("a.jpg", b"x", "image/jpeg")},
            timeout=5,
        )
        assert r.status_code == 401


class TestAdminSampleImages:
    """Sample-image routes reject malformed ids and unreadable uploads."""

    def test_sample_image_rejects_bad_worker_id(self, server):
        r = requests.get(
            f"{BASE_URL}/api/admin/samples/..%2F..%2Fetc/1", auth=ADMIN, timeout=5
        )
        assert r.status_code in (400, 404)

    def test_sample_image_rejects_non_numeric_sample_id(self, server):
        r = requests.get(
            f"{BASE_URL}/api/admin/samples/W001/..%2F..%2Fpasswd", auth=ADMIN, timeout=5
        )
        assert r.status_code in (400, 404)

    def test_missing_sample_image_is_404(self, server):
        missing = "00000000-0000-0000-0000-000000000000"
        r = requests.get(f"{BASE_URL}/api/admin/samples/W001/{missing}", auth=ADMIN, timeout=5)
        assert r.status_code == 404

    def test_upload_rejects_non_image(self, server):
        r = requests.post(
            f"{BASE_URL}/api/admin/workers/W001/samples/upload",
            files={"file": ("notes.txt", b"this is not an image", "text/plain")},
            auth=ADMIN,
            timeout=10,
        )
        assert r.status_code == 400

    def test_delete_unknown_worker_is_404(self, server):
        r = requests.delete(f"{BASE_URL}/api/admin/workers/W999", auth=ADMIN, timeout=5)
        assert r.status_code == 404


# ── Camera ──

class TestCameraAPI:
    def test_camera_status(self, server):
        r = requests.get(f"{BASE_URL}/camera/status", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "enabled" in data

    def test_camera_toggle_off(self, server):
        r = requests.post(f"{BASE_URL}/api/camera/toggle", json={"enabled": False}, timeout=5)
        assert r.status_code == 200
        assert r.json()["enabled"] is False

    def test_camera_toggle_on(self, server):
        r = requests.post(f"{BASE_URL}/api/camera/toggle", json={"enabled": True}, timeout=5)
        assert r.status_code == 200
        assert r.json()["enabled"] is True


# ── Frontend ──

class TestFrontend:
    def test_swagger_ui(self, server):
        r = requests.get(f"{BASE_URL}/docs", timeout=5)
        assert r.status_code == 200

    def test_redoc(self, server):
        r = requests.get(f"{BASE_URL}/redoc", timeout=5)
        assert r.status_code == 200
