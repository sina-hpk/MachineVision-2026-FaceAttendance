"""
main_fastapi.py — Unified FastAPI Application (merged from web_dashboard.py + main_fastapi.py)
Main entry point for the CV Attendance System API
"""
from contextlib import asynccontextmanager
from fastapi import (
    FastAPI, Depends, HTTPException, status, Request, WebSocket, WebSocketDisconnect,
    UploadFile, File,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse, HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.openapi.utils import get_openapi
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from typing import List, Optional
from datetime import datetime, timedelta
import threading
import time
import csv
import re
import secrets
from io import StringIO
from pathlib import Path
from collections import defaultdict

import cv2
import face_recognition
import numpy as np

from models import (
    SessionLocal, get_db, init_db,
)
from models.worker import Worker as WorkerModel, FaceEncoding as FaceEncodingModel
from models.guest import Guest as GuestModel
from models.attendance import (
    AttendanceEvent as AttendanceEventModel,
    FaceSighting as FaceSightingModel,
)
from models.user import User as UserModel
from auth import (
    Role, Permission, TokenData,
    verify_password, get_password_hash,
    create_access_token, create_refresh_token, decode_token,
    create_tokens, refresh_access_token, has_permission,
)
from auth_fastapi import (
    require_permission, require_role,
    get_current_user, get_current_active_user, security,
)
from config import settings
from attendance import AttendanceTracker
from models.repository import FaceRepository, DuplicateNameError
from face_recognizer import FaceRecognizer
from registration import start_session, abort_session, get_session, draw_registration_overlay, update_session, _reg_lock
from academic import get_suite_data, get_benchmark
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
import logging
from redis_client import redis_client, rate_limit
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel, EmailStr, Field

templates = Jinja2Templates(directory="templates")


# ═══════════════════════════════════════════════════════════════════
# Pydantic Schemas
# ═══════════════════════════════════════════════════════════════════

class WorkerCreate(BaseModel):
    worker_id: str = Field(..., pattern=r"^W\d{3}$")
    name: str = Field(..., min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    department: Optional[str] = None
    position: Optional[str] = None


class WorkerUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    department: Optional[str] = None
    position: Optional[str] = None
    is_active: Optional[bool] = None


class WorkerResponse(BaseModel):
    id: str
    worker_id: str
    name: str
    email: Optional[str]
    department: Optional[str]
    position: Optional[str]
    is_active: bool
    registered_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FaceEncodingResponse(BaseModel):
    id: str
    worker_id: str
    encoding: List[float]
    quality_score: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class GuestResponse(BaseModel):
    id: str
    guest_id: str
    encodings: List[List[float]]
    registered_at: datetime
    last_seen: datetime
    promoted: bool
    promoted_to_worker_id: Optional[str]

    class Config:
        from_attributes = True


class AttendanceEventCreate(BaseModel):
    worker_id: str
    event_type: str = Field(..., pattern="^(in|out)$")
    quality_score: Optional[str] = None
    confidence: Optional[str] = None
    device_info: Optional[str] = None


class AttendanceEventResponse(BaseModel):
    id: str
    worker_id: str
    event_type: str
    event_time: datetime
    event_date: datetime
    quality_score: Optional[str]
    confidence: Optional[str]
    device_info: Optional[str]

    class Config:
        from_attributes = True


class AttendanceReportRow(BaseModel):
    worker_id: str
    name: str
    first_in: Optional[str]
    last_out: Optional[str]
    total_hours: float
    num_switches: int


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenRefresh(BaseModel):
    refresh_token: str


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    password: str = Field(..., min_length=8)
    role: Role = Role.VIEWER


class UserResponse(BaseModel):
    id: str
    username: str
    email: Optional[str]
    full_name: Optional[str]
    role: Role
    is_active: bool
    last_login: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    username: str
    password: str


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    camera: bool
    database: bool
    redis: bool
    version: str


class CameraToggleRequest(BaseModel):
    enabled: bool


class PromoteRequest(BaseModel):
    name: str = Field(..., min_length=1)


class CaptureResponse(BaseModel):
    id: str
    name: str
    samples: int
    message: str


# ═══════════════════════════════════════════════════════════════════
# Prometheus Metrics
# ═══════════════════════════════════════════════════════════════════

if settings.metrics_enabled:
    HTTP_REQUESTS_TOTAL = Counter(
        "http_requests_total",
        "Total HTTP requests",
        ["method", "endpoint", "status"],
    )
    HTTP_REQUEST_DURATION = Histogram(
        "http_request_duration_seconds",
        "HTTP request latency in seconds",
        ["method", "endpoint"],
        buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    )
    CAMERA_FRAMES_TOTAL = Counter(
        "camera_frames_total",
        "Total frames processed by camera loop",
        ["status"],  # success, error, skipped
    )
    RECOGNITION_TOTAL = Counter(
        "recognition_total",
        "Total face recognitions",
        ["result"],  # known, unknown, error
    )
    ATTENDANCE_EVENTS_TOTAL = Counter(
        "attendance_events_total",
        "Total attendance events",
        ["type"],  # in, out, unknown
    )
    CAMERA_ACTIVE = Gauge(
        "camera_active",
        "Whether camera is active (1) or not (0)",
    )
    WORKERS_COUNT = Gauge(
        "workers_count",
        "Number of registered workers",
    )
    GUESTS_COUNT = Gauge(
        "guests_count",
        "Number of registered guests",
    )
    CURRENTLY_IN = Gauge(
        "currently_in",
        "Number of workers currently checked in",
    )
else:
    class _Dummy:
        def labels(self, *args, **kwargs):
            return self
        def inc(self, *args, **kwargs):
            pass
        def observe(self, *args, **kwargs):
            pass
        def set(self, *args, **kwargs):
            pass
    HTTP_REQUESTS_TOTAL = HTTP_REQUEST_DURATION = CAMERA_FRAMES_TOTAL = RECOGNITION_TOTAL = ATTENDANCE_EVENTS_TOTAL = CAMERA_ACTIVE = WORKERS_COUNT = GUESTS_COUNT = CURRENTLY_IN = _Dummy()


# ═══════════════════════════════════════════════════════════════════
# Core Components
# ═══════════════════════════════════════════════════════════════════

db = FaceRepository(faces_dir=settings.faces_dir)
init_db()  # Ensure database tables exist before any query
attendance = AttendanceTracker(data_dir=settings.attendance_dir)
recognizer = FaceRecognizer(
    db=db,
    tolerance=settings.tolerance,
    process_scale=settings.process_scale,
    augment_min_distance=settings.augment_min_distance,
    max_encodings=settings.max_encodings,
    augment_cooldown=timedelta(minutes=settings.augment_cooldown_minutes),
    prefer_insightface=settings.prefer_insightface,
    insightface_det_size=settings.insightface_det_size,
    enable_quality_gate=False,
)
logging.getLogger("main").info("Recognition engine: %s", recognizer.engine_name)


# ═══════════════════════════════════════════════════════════════════
# Shared State (Thread-Safe)
# ═══════════════════════════════════════════════════════════════════

cam_lock = threading.Lock()
frame: Optional[np.ndarray] = None
raw_frame: Optional[np.ndarray] = None
frame_seq = 0

recognition_lock = threading.Lock()  # Serialize InsightFace access across threads

log = logging.getLogger("cv_attendance")

cooldowns: dict[str, datetime] = {}
event: Optional[dict] = None
event_seq = 0
event_lock = threading.Lock()

guest_id: Optional[str] = None
guest_lock = threading.Lock()
guest_captured_at: float = 0

camera_enabled = settings.camera_enabled
camera_error: Optional[str] = None  # Last camera error, reset on toggle
camera_lock = threading.Lock()  # Protect camera_enabled and camera_error

shutdown_event = threading.Event()


# ═══════════════════════════════════════════════════════════════════
# Camera Loop (Background Thread, non-blocking via asyncio)
# ═══════════════════════════════════════════════════════════════════

def camera_loop(cam_index: int) -> None:
    """Camera loop: read frames, run recognition, drive attendance + registration."""
    global frame, raw_frame, frame_seq, camera_error

    if not recognizer.open(cam_index):
        camera_error = f"Failed to open camera at index {cam_index}"
        CAMERA_ACTIVE.set(0)
        return

    camera_error = None
    CAMERA_ACTIVE.set(1)

    while not shutdown_event.is_set():
        try:
            if not camera_enabled:
                time.sleep(0.5)
                continue

            raw = recognizer.read()
            if raw is None:
                time.sleep(0.016)
                continue

            CAMERA_FRAMES_TOTAL.labels(status="ok").inc()

            with recognition_lock:
                results = recognizer.recognize(raw)

            # Annotated frame for the MJPEG stream
            display = raw.copy()
            if results:
                recognizer.draw_boxes(display, results)

            with cam_lock:
                frame = display
                raw_frame = raw
                frame_seq += 1

            sess = get_session()
            if sess is not None and sess.is_active and not sess.is_done:
                # Registration mode: collect samples, don't toggle attendance
                best = _best_face(results)
                if best is None:
                    update_session()
                else:
                    update_session(best[0], _crop_face(raw, best[1]))
            elif results:
                _process_results(results)

            # Yield the GIL so HTTP handlers stay responsive while recognition
            # runs continuously.
            time.sleep(0.01)

        except Exception as exc:
            camera_error = f"Camera error: {exc}"
            log.exception("camera loop error")
            CAMERA_FRAMES_TOTAL.labels(status="error").inc()
            time.sleep(3)

    recognizer.close()
    CAMERA_ACTIVE.set(0)


def _best_face(results: list[dict]) -> Optional[tuple[np.ndarray, tuple[int, int, int, int]]]:
    """Pick the largest detected face with a usable encoding."""
    best = None
    best_area = 0
    for r in results:
        enc = r.get("encoding")
        if enc is None or getattr(enc, "size", 0) == 0:
            continue
        l, t, rt, b = (int(v) for v in r["bbox"])
        area = max(0, rt - l) * max(0, b - t)
        if area > best_area:
            best_area = area
            best = (enc, (l, t, rt, b))
    return best


def _crop_face(image: np.ndarray, bbox: tuple[int, int, int, int]) -> Optional[np.ndarray]:
    """Crop bbox from image, clamped to bounds."""
    l, t, r, b = bbox
    h, w = image.shape[:2]
    l, t = max(0, l), max(0, t)
    r, b = min(w, r), min(h, b)
    if r <= l or b <= t:
        return None
    return image[t:b, l:r].copy()


def _set_event(data: dict) -> None:
    """Publish an event to the dashboard (REST snapshot + WebSocket push)."""
    global event, event_seq
    with event_lock:
        event = data
        event_seq += 1
    broadcast_event(data)


def _process_results(results: list[dict]) -> None:
    """Process recognition results: attendance, guests, events."""
    global guest_id, guest_captured_at

    now = datetime.now()
    unknown_enc = None
    unknown_crop = None
    saw_known = False

    for r in results:
        pid = r["person_id"]

        # Unknown face
        if pid is None:
            enc = r.get("encoding")
            if unknown_enc is None and enc is not None and enc.size > 0:
                unknown_enc = enc
                unknown_crop = r.get("aligned_face")
            continue

        # Known face but no name in DB
        if r["name"] is None:
            continue

        saw_known = True

        # Guests are recognized (so they aren't re-registered) but have no
        # attendance record until an operator promotes them to a worker.
        if not pid.startswith("W"):
            continue

        # Cooldown check
        if now - cooldowns.get(pid, datetime.min) < timedelta(seconds=settings.cooldown_seconds):
            continue

        # Record presence: first sighting of the day is clock-in, every later
        # sighting extends last_seen (clock-out = last time seen).
        if not attendance.record_sighting(pid, r["name"], now):
            continue
        cooldowns[pid] = now

        _set_event({
            "type": "in",
            "label": "IN",
            "name": r["name"],
            "id": pid,
            "time": now.strftime("%H:%M:%S"),
        })

        ATTENDANCE_EVENTS_TOTAL.labels(type="in").inc()

    if saw_known:
        RECOGNITION_TOTAL.labels(result="known").inc()

    # Handle unknown face (guest registration)
    if unknown_enc is not None and time.time() - guest_captured_at > settings.guest_capture_interval:
        gid = db.add_guest([unknown_enc], face_image=unknown_crop)
        guest_captured_at = time.time()
        with guest_lock:
            guest_id = gid
        _set_event({
            "type": "unknown",
            "label": "NEW FACE",
            "name": gid,
            "time": datetime.now().strftime("%H:%M:%S"),
        })
        GUESTS_COUNT.set(db.guest_count())
        RECOGNITION_TOTAL.labels(result="unknown").inc()
        recognizer.invalidate_cache()


# ═══════════════════════════════════════════════════════════════════
# MJPEG Video Stream
# ═══════════════════════════════════════════════════════════════════

def _mjpeg_generator():
    """Generate MJPEG stream frames — non-blocking, always yields latest."""
    last_seq = -1
    while not shutdown_event.is_set():
        with cam_lock:
            if frame is not None and frame_seq != last_seq:
                display = frame.copy()
                # Apply registration overlay if session is active
                sess = get_session()
                if sess and sess.is_active:
                    display = draw_registration_overlay(display)
                _, buf = cv2.imencode(".jpg", display, [cv2.IMWRITE_JPEG_QUALITY, 85])
                data = buf.tobytes()
                last_seq = frame_seq
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + data + b"\r\n"
                continue
        # No new frame — yield nothing and wait shortly
        time.sleep(0.05)


# ── Placeholder frame (no longer needed — MJPEG generator handles empty state)



# ═══════════════════════════════════════════════════════════════════
# Lifespan
# ═══════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global _ws_loop
    _ws_loop = asyncio.get_running_loop()
    init_db()

    # Set initial metrics
    try:
        WORKERS_COUNT.set(db.worker_count())
        GUESTS_COUNT.set(db.guest_count())
        CURRENTLY_IN.set(attendance.count_in())
    except Exception:
        pass  # DB might not be ready

    # Auto-start camera thread if camera is enabled
    if settings.camera_enabled:
        _ensure_camera_thread()

    # Start camera watchdog
    global _watchdog_thread
    _watchdog_thread = threading.Thread(target=_camera_watchdog, daemon=True)
    _watchdog_thread.start()

    yield

    # Shutdown
    shutdown_event.set()


# ═══════════════════════════════════════════════════════════════════
# FastAPI App
# ═══════════════════════════════════════════════════════════════════

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
    **CV Attendance System** - Face Recognition based Attendance Management

    ## Features
    - **Face Recognition**: Real-time face detection and recognition
    - **Attendance Tracking**: Automatic check-in/check-out with cooldown
    - **Worker Management**: Register, update, delete workers with face encodings
    - **Guest Registration**: Capture unknown faces for later promotion
    - **Reports**: Daily attendance reports with hours calculation
    - **Security**: JWT authentication with RBAC
    - **Monitoring**: Prometheus metrics, health checks

    ## Authentication
    Most endpoints require authentication. Use the `/auth/login` endpoint to obtain tokens.

    ## Rate Limiting
    API endpoints are rate-limited (default: 100 req/min). Check `X-RateLimit-*` headers.
    """,
    docs_url=None,
    redoc_url=None,
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
import os as _os
_static_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "static")
if _os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")


# ═══════════════════════════════════════════════════════════════════
# Middleware: Request Metrics
# ═══════════════════════════════════════════════════════════════════

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    if settings.metrics_enabled:
        HTTP_REQUEST_DURATION.labels(
            method=request.method,
            endpoint=request.url.path,
        ).observe(duration)
        HTTP_REQUESTS_TOTAL.labels(
            method=request.method,
            endpoint=request.url.path,
            status=response.status_code,
        ).inc()
    return response


# ═══════════════════════════════════════════════════════════════════
# Exception Handlers
# ═══════════════════════════════════════════════════════════════════

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    # Keep exc.headers (e.g. WWW-Authenticate for HTTP Basic). Without it the
    # browser never shows the Basic Auth dialog and the admin page looks broken.
    headers = dict(exc.headers or {})
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "status_code": exc.status_code},
        headers=headers,
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Catch-all for unhandled exceptions — return JSON without traceback."""
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "status_code": 500},
    )


