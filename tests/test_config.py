"""
Tests for the config module.
"""
import os
from config import Settings, get_settings, settings


class TestSettingsDefaults:
    """Tests that settings have correct default values.

    These tests explicitly clear relevant env vars so they test
    the code defaults rather than any environment overrides.
    """

    def test_app_defaults(self, monkeypatch):
        """App settings have correct defaults."""
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        monkeypatch.delenv("METRICS_ENABLED", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("REDIS_URL", raising=False)
        s = Settings(_env_file=None)
        assert s.app_name == "CV Attendance System"
        assert s.app_version == "3.2.0"
        assert s.debug is False

    def test_database_defaults(self, monkeypatch):
        """Database settings have correct defaults."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        s = Settings(_env_file=None)
        assert s.database_url == "sqlite:///data/cv_attendance.db"
        assert s.db_echo is False

    def test_security_defaults(self, monkeypatch):
        """Security settings have correct defaults."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("REDIS_URL", raising=False)
        s = Settings(_env_file=None)
        assert s.secret_key == "cv-attendance-change-me-in-production-2024"
        assert s.algorithm == "HS256"
        assert s.access_token_expire_minutes == 30
        assert s.refresh_token_expire_days == 7

    def test_server_defaults(self, monkeypatch):
        """Server settings have correct defaults."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("REDIS_URL", raising=False)
        s = Settings(_env_file=None)
        assert s.host == "0.0.0.0"
        assert s.port == 5000
        assert s.workers == 4

    def test_face_recognition_defaults(self, monkeypatch):
        """Face recognition settings have correct defaults."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("REDIS_URL", raising=False)
        s = Settings(_env_file=None)
        assert s.tolerance == 0.6
        assert s.quality_threshold == 0.4
        assert s.liveness_threshold == 0.55

    def test_logging_defaults(self, monkeypatch):
        """Logging settings have correct defaults."""
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("REDIS_URL", raising=False)
        s = Settings(_env_file=None)
        assert s.log_level == "INFO"
        assert s.log_json is True

    def test_metrics_defaults(self, monkeypatch):
        """Metrics settings have correct defaults."""
        monkeypatch.delenv("METRICS_ENABLED", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("REDIS_URL", raising=False)
        s = Settings(_env_file=None)
        assert s.metrics_enabled is True

    def test_rate_limiting_defaults(self, monkeypatch):
        """Rate limiting settings have correct defaults."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("REDIS_URL", raising=False)
        s = Settings(_env_file=None)
        assert s.rate_limit_requests == 100
        assert s.rate_limit_window == 60


class TestEnvironmentOverrides:
    """Tests for environment variable overrides."""

    def test_database_url_override(self, monkeypatch):
        """DATABASE_URL env var overrides the default."""
        monkeypatch.setenv("DATABASE_URL", "sqlite:///test_override.db")
        s = Settings()
        assert s.database_url == "sqlite:///test_override.db"

    def test_debug_override(self, monkeypatch):
        """DEBUG env var overrides the default."""
        monkeypatch.setenv("DEBUG", "true")
        s = Settings()
        assert s.debug is True

    def test_log_level_override(self, monkeypatch):
        """LOG_LEVEL env var overrides the default."""
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        s = Settings()
        assert s.log_level == "DEBUG"

    def test_metrics_disabled(self, monkeypatch):
        """METRICS_ENABLED can be set to false via env."""
        monkeypatch.setenv("METRICS_ENABLED", "false")
        s = Settings()
        assert s.metrics_enabled is False

    def test_port_override(self, monkeypatch):
        """PORT env var overrides the default."""
        monkeypatch.setenv("PORT", "8080")
        s = Settings()
        assert s.port == 8080

    def test_secret_key_override(self, monkeypatch):
        """SECRET_KEY env var overrides the default."""
        monkeypatch.setenv("SECRET_KEY", "custom-secret-key")
        s = Settings()
        assert s.secret_key == "custom-secret-key"

    def test_camera_index_override(self, monkeypatch):
        """CAMERA_INDEX env var overrides the default."""
        monkeypatch.setenv("CAMERA_INDEX", "2")
        s = Settings()
        assert s.camera_index == 2

    def test_tolerance_override(self, monkeypatch):
        """TOLERANCE env var overrides the default."""
        monkeypatch.setenv("TOLERANCE", "0.6")
        s = Settings()
        assert s.tolerance == 0.6

    def test_redis_url_override(self, monkeypatch):
        """REDIS_URL env var overrides the default."""
        monkeypatch.setenv("REDIS_URL", "redis://custom-host:6379/5")
        s = Settings()
        assert s.redis_url == "redis://custom-host:6379/5"


class TestGetSettings:
    """Tests for the get_settings() singleton."""

    def test_get_settings_returns_instance(self):
        """get_settings returns a Settings instance."""
        s = get_settings()
        assert isinstance(s, Settings)

    def test_get_settings_is_singleton(self):
        """get_settings returns the same instance on repeated calls."""
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_global_settings_is_instance(self):
        """The module-level settings object is a Settings instance."""
        assert isinstance(settings, Settings)
