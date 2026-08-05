"""
JWT Authentication + RBAC (Role-Based Access Control)
Core module - no FastAPI dependencies at module level
"""
from datetime import datetime, timedelta
from typing import Optional, List
from enum import Enum
from dataclasses import dataclass

from jose import jwt, JWTError
from passlib.context import CryptContext

from config import settings


# Password hashing - use sha256_crypt instead of bcrypt for compatibility
pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")


class Role(str, Enum):
    """User roles."""
    ADMIN = "admin"
    MANAGER = "manager"
    OPERATOR = "operator"
    VIEWER = "viewer"


class Permission(str, Enum):
    """Granular permissions."""
    # Workers
    WORKER_READ = "worker:read"
    WORKER_CREATE = "worker:create"
    WORKER_UPDATE = "worker:update"
    WORKER_DELETE = "worker:delete"

    # Attendance
    ATTENDANCE_READ = "attendance:read"
    ATTENDANCE_EXPORT = "attendance:export"

    # System
    SYSTEM_CONFIG = "system:config"
    SYSTEM_LOGS = "system:logs"
    CAMERA_CONTROL = "camera:control"

    # API
    API_ACCESS = "api:access"


# Role-Permission mapping
ROLE_PERMISSIONS = {
    Role.ADMIN: [
        Permission.WORKER_READ,
        Permission.WORKER_CREATE,
        Permission.WORKER_UPDATE,
        Permission.WORKER_DELETE,
        Permission.ATTENDANCE_READ,
        Permission.ATTENDANCE_EXPORT,
        Permission.SYSTEM_CONFIG,
        Permission.SYSTEM_LOGS,
        Permission.CAMERA_CONTROL,
        Permission.API_ACCESS,
    ],
    Role.MANAGER: [
        Permission.WORKER_READ,
        Permission.WORKER_CREATE,
        Permission.WORKER_UPDATE,
        Permission.ATTENDANCE_READ,
        Permission.ATTENDANCE_EXPORT,
        Permission.CAMERA_CONTROL,
        Permission.API_ACCESS,
    ],
    Role.OPERATOR: [
        Permission.WORKER_READ,
        Permission.WORKER_CREATE,
        Permission.ATTENDANCE_READ,
        Permission.CAMERA_CONTROL,
        Permission.API_ACCESS,
    ],
    Role.VIEWER: [
        Permission.WORKER_READ,
        Permission.ATTENDANCE_READ,
        Permission.API_ACCESS,
    ],
}


@dataclass
class TokenData:
    """Decoded token data."""
    sub: str  # user_id
    username: str
    role: Role
    permissions: List[Permission]
    exp: int
    iat: int
    token_type: str  # "access" or "refresh"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create JWT access token."""
    to_encode = data.copy()
    now = datetime.utcnow()
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.access_token_expire_minutes)

    to_encode.update({"exp": expire, "iat": now, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """Create JWT refresh token."""
    to_encode = data.copy()
    now = datetime.utcnow()
    expire = now + timedelta(days=settings.refresh_token_expire_days)
    to_encode.update({"exp": expire, "iat": now, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt


def decode_token(token: str) -> Optional[TokenData]:
    """Decode and validate JWT token."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])

        if payload.get("type") not in ("access", "refresh"):
            return None

        sub = payload.get("sub")
        username = payload.get("username")
        role_str = payload.get("role")
        permissions = payload.get("permissions", [])
        exp = payload.get("exp")
        iat = payload.get("iat")
        token_type = payload.get("type")

        if not all([sub, username, role_str, exp, iat]):
            return None

        try:
            role = Role(role_str)
        except ValueError:
            return None

        perm_list = [Permission(p) for p in permissions if p in Permission.__members__.values()]

        return TokenData(
            sub=sub,
            username=username,
            role=role,
            permissions=perm_list,
            exp=exp,
            iat=iat,
            token_type=token_type,
        )
    except JWTError:
        return None


def create_tokens(user_id: str, username: str, role: Role) -> dict:
    """Create access and refresh tokens for a user."""
    permissions = ROLE_PERMISSIONS.get(role, [])
    permission_values = [p.value for p in permissions]

    access_data = {
        "sub": user_id,
        "username": username,
        "role": role.value,
        "permissions": permission_values,
    }

    refresh_data = {
        "sub": user_id,
        "username": username,
        "role": role.value,
        "permissions": permission_values,
    }

    return {
        "access_token": create_access_token(access_data),
        "refresh_token": create_refresh_token(refresh_data),
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
    }


def refresh_access_token(refresh_token: str) -> Optional[dict]:
    """Refresh access token using refresh token."""
    token_data = decode_token(refresh_token)
    if not token_data or token_data.token_type != "refresh":
        return None

    return create_tokens(token_data.sub, token_data.username, token_data.role)


def has_permission(token_data: TokenData, permission: Permission) -> bool:
    """Check if token has specific permission."""
    return permission in token_data.permissions