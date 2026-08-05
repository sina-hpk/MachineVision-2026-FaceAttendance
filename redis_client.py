"""
Redis Integration - Caching, Session Management, Rate Limiting
Uses lazy connection to avoid blocking at import time.
"""
import redis
import json
import hashlib
from typing import Optional, Any, Callable
from functools import wraps
import time
from contextlib import contextmanager

from config import settings


class RedisClient:
    """Redis client wrapper with connection pooling and common operations."""

    _instance: Optional['RedisClient'] = None
    _client: Optional[redis.Redis] = None
    _health: Optional[tuple[float, bool]] = None
    _HEALTH_TTL = 10.0

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        pass  # Lazy init — _connect() is called on first use

    def _connect(self):
        """Lazily connect to Redis."""
        if self._client is None:
            self._client = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
                retry_on_timeout=False,
                max_connections=5,
            )
        return self._client

    @property
    def client(self) -> redis.Redis:
        return self._connect()

    def health_check(self) -> bool:
        """Check Redis connectivity. Result is cached briefly so that an
        unreachable Redis does not add latency to every health request."""
        cached = type(self)._health
        now = time.time()
        if cached is not None and now - cached[0] < self._HEALTH_TTL:
            return cached[1]
        try:
            ok = bool(self.client.ping())
        except Exception:
            ok = False
        type(self)._health = (now, ok)
        return ok

    # ── Generic Cache Operations ──

    def get(self, key: str) -> Optional[str]:
        return self.client.get(key)

    def set(self, key: str, value: str, ttl: int = 3600) -> bool:
        return self.client.setex(key, ttl, value)

    def set_json(self, key: str, value: Any, ttl: int = 3600) -> bool:
        return self.set(key, json.dumps(value), ttl)

    def get_json(self, key: str) -> Optional[Any]:
        val = self.get(key)
        if val:
            return json.loads(val)
        return None

    def delete(self, *keys: str) -> int:
        return self.client.delete(*keys)

    def exists(self, key: str) -> bool:
        return self.client.exists(key)

    def expire(self, key: str, ttl: int) -> bool:
        return self.client.expire(key, ttl)

    def ttl(self, key: str) -> int:
        return self.client.ttl(key)

    # ── Session Management ──

    def create_session(self, user_id: str, data: dict, ttl: int = 1800) -> str:
        """Create a session with token."""
        import secrets
        token = secrets.token_urlsafe(32)
        session_key = f"session:{token}"
        session_data = {
            "user_id": user_id,
            "data": data,
            "created_at": time.time(),
        }
        self.set_json(session_key, session_data, ttl)
        return token

    def get_session(self, token: str) -> Optional[dict]:
        return self.get_json(f"session:{token}")

    def delete_session(self, token: str) -> bool:
        return self.delete(f"session:{token}") > 0

    def extend_session(self, token: str, ttl: int = 1800) -> bool:
        return self.expire(f"session:{token}", ttl)

    # ── Rate Limiting ──

    def check_rate_limit(
        self,
        key: str,
        limit: int,
        window: int,
    ) -> tuple[bool, dict]:
        """
        Check rate limit using sliding window log algorithm.

        Returns:
            (allowed, info_dict) where info_dict contains:
            - remaining: requests remaining
            - reset_at: unix timestamp when window resets
            - limit: max requests
        """
        now = time.time()
        window_start = now - window
        rate_key = f"ratelimit:{key}"

        pipe = self.client.pipeline()

        # Remove expired entries
        pipe.zremrangebyscore(rate_key, 0, window_start)

        # Count current requests
        pipe.zcard(rate_key)

        # Add current request
        pipe.zadd(rate_key, {str(now): now})

        # Set expiry
        pipe.expire(rate_key, window)

        results = pipe.execute()
        current_count = results[1]

        allowed = current_count < limit
        remaining = max(0, limit - current_count - 1)

        return allowed, {
            "allowed": allowed,
            "remaining": remaining,
            "reset_at": int(now + window),
            "limit": limit,
            "current": current_count,
        }

    def clear_rate_limit(self, key: str) -> int:
        return self.delete(f"ratelimit:{key}")

    # ── Caching Decorators ──

    def cache_key(self, prefix: str, *args, **kwargs) -> str:
        """Generate cache key from function arguments."""
        key_parts = [prefix]
        key_parts.extend(str(arg) for arg in args)
        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}:{v}")
        raw = ":".join(key_parts)
        return f"cache:{hashlib.md5(raw.encode()).hexdigest()}"


def cached(ttl: int = 300, prefix: str = "func"):
    """Decorator for caching function results (supports sync and async)."""
    def decorator(func: Callable):
        import asyncio

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            r = RedisClient()
            key = r.cache_key(prefix, func.__name__, *args, **kwargs)
            cached_result = r.get_json(key)
            if cached_result is not None:
                return cached_result
            result = await func(*args, **kwargs)
            r.set_json(key, result, ttl)
            return result

        @wraps(func)
        def wrapper(*args, **kwargs):
            r = RedisClient()
            key = r.cache_key(prefix, func.__name__, *args, **kwargs)
            cached_result = r.get_json(key)
            if cached_result is not None:
                return cached_result
            result = func(*args, **kwargs)
            r.set_json(key, result, ttl)
            return result

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper
    return decorator


# ── Rate Limit Decorator ──

def rate_limit(
    limit: int = 100,
    window: int = 60,
    key_func: Optional[Callable] = None,
):
    """Decorator for rate limiting endpoints (supports both sync and async)."""
    def decorator(func: Callable):
        import asyncio

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            r = RedisClient()

            if key_func:
                key = key_func(*args, **kwargs)
            else:
                key = f"{func.__name__}:{args[0] if args else 'default'}"

            allowed, info = r.check_rate_limit(key, limit, window)

            if not allowed:
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "Rate limit exceeded",
                        "retry_after": info["reset_at"] - int(time.time()),
                        "limit": limit,
                        "window": window,
                    }
                )

            return await func(*args, **kwargs)

        @wraps(func)
        def wrapper(*args, **kwargs):
            r = RedisClient()

            if key_func:
                key = key_func(*args, **kwargs)
            else:
                key = f"{func.__name__}:{args[0] if args else 'default'}"

            allowed, info = r.check_rate_limit(key, limit, window)

            if not allowed:
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "Rate limit exceeded",
                        "retry_after": info["reset_at"] - int(time.time()),
                        "limit": limit,
                        "window": window,
                    }
                )

            return func(*args, **kwargs)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper
    return decorator


# ── Global Instance (lazy — doesn't connect at import) ──

redis_client = RedisClient()


@contextmanager
def redis_session():
    """Context manager for Redis operations with error handling."""
    try:
        yield redis_client
    except redis.RedisError as e:
        print(f"Redis error: {e}")
