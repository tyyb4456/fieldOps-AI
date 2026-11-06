from __future__ import annotations

import threading
import time
from collections import deque

from app.core.config import settings

# This is deliberately an in-process limiter. It does not add Redis/Celery
# dependencies to the authentication path. In a multi-instance deployment,
# reverse-proxy or gateway rate limiting must also be configured; see
# _docs/clerk_authentication.md. The limiter here is a best-effort defence
# that is still useful for a single-process deployment and for tests.
_KEY_SEPARATOR = "\x1f"


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Too many requests")
        self.retry_after = max(1, int(retry_after))


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: int,
        now: float | None = None,
    ) -> None:
        current = time.monotonic() if now is None else now
        cutoff = current - window_seconds

        with self._lock:
            events = self._events.setdefault(key, deque())
            while events and events[0] <= cutoff:
                events.popleft()

            if len(events) >= limit:
                retry_after = max(
                    1,
                    int(events[0] + window_seconds - current) + 1,
                )
                raise RateLimitExceeded(retry_after)

            events.append(current)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


bootstrap_ip_limiter = InMemoryRateLimiter()
bootstrap_subject_limiter = InMemoryRateLimiter()


def _client_ip(request) -> str:
    """Return the direct peer address.

    X-Forwarded-For is intentionally not trusted here because it is
    client-controlled unless a trusted reverse proxy strips and rewrites it.
    Deployments behind a proxy should enforce rate limits at the proxy or
    explicitly configure trusted proxy handling before relying on this value.
    """
    client = getattr(request, "client", None)
    if client is None:
        return "unknown"
    host = getattr(client, "host", None)
    return str(host) if host else "unknown"


def _bootstrap_key(prefix: str, value: str) -> str:
    return f"{prefix}{_KEY_SEPARATOR}{value}"


def enforce_bootstrap_ip_limit(request) -> None:
    bootstrap_ip_limiter.check(
        _bootstrap_key("ip", _client_ip(request)),
        limit=settings.auth_bootstrap_rate_limit_per_ip,
        window_seconds=settings.auth_bootstrap_rate_limit_window_seconds,
    )


def enforce_bootstrap_subject_limit(subject: str) -> None:
    bootstrap_subject_limiter.check(
        _bootstrap_key("sub", subject),
        limit=settings.auth_bootstrap_rate_limit_per_subject,
        window_seconds=settings.auth_bootstrap_rate_limit_window_seconds,
    )


def reset_rate_limiters() -> None:
    bootstrap_ip_limiter.clear()
    bootstrap_subject_limiter.clear()
