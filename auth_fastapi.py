"""
FastAPI-specific authentication dependencies.
This module is only imported when FastAPI is available.
"""
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from auth import (
    decode_token,
    TokenData,
    Permission,
    Role,
    has_permission,
)


# FastAPI Security scheme
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[TokenData]:
    """Get current authenticated user from token."""
    if not credentials:
        return None

    token_data = decode_token(credentials.credentials)
    return token_data


async def get_current_active_user(
    current_user: Optional[TokenData] = Depends(get_current_user)
) -> TokenData:
    """Get current active user (required authentication)."""
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user


def require_permission(permission: Permission):
    """FastAPI dependency for permission checking."""

    def permission_checker(
        credentials: HTTPAuthorizationCredentials = Depends(security)
    ) -> TokenData:
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token_data = decode_token(credentials.credentials)
        if not token_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not has_permission(token_data, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission.value} required",
            )

        return token_data

    return permission_checker


def require_role(*roles: Role):
    """FastAPI dependency for role checking."""

    def role_checker(
        credentials: HTTPAuthorizationCredentials = Depends(security)
    ) -> TokenData:
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token_data = decode_token(credentials.credentials)
        if not token_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if token_data.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role required: {[r.value for r in roles]}",
            )

        return token_data

    return role_checker