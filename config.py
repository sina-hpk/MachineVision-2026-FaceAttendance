"""
Settings Management - Pydantic Settings with Environment Variables
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "CV Attendance System"
    app_version: str = "3.2.0"
    debug: bool = False

    # Database
    database_url: str = "sqlite:///data/cv_attendance.db"
    db_echo: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Security
    secret_key: str = "cv-attendance-change-me-in-production-2024"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Admin panel (HTTP Basic). The panel can delete face samples and promote
    # guests, so it must not stay open. Override both via .env in production.
    admin_username: str = "admin"
    admin_password: str = "admin"

    # Server
    host: str = "0.0.0.0"
    port: int = 5000
    workers: int = 4

    # Camera
    camera_index: int = 0
    camera_enabled: bool = True
    process_scale: float = 0.5

    # Face Recognition
    prefer_insightface: bool = True
    insightface_det_size: int = 320
    tolerance: float = 0.6
    quality_threshold: float = 0.4
    liveness_threshold: float = 0.55
    augment_min_distance: float = 0.2
    max_encodings: int = 10
    augment_cooldown_minutes: int = 5
    cooldown_seconds: int = 8
    guest_capture_interval: int = 5

    # Paths
    data_dir: str = "data"
    faces_dir: str = "data/faces"
    attendance_dir: str = "data/attendance"

    # Logging
    log_level: str = "INFO"
    log_json: bool = True

    # Prometheus
    metrics_enabled: bool = True

    # Rate Limiting
    rate_limit_requests: int = 100
    rate_limit_window: int = 60


@lru_cache
def get_settings() -> "Settings":
    return Settings()


settings = get_settings()