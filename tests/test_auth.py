"""
Unit tests for authentication (JWT + RBAC).
"""
import pytest
from datetime import datetime, timedelta
from auth import (
    Role, Permission, TokenData,
    verify_password, get_password_hash,
    create_tokens, decode_token,
    has_permission, ROLE_PERMISSIONS,
)


class TestAuth:
    """Test JWT authentication and RBAC."""

    def test_password_hashing(self):
        pw = "test_password_123"
        hashed = get_password_hash(pw)
        assert hashed != pw
        assert verify_password(pw, hashed) is True

    def test_password_hash_wrong(self):
        hashed = get_password_hash("correct")
        assert verify_password("wrong", hashed) is False

    def test_create_tokens(self):
        tokens = create_tokens("user-1", "admin", Role.ADMIN)
        assert "access_token" in tokens
        assert "refresh_token" in tokens
        assert tokens["token_type"] == "bearer"
        assert tokens["expires_in"] > 0

    def test_decode_valid_access_token(self):
        tokens = create_tokens("user-1", "admin", Role.ADMIN)
        decoded = decode_token(tokens["access_token"])
        assert decoded is not None
        assert decoded.sub == "user-1"
        assert decoded.username == "admin"
        assert decoded.role == Role.ADMIN
        assert decoded.token_type == "access"

    def test_decode_valid_refresh_token(self):
        tokens = create_tokens("user-1", "admin", Role.ADMIN)
        decoded = decode_token(tokens["refresh_token"])
        assert decoded is not None
        assert decoded.token_type == "refresh"

    def test_decode_invalid_token(self):
        decoded = decode_token("invalid_token_here")
        assert decoded is None

    def test_has_permission_admin(self):
        """Admin has all permissions."""
        now = int(datetime.utcnow().timestamp())
        token = TokenData(
            sub="user-1",
            username="admin",
            role=Role.ADMIN,
            permissions=[p.value for p in Permission],
            exp=now + 3600,
            iat=now,
            token_type="access",
        )
        assert has_permission(token, Permission.WORKER_CREATE) is True
        assert has_permission(token, Permission.SYSTEM_CONFIG) is True

    def test_has_permission_viewer(self):
        """Viewer has limited permissions."""
        now = int(datetime.utcnow().timestamp())
        token = TokenData(
            sub="user-2",
            username="viewer",
            role=Role.VIEWER,
            permissions=[p.value for p in ROLE_PERMISSIONS[Role.VIEWER]],
            exp=now + 3600,
            iat=now,
            token_type="access",
        )
        assert has_permission(token, Permission.WORKER_READ) is True
        assert has_permission(token, Permission.WORKER_CREATE) is False
        assert has_permission(token, Permission.SYSTEM_CONFIG) is False

    def test_token_expiry(self):
        """Very old token should be expired."""
        from auth import create_access_token
        old_data = {
            "sub": "user-1",
            "username": "admin",
            "role": Role.ADMIN.value,
            "permissions": [p.value for p in Permission],
        }
        # Create a token that expired long ago
        from datetime import timedelta
        old_token = create_access_token(old_data, expires_delta=timedelta(days=-1))
        decoded = decode_token(old_token)
        assert decoded is None  # Expired