# ═══════════════════════════════════════════════════════════════════
# Custom OpenAPI
# ═══════════════════════════════════════════════════════════════════

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=settings.app_name,
        version=settings.app_version,
        description=app.description,
        routes=app.routes,
    )

    # Add security scheme
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
    }

    # Add global security requirement
    openapi_schema["security"] = [{"BearerAuth": []}]

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


# ═══════════════════════════════════════════════════════════════════
# Documentation Endpoints
# ═══════════════════════════════════════════════════════════════════

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{settings.app_name} - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
    )


@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=f"{settings.app_name} - ReDoc",
        redoc_js_url="https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js",
    )


# ═══════════════════════════════════════════════════════════════════
# Health & Monitoring
# ═══════════════════════════════════════════════════════════════════

@app.get("/healthz", response_model=HealthResponse, tags=["Monitoring"])
async def health_check():
    """Liveness probe - is the process alive?"""
    db_ok = True
    try:
        from models.base import SessionLocal
        s = SessionLocal()
        s.execute(func.now())
        s.close()
    except Exception:
        db_ok = False
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat() + "Z",
        camera=recognizer.is_open() if hasattr(recognizer, "is_open") else False,
        database=db_ok,
        redis=redis_client.health_check(),
        version=settings.app_version,
    )


@app.get("/readyz", response_model=HealthResponse, tags=["Monitoring"])
async def readiness_check():
    """Readiness probe - can serve traffic?"""
    db_ok = True
    try:
        from models.base import SessionLocal
        s = SessionLocal()
        s.execute(func.now())
        s.close()
    except Exception:
        db_ok = False
    return HealthResponse(
        status="ready",
        timestamp=datetime.utcnow().isoformat() + "Z",
        camera=recognizer.is_open(),
        database=db_ok,
        redis=redis_client.health_check(),
        version=settings.app_version,
    )


@app.get("/metrics", response_class=Response, tags=["Monitoring"])
async def metrics():
    """Prometheus metrics endpoint."""
    if not settings.metrics_enabled:
        return Response("Metrics disabled", status_code=404)
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ═══════════════════════════════════════════════════════════════════
# Authentication
# ═══════════════════════════════════════════════════════════════════

@app.post("/auth/login", response_model=Token, tags=["Authentication"])
async def login(request: LoginRequest, db_session: Session = Depends(get_db)):
    """Login with username/password, return access + refresh tokens."""
    user = db_session.query(UserModel).filter(UserModel.username == request.username).first()
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    user.last_login = datetime.utcnow()
    db_session.commit()

    return create_tokens(str(user.id), user.username, user.role)


@app.post("/auth/refresh", response_model=Token, tags=["Authentication"])
async def refresh_token(request: TokenRefresh):
    """Refresh access token using refresh token."""
    tokens = refresh_access_token(request.refresh_token)
    if not tokens:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    return tokens


@app.get("/auth/me", response_model=UserResponse, tags=["Authentication"])
async def get_current_user_info(current_user: TokenData = Depends(get_current_active_user)):
    """Get current user info from token."""
    return UserResponse(
        id=current_user.sub,
        username=current_user.username,
        email=None,
        full_name=None,
        role=current_user.role,
        is_active=True,
        last_login=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


# ═══════════════════════════════════════════════════════════════════
# Workers CRUD (Auth-protected, from main_fastapi)
# ═══════════════════════════════════════════════════════════════════

@app.post("/workers", response_model=WorkerResponse, status_code=201, tags=["Workers"])
@rate_limit(limit=20, window=60)
async def create_worker(
    worker: WorkerCreate,
    db_session: Session = Depends(get_db),
    _: TokenData = Depends(require_permission(Permission.WORKER_CREATE)),
):
    """Create a new worker (face encodings added via /workers/{id}/capture)."""
    existing = db_session.query(WorkerModel).filter(WorkerModel.worker_id == worker.worker_id).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Worker ID {worker.worker_id} already exists")

    if worker.email:
        existing = db_session.query(WorkerModel).filter(WorkerModel.email == worker.email).first()
        if existing:
            raise HTTPException(status_code=409, detail=f"Email {worker.email} already registered")

    db_worker = WorkerModel(
        worker_id=worker.worker_id,
        name=worker.name,
        email=worker.email,
        department=worker.department,
        position=worker.position,
        is_active=1,
    )
    db_session.add(db_worker)
    db_session.commit()
    db_session.refresh(db_worker)
    return db_worker


@app.get("/workers", response_model=List[WorkerResponse], tags=["Workers"])
@rate_limit(limit=100, window=60)
async def list_workers(
    skip: int = 0,
    limit: int = 100,
    active_only: bool = True,
    db_session: Session = Depends(get_db),
    _: TokenData = Depends(require_permission(Permission.WORKER_READ)),
):
    """List all workers with pagination."""
    query = db_session.query(WorkerModel)
    if active_only:
        query = query.filter(WorkerModel.is_active == 1)
    workers = query.offset(skip).limit(limit).all()
    return workers


@app.get("/workers/{worker_id}", response_model=WorkerResponse, tags=["Workers"])
async def get_worker(
    worker_id: str,
    db_session: Session = Depends(get_db),
    _: TokenData = Depends(require_permission(Permission.WORKER_READ)),
):
    """Get worker by ID."""
    worker = db_session.query(WorkerModel).filter(WorkerModel.id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    return worker


@app.put("/workers/{worker_id}", response_model=WorkerResponse, tags=["Workers"])
async def update_worker(
    worker_id: str,
    worker_update: WorkerUpdate,
    db_session: Session = Depends(get_db),
    _: TokenData = Depends(require_permission(Permission.WORKER_UPDATE)),
):
    """Update worker details."""
    worker = db_session.query(WorkerModel).filter(WorkerModel.id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    update_data = worker_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(worker, field, 1 if value is True else (0 if value is False else value))
    worker.updated_at = datetime.utcnow()
    db_session.commit()
    db_session.refresh(worker)
    return worker


@app.delete("/workers/{worker_id}", status_code=204, tags=["Workers"])
async def delete_worker(
    worker_id: str,
    db_session: Session = Depends(get_db),
    _: TokenData = Depends(require_permission(Permission.WORKER_DELETE)),
):
    """Delete worker and all associated face encodings."""
    worker = db_session.query(WorkerModel).filter(WorkerModel.id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    db_session.delete(worker)
    db_session.commit()
    return


@app.get("/workers/{worker_id}/encodings", response_model=List[FaceEncodingResponse], tags=["Workers"])
async def get_worker_encodings(
    worker_id: str,
    db_session: Session = Depends(get_db),
    _: TokenData = Depends(require_permission(Permission.WORKER_READ)),
):
    """Get all face encodings for a worker."""
    encodings = db_session.query(FaceEncodingModel).filter(FaceEncodingModel.worker_id == worker_id).all()
    return encodings


@app.post("/workers/{worker_id}/capture", tags=["Workers"])
async def capture_worker_face(
    worker_id: str,
    db_session: Session = Depends(get_db),
    _: TokenData = Depends(require_permission(Permission.WORKER_CREATE)),
):
    """Capture face samples for a worker (requires camera access)."""
    worker = db_session.query(WorkerModel).filter(WorkerModel.id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    return {"message": "Face capture endpoint - implement with camera integration", "worker_id": worker_id}


# ═══════════════════════════════════════════════════════════════════
# Guests CRUD (Auth-protected, from main_fastapi)
# ═══════════════════════════════════════════════════════════════════

@app.get("/guests", response_model=List[GuestResponse], tags=["Guests"])
async def list_guests(
    db_session: Session = Depends(get_db),
    _: TokenData = Depends(require_permission(Permission.WORKER_READ)),
):
    """List all guests (unknown faces)."""
    guests = db_session.query(GuestModel).all()
    return guests


@app.post("/guests/{guest_id}/promote", response_model=WorkerResponse, tags=["Guests"])
async def promote_guest(
    guest_id: str,
    worker_data: WorkerCreate,
    db_session: Session = Depends(get_db),
    _: TokenData = Depends(require_permission(Permission.WORKER_CREATE)),
):
    """Promote a guest to a registered worker."""
    guest = db_session.query(GuestModel).filter(GuestModel.id == guest_id).first()
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")

    db_worker = WorkerModel(
        worker_id=worker_data.worker_id,
        name=worker_data.name,
        email=worker_data.email,
        department=worker_data.department,
        position=worker_data.position,
    )
    db_session.add(db_worker)
    db_session.flush()

    for enc in guest.encodings:
        db_enc = FaceEncodingModel(worker_id=db_worker.id, encoding=enc, quality_score="0.5")
        db_session.add(db_enc)

    guest.promoted = 1
    guest.promoted_to_worker_id = str(db_worker.id)
    db_session.commit()
    db_session.refresh(db_worker)
    return db_worker


@app.delete("/guests/{guest_id}", status_code=204, tags=["Guests"])
async def dismiss_guest(
    guest_id: str,
    db_session: Session = Depends(get_db),
    _: TokenData = Depends(require_permission(Permission.WORKER_DELETE)),
):
    """Dismiss a guest (delete)."""
    guest = db_session.query(GuestModel).filter(GuestModel.id == guest_id).first()
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")
    db_session.delete(guest)
    db_session.commit()


# ═══════════════════════════════════════════════════════════════════
# Attendance (Auth-protected, from main_fastapi)
# ═══════════════════════════════════════════════════════════════════

@app.post("/attendance", response_model=AttendanceEventResponse, status_code=201, tags=["Attendance"])
async def create_attendance_event(
    event: AttendanceEventCreate,
    db_session: Session = Depends(get_db),
    _: TokenData = Depends(require_permission(Permission.ATTENDANCE_READ)),
):
    """Record attendance event (check-in/out)."""
    worker = db_session.query(WorkerModel).filter(WorkerModel.id == event.worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    db_event = AttendanceEventModel(
        worker_id=event.worker_id,
        event_type=event.event_type,
        quality_score=event.quality_score,
        confidence=event.confidence,
        device_info=event.device_info,
    )
    db_session.add(db_event)
    db_session.commit()
    db_session.refresh(db_event)
    return db_event


@app.get("/attendance/report", response_model=List[AttendanceReportRow], tags=["Attendance"])
async def get_attendance_report(
    date: Optional[str] = None,
    db_session: Session = Depends(get_db),
    _: TokenData = Depends(require_permission(Permission.ATTENDANCE_READ)),
):
    """Get daily attendance report with hours calculation (API access)."""
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format, expected YYYY-MM-DD")
    else:
        # Events are recorded with local time, so the report day is local too.
        target_date = datetime.now().date()

    events = db_session.query(FaceSightingModel).filter(
        func.date(FaceSightingModel.event_date) == target_date
    ).order_by(FaceSightingModel.worker_id, FaceSightingModel.first_seen).all()

    worker_events = defaultdict(list)
    for e in events:
        worker_events[str(e.worker_id)].append(e)

    workers = (
        db_session.query(WorkerModel).filter(
            WorkerModel.id.in_(list(worker_events)), WorkerModel.is_active == 1
        ).all() if worker_events else []
    )
    worker_map = {str(w.id): w for w in workers}

    rows = []
    for worker_id, evs in worker_events.items():
        worker = worker_map.get(worker_id)
        if not worker:
            continue

        first_in = min(e.first_seen for e in evs)
        last_out = max(e.last_seen for e in evs)
        total_sec = max(0.0, (last_out - first_in).total_seconds())

        rows.append(AttendanceReportRow(
            worker_id=worker.worker_id,
            name=worker.name,
            first_in=first_in.strftime("%H:%M:%S"),
            last_out=last_out.strftime("%H:%M:%S"),
            total_hours=round(total_sec / 3600, 2),
            num_switches=len(evs),
        ))

    rows.sort(key=lambda r: r.worker_id)
    return rows


@app.get("/attendance/export", tags=["Attendance"])
async def export_attendance_csv(
    date: Optional[str] = None,
    db_session: Session = Depends(get_db),
    _: TokenData = Depends(require_permission(Permission.ATTENDANCE_EXPORT)),
):
    """Export attendance as CSV."""
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format, expected YYYY-MM-DD")
    else:
        target_date = datetime.now().date()

    events = db_session.query(FaceSightingModel).filter(
        func.date(FaceSightingModel.event_date) == target_date
    ).order_by(FaceSightingModel.worker_id, FaceSightingModel.first_seen).all()

    worker_map = {}
    if events:
        ids = {e.worker_id for e in events}
        worker_map = {
            w.id: w for w in
            db_session.query(WorkerModel).filter(WorkerModel.id.in_(ids)).all()
        }

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Worker ID", "Name", "First Seen", "Last Seen", "Hours"])

    for e in events:
        worker = worker_map.get(e.worker_id)
        hours = max(0.0, (e.last_seen - e.first_seen).total_seconds()) / 3600
        writer.writerow([
            worker.worker_id if worker else str(e.worker_id),
            worker.name if worker else "Unknown",
            e.first_seen.strftime("%H:%M:%S"),
            e.last_seen.strftime("%H:%M:%S"),
            round(hours, 2),
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=attendance_{date or 'today'}.csv"},
    )


# ═══════════════════════════════════════════════════════════════════
# Users (Admin only)
# ═══════════════════════════════════════════════════════════════════

@app.post("/users", response_model=UserResponse, status_code=201, tags=["Users"])
async def create_user(
    user: UserCreate,
    db_session: Session = Depends(get_db),
    _: TokenData = Depends(require_role(Role.ADMIN)),
):
    """Create a new system user (admin only)."""
    existing = db_session.query(UserModel).filter(UserModel.username == user.username).first()
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists")

    if user.email:
        existing = db_session.query(UserModel).filter(UserModel.email == user.email).first()
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")

    hashed_pw = get_password_hash(user.password)
    db_user = UserModel(
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        hashed_password=hashed_pw,
        role=user.role,
    )
    db_session.add(db_user)
    db_session.commit()
    db_session.refresh(db_user)
    return db_user


@app.get("/users", response_model=List[UserResponse], tags=["Users"])
async def list_users(
    db_session: Session = Depends(get_db),
    _: TokenData = Depends(require_role(Role.ADMIN)),
):
    """List all system users (admin only)."""
    users = db_session.query(UserModel).all()
    return users


# ═══════════════════════════════════════════════════════════════════
# Dashboard Web Endpoints (from web_dashboard, no auth)
# ═══════════════════════════════════════════════════════════════════

@app.get("/", tags=["Dashboard"])
async def index(request: Request):
    """Render the dashboard HTML."""
    from pathlib import Path
    return HTMLResponse(
        (Path(__file__).parent / "templates" / "dashboard.html").read_text(encoding="utf-8")
    )


@app.get("/video_feed", tags=["Dashboard"])
async def video_feed():
    """MJPEG video stream."""
    return StreamingResponse(
        _mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/api/dashboard", tags=["Dashboard"])
def api_dashboard():
    """JSON dashboard data.

    Declared sync on purpose: every call does blocking DB work, so Starlette
    runs it in the threadpool instead of stalling the event loop (which made the
    browser's 5s fetch timeout abort while the camera thread held the GIL).
    """
    with event_lock:
        e = dict(event) if event else None
    with guest_lock:
        g = guest_id

    workers = db.list_workers()
    guests = db.list_guests()

    return {
        "now": datetime.now().strftime("%H:%M:%S"),
        "workers": [
            {"id": w["id"], "name": w["name"], "status": attendance.get_state(w["id"])}
            for w in workers
        ],
        "worker_count": len(workers),
        "guest_count": len(guests),
        "guests": [
            {"id": g["id"], "registered_at": g["registered_at"]}
            for g in guests
        ],
        "events_today": attendance.count_in(),
        "currently_in": attendance.count_in(),
        "latest_event": e,
        "unknown_guest": g,
        "camera_enabled": camera_enabled,
        "camera_is_open": recognizer.is_open(),
        "camera_error": camera_error,
    }


@app.get("/api/attendance/report", tags=["Dashboard"])
def api_attendance_report():
    """Daily attendance report for dashboard (no auth). Sync — see api_dashboard."""
    today = datetime.now().date()
    db_session = SessionLocal()
    try:
        events = db_session.query(FaceSightingModel).filter(
            func.date(FaceSightingModel.event_date) == today
        ).order_by(FaceSightingModel.worker_id, FaceSightingModel.first_seen).all()

        worker_events = defaultdict(list)
        for e in events:
            worker_events[str(e.worker_id)].append(e)

        worker_ids = list(worker_events)
        workers = (
            db_session.query(WorkerModel)
            .filter(WorkerModel.id.in_(worker_ids), WorkerModel.is_active == 1)
            .all() if worker_ids else []
        )
        worker_map = {str(w.id): w for w in workers}
    finally:
        db_session.close()

    rows = []
    for wid, evs in worker_events.items():
        worker = worker_map.get(wid)
        if worker is None:
            continue
        first_in = min(e.first_seen for e in evs)
        last_out = max(e.last_seen for e in evs)
        sec = max(0.0, (last_out - first_in).total_seconds())

        rows.append({
            "worker_id": worker.worker_id,
            "name": worker.name,
            "first_in": first_in.strftime("%H:%M:%S"),
            "last_out": last_out.strftime("%H:%M:%S"),
            "total_hours": round(sec / 3600, 2),
        })

    rows.sort(key=lambda r: r["worker_id"])
    return {"workers": rows}


@app.post("/api/workers/capture", response_model=CaptureResponse, tags=["Dashboard"])
async def api_capture_worker(request: Request):
    """Register worker by capturing face samples from shared camera."""
    body = await request.json() if request.headers.get("content-type") else {}
    name = (body or {}).get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")

    # Auto-start camera if not running
    global camera_enabled
    was_disabled = False
    if not recognizer.is_open():
        _ensure_camera_thread()
        # Wait for camera to initialize (max 3s)
        for _ in range(15):
            if recognizer.is_open():
                break
            time.sleep(0.2)
        if not recognizer.is_open():
            raise HTTPException(status_code=503, detail="Camera not available (no webcam detected)")
        was_disabled = not camera_enabled
        if was_disabled:
            camera_enabled = True

    try:
        # Get a fresh unannotated frame. The display frame has recognition
        # boxes drawn onto it, which corrupts any encoding taken from it.
        with cam_lock:
            current_frame = raw_frame.copy() if raw_frame is not None else None
        if current_frame is None:
            log.warning("capture: no frame from camera")
            raise HTTPException(status_code=503, detail="No frame from camera yet")

        # Encode through the same pipeline the camera loop uses, so the stored
        # encoding is directly comparable with live ones.
        with recognition_lock:
            results = recognizer.recognize(current_frame)
        if not results:
            raise HTTPException(
                status_code=400,
                detail="No face detected. Look directly at the camera and try again.",
            )

        best = _best_face(results)
        if best is None:
            raise HTTPException(
                status_code=400,
                detail="Could not encode face. Adjust lighting and try again.",
            )

        seed_enc, bbox = best
        face_crop = _crop_face(current_frame, bbox)

        # Save and return
        collected = [seed_enc]
        wid = db.add_worker(
            name, collected, face_image=face_crop, sample_images=[face_crop]
        )
        recognizer.invalidate_cache()
        WORKERS_COUNT.set(db.worker_count())

        if was_disabled:
            camera_enabled = False

        return CaptureResponse(
            id=wid,
            name=name,
            samples=1,
            message=f"Registered {name} successfully!",
        )

    except DuplicateNameError:
        raise HTTPException(status_code=409, detail="Duplicate name")


@app.delete("/api/workers/{wid}", tags=["Dashboard"])
async def api_remove_worker(wid: str):
    """Remove a worker by ID (from web dashboard, no auth)."""
    ok, name = db.remove_worker(wid)
    if ok:
        recognizer.invalidate_cache()
        WORKERS_COUNT.set(db.worker_count())
        return {"message": f"Removed {name}"}
    raise HTTPException(status_code=404, detail="Not found")


@app.post("/api/unknown/promote", tags=["Dashboard"])
async def api_promote(request: Request):
    """Promote an unknown guest to a registered worker."""
    global guest_id, event
    body = await request.json() if request.headers.get("content-type") else {}
    name = (body or {}).get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")

    with guest_lock:
        gid = guest_id

    if not gid:
        raise HTTPException(status_code=400, detail="No unknown face available")

    try:
        wid = db.promote_guest_to_worker(gid, name)
        with guest_lock:
            guest_id = None
        with event_lock:
            event = None
        recognizer.invalidate_cache()
        WORKERS_COUNT.set(db.worker_count())
        GUESTS_COUNT.set(db.guest_count())
        return {"id": wid, "name": name, "message": f"Registered {name}"}
    except DuplicateNameError:
        raise HTTPException(status_code=409, detail="Duplicate name")


@app.post("/api/unknown/dismiss", tags=["Dashboard"])
async def api_dismiss():
    """Dismiss the current unknown guest."""
    global guest_id, event
    with guest_lock:
        guest_id = None
    with event_lock:
        event = None
    return {"message": "Dismissed"}


# ═══════════════════════════════════════════════════════════════════
# Registration Endpoints (Photo-based, 6 angles)
# ═══════════════════════════════════════════════════════════════════

@app.post("/api/registration/start", tags=["Registration"])
async def api_registration_start(request: Request):
    """Start a registration session. The user will be guided through 6 poses."""
    body = await request.json() if request.headers.get("content-type") else {}
    name = (body or {}).get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    
    # Check for duplicate
    try:
        db_workers = db.list_workers()
        for w in db_workers:
            if w["name"].lower() == name.lower():
                raise HTTPException(status_code=409, detail=f"Worker '{name}' already exists")
    except HTTPException:
        raise
    except Exception:
        pass

    ok = start_session(name)
    if not ok:
        raise HTTPException(status_code=409, detail="A registration session is already in progress")
    
    return {"message": f"Registration started for {name}", "name": name, "total_steps": 6}


@app.get("/api/registration/status", tags=["Registration"])
async def api_registration_status():
    """Get current registration session status."""
    sess = get_session()
    if sess is None:
        return {"active": False, "message": "No active session"}
    
    return {
        "active": sess.is_active,
        "name": sess.name,
        "step": sess.step_index + 1 if not sess.is_done else 6,
        "total_steps": 6,
        "progress": round(sess.progress * 100),
        "current_pose": sess.current_guide if not sess.is_done else "done",
        "is_done": sess.is_done,
        "encodings_collected": len(sess.encodings),
        "result_message": sess.result_message,
    }


@app.post("/api/registration/abort", tags=["Registration"])
async def api_registration_abort():
    """Abort the current registration session."""
    abort_session()
    return {"message": "Registration aborted"}


@app.post("/api/registration/commit", tags=["Registration"])
async def api_registration_commit():
    """Commit the registration: save encodings to DB."""
    sess = get_session()
    if sess is None or not sess.is_done or not sess.encodings:
        raise HTTPException(status_code=400, detail="No completed registration to commit")
    
    try:
        wid = db.add_worker(
            sess.name,
            sess.encodings,
            face_image=sess.face_crops[0] if sess.face_crops else None,
            # One crop per pose, so the admin panel can show which view each
            # embedding came from.
            sample_images=sess.face_crops,
        )
        abort_session()
        recognizer.invalidate_cache()
        WORKERS_COUNT.set(db.worker_count())
        return {"id": wid, "name": sess.name, "samples": len(sess.encodings)}
    except DuplicateNameError:
        abort_session()
        raise HTTPException(status_code=409, detail="Duplicate name")
    except Exception as e:
        abort_session()
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════
# Academic / Benchmark Endpoints
# ═══════════════════════════════════════════════════════════════════

@app.get("/academic", tags=["Academic"])
async def academic_page():
    """Render the academic benchmark dashboard."""
    from pathlib import Path
    return HTMLResponse(
        (Path(__file__).parent / "templates" / "academic.html").read_text(encoding="utf-8")
    )


@app.get("/api/academic/benchmark", tags=["Academic"])
async def api_academic_benchmark():
    """Get benchmark comparison data (InsightFace vs dlib)."""
    return get_suite_data()


@app.get("/api/academic/latency", tags=["Academic"])
async def api_academic_latency():
    """Measure model latency in real-time."""
    from academic import SystemBenchmark
    bm = get_benchmark()
    results = {
        "insightface_arcface": bm.measure_latency("InsightFace (ArcFace)"),
        "dlib_resnet": bm.measure_latency("dlib (ResNet)"),
        "dlib_hog": bm.measure_latency("dlib (HOG)"),
    }
    return results


# ── Lazy Camera Thread ──

_camera_thread: Optional[threading.Thread] = None


def _ensure_camera_thread():
    global _camera_thread
    idx = settings.camera_index
    if idx < 0:
        # No camera index configured — try default webcam (index 0)
        idx = 0
    if _camera_thread is None or not _camera_thread.is_alive():
        t = threading.Thread(target=camera_loop, args=(idx,), daemon=True)
        t.start()
        _camera_thread = t


# Camera Watchdog: check every 30 seconds if camera loop is alive
def _camera_watchdog():
    """Background thread that restarts the camera loop if it dies."""
    global camera_error
    while not shutdown_event.wait(30):
        if camera_enabled and (_camera_thread is None or not _camera_thread.is_alive()):
            camera_error = "Camera loop died, restarting..."
            log.warning("watchdog: camera loop not alive, restarting")
            _ensure_camera_thread()


# Start watchdog in lifespan
_watchdog_thread: Optional[threading.Thread] = None


# ═══════════════════════════════════════════════════════════════════
# ADMIN PANEL (HTTP Basic — the panel can delete samples and promote guests)
# ═══════════════════════════════════════════════════════════════════

_basic = HTTPBasic(auto_error=False)


def require_admin(creds: Optional[HTTPBasicCredentials] = Depends(_basic)) -> str:
    """Gate the admin panel behind HTTP Basic.

    Basic (not JWT) is deliberate: the panel is a plain HTML page with no login
    form, and the browser replays the credentials on every /api/admin/* fetch
    from the same origin. `compare_digest` keeps the check constant-time.
    """
    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin credentials required",
            headers={"WWW-Authenticate": "Basic"},
        )
    user_ok = secrets.compare_digest(creds.username, settings.admin_username)
    pass_ok = secrets.compare_digest(creds.password, settings.admin_password)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return creds.username


@app.get("/admin", tags=["Admin"])
async def admin_page(_: str = Depends(require_admin)):
    """Render the admin HTML page."""
    from pathlib import Path
    return HTMLResponse(
        (Path(__file__).parent / "templates" / "admin.html").read_text(encoding="utf-8")
    )


@app.get("/api/admin/workers", tags=["Admin"])
def api_admin_workers(_: str = Depends(require_admin)):
    """Registered workers with their face samples. Sync — see api_dashboard."""
    workers = db.list_workers_detailed()
    states = attendance.get_all_states()
    for w in workers:
        w["status"] = states.get(w["id"], "out")
    return {
        "worker_count": len(workers),
        "sample_total": sum(w["sample_count"] for w in workers),
        "workers": workers,
        "guests": db.list_guests(),
    }


@app.get("/api/admin/face/{identifier}", tags=["Admin"])
def api_admin_face(identifier: str, _: str = Depends(require_admin)):
    """Serve a stored face image for a worker or guest."""
    # Reject path traversal: identifiers are generated as W001 / guest_001.
    if not re.fullmatch(r"(W\d{3,}|guest_\d{3,})", identifier):
        raise HTTPException(status_code=400, detail="Invalid identifier")

    path = Path(settings.faces_dir) / f"{identifier}.jpg"
    if not path.exists():
        raise HTTPException(status_code=404, detail="No image stored")
    return Response(content=path.read_bytes(), media_type="image/jpeg")


@app.get("/api/admin/samples/{wid}/{sid}", tags=["Admin"])
def api_admin_sample_image(wid: str, sid: str, _: str = Depends(require_admin)):
    """Serve the face crop a single embedding was built from.

    Lets an operator see *what the model actually stored* — a blurry or
    mis-cropped sample explains a bad match far faster than reading numbers.
    """
    # Sample ids are UUIDs (FaceEncoding.id), so only hex and dashes.
    if not re.fullmatch(r"W\d{3,}", wid) or not re.fullmatch(r"[0-9a-fA-F-]{8,36}", sid):
        raise HTTPException(status_code=400, detail="Invalid identifier")

    path = db.sample_image_path(wid, sid)
    if not path.exists():
        raise HTTPException(status_code=404, detail="No image stored for this sample")
    return Response(content=path.read_bytes(), media_type="image/jpeg")


@app.post("/api/admin/workers/{wid}/samples", tags=["Admin"])
def api_admin_add_sample(wid: str, _: str = Depends(require_admin)):
    """Capture one extra face sample for an existing worker (live camera)."""
    if not recognizer.is_open():
        raise HTTPException(status_code=503, detail="Camera is not running")

    with cam_lock:
        current = raw_frame.copy() if raw_frame is not None else None
    if current is None:
        raise HTTPException(status_code=503, detail="No frame from camera yet")

    with recognition_lock:
        results = recognizer.recognize(current)
    best = _best_face(results)
    if best is None:
        raise HTTPException(
            status_code=400,
            detail="No usable face detected. Look at the camera and try again.",
        )

    encoding, bbox = best
    if not db.add_encoding_to_worker(
        wid, encoding, sample_image=_crop_face(current, bbox)
    ):
        raise HTTPException(
            status_code=400,
            detail="Could not add sample (worker not found or sample limit reached)",
        )
    recognizer.invalidate_cache()
    return {"ok": True, "message": "Sample added"}


@app.post("/api/admin/workers/{wid}/samples/upload", tags=["Admin"])
async def api_admin_upload_sample(
    wid: str, file: UploadFile = File(...), _: str = Depends(require_admin)
):
    """Add a face sample from an uploaded photo instead of the live camera.

    Useful when someone is absent, or to feed a specific hard case (glasses,
    poor light) into the gallery on purpose.
    """
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image larger than 10MB")

    image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="Not a readable image file")

    with recognition_lock:
        results = recognizer.recognize(image)
    best = _best_face(results)
    if best is None:
        raise HTTPException(
            status_code=400,
            detail="No face found in that photo. Use a clear, front-facing shot.",
        )

    encoding, bbox = best
    if not db.add_encoding_to_worker(
        wid, encoding, sample_image=_crop_face(image, bbox)
    ):
        raise HTTPException(
            status_code=400,
            detail="Could not add sample (worker not found or sample limit reached)",
        )
    recognizer.invalidate_cache()
    return {"ok": True, "message": "Sample added from upload"}


@app.delete("/api/admin/workers/{wid}/samples/{sid}", tags=["Admin"])
def api_admin_delete_sample(wid: str, sid: str, _: str = Depends(require_admin)):
    """Delete one face sample from a worker."""
    ok, msg = db.remove_encoding(wid, sid)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    recognizer.invalidate_cache()
    return {"ok": True, "message": msg}


@app.delete("/api/admin/workers/{wid}", tags=["Admin"])
def api_admin_delete_worker(wid: str, _: str = Depends(require_admin)):
    """Remove a worker and every face sample belonging to them."""
    ok, name = db.remove_worker(wid)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Worker '{wid}' not found")
    attendance.drop_worker(wid)
    recognizer.invalidate_cache()
    WORKERS_COUNT.set(db.worker_count())
    return {"ok": True, "worker_id": wid, "name": name}


@app.post("/api/guests/{guest_id}/promote", tags=["Admin"])
async def api_admin_promote_guest(
    guest_id: str, request: Request, _: str = Depends(require_admin)
):
    """Promote a guest to a registered worker (admin panel)."""
    body = await request.json() if request.headers.get("content-type") else {}
    name = ((body or {}).get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")

    try:
        wid = db.promote_guest_to_worker(guest_id, name)
    except DuplicateNameError:
        raise HTTPException(status_code=409, detail=f"A worker named '{name}' already exists")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    recognizer.invalidate_cache()
    WORKERS_COUNT.set(db.worker_count())
    GUESTS_COUNT.set(db.guest_count())
    return {"ok": True, "worker_id": wid, "name": name}


@app.post("/api/camera/toggle", tags=["Dashboard"])
async def api_camera_toggle(request: Request):
    """Enable or disable the camera."""
    global camera_enabled
    with camera_lock:
        body = await request.json() if request.headers.get("content-type") else {}
        if "enabled" in body:
            camera_enabled = bool(body["enabled"])
        else:
            camera_enabled = not camera_enabled
        enabled = camera_enabled
        error = camera_error
    if enabled:
        _ensure_camera_thread()
    return {
        "enabled": enabled,
        "is_open": recognizer.is_open(),
        "error": error,
    }


# ═══════════════════════════════════════════════════════════════════
# Camera Status (from main_fastapi)
# ═══════════════════════════════════════════════════════════════════

@app.get("/camera/status", tags=["Camera"])
async def camera_status():
    """Get camera status."""
    with camera_lock:
        return {
            "enabled": camera_enabled,
            "is_open": recognizer.is_open(),
            "error": camera_error,
            "has_frame": frame is not None,
        }


# ═══════════════════════════════════════════════════════════════════
# WebSocket - Real-time Dashboard Events
# ═══════════════════════════════════════════════════════════════════

import asyncio

connected_websockets: set[WebSocket] = set()
_ws_loop = None  # reference to the asyncio event loop
_websocket_lock = threading.Lock()  # protect connected_websockets from multi-thread access


@app.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket):
    """WebSocket endpoint for real-time dashboard updates.
    Pushes attendance events as they happen.
    """
    await websocket.accept()
    with _websocket_lock:
        connected_websockets.add(websocket)
    global _ws_loop
    if _ws_loop is None:
        _ws_loop = asyncio.get_running_loop()

    last_seq_sent = 0
    try:
        while True:
            global frame_seq
            # Send latest event if available
            with event_lock:
                if event is not None:
                    await websocket.send_json({
                        "type": "event",
                        "data": event,
                    })
            # Send frame sequence info
            with cam_lock:
                current_seq = frame_seq
            if current_seq != last_seq_sent:
                await websocket.send_json({
                    "type": "frame",
                    "data": {"seq": current_seq},
                })
                last_seq_sent = current_seq

            await asyncio.sleep(0.5)  # 2 updates/sec
    except WebSocketDisconnect:
        pass
    finally:
        with _websocket_lock:
            connected_websockets.discard(websocket)


def broadcast_event(event_data: dict):
    """Broadcast an event to all connected WebSocket clients."""
    loop = _ws_loop
    if loop is None:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            return  # No event loop available — skip broadcast
    with _websocket_lock:
        clients = list(connected_websockets)
    for ws in clients:
        try:
            asyncio.run_coroutine_threadsafe(
                ws.send_json({"type": "event", "data": event_data}),
                loop,
            )
        except Exception:
            with _websocket_lock:
                connected_websockets.discard(ws)
