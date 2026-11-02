import logging
import os
import threading
import time
from pathlib import Path

import redis

logger = logging.getLogger("redis_support")

_lock = threading.Lock()
_client = None
_down_until = 0.0
_url = None


def _redis_url() -> str:
    global _url
    if _url is None:
        _url = os.environ.get("REDIS_URL", "")
        if not _url:
            env = Path(".env")
            if env.exists():
                for line in env.read_text().splitlines():
                    if line.startswith("REDIS_URL="):
                        _url = line.split("=", 1)[1].strip().strip('"').strip("'")
        _url = _url or ""
    return _url


def get_client():
    """The Redis client, or None when Redis is not set up or is down right now."""
    global _client
    if time.time() < _down_until:
        return None
    url = _redis_url()
    if not url:
        return None
    with _lock:
        if _client is None:
            _client = redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
        return _client


def mark_down(exc: Exception):
    """After a failure, stop trying Redis for 30 seconds (the app keeps working without it)."""
    global _client, _down_until
    logger.warning("Redis is unavailable (%s). Using the fallback for 30 seconds.", type(exc).__name__)
    _down_until = time.time() + 30
    _client = None


# ---------- rate limiting ----------

# Count the request and set the 1-minute timer on the first one; all in ONE command.
_RATE_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('PEXPIRE', KEYS[1], ARGV[1]) end
local ttl = redis.call('PTTL', KEYS[1])
return {count, ttl}
"""


class HybridRateLimiter:
    """Uses Redis when it works, and the given in-memory limiter when it does not."""

    def __init__(self, fallback):
        self.fallback = fallback

    def check(self, key: str, limit: int, window: int = 60) -> int:
        """Return 0 if allowed, otherwise the number of seconds to wait."""
        client = get_client()
        if client is not None:
            try:
                count, ttl_ms = client.eval(_RATE_SCRIPT, 1, f"rl:{key}", window * 1000)
                if count > limit:
                    return max(1, int(max(ttl_ms, 1000) / 1000) + 1)
                return 0
            except Exception as exc:
                mark_down(exc)
        return self.fallback.check(key, limit, window)


# ---------- caching ----------
# Every cache has a "version" number. Changing data raises the version,
# which makes all older cached answers unreachable at once.

def cache_lookup(namespace: str, key: str):
    """Returns (cached_bytes_or_None, version). version is None when Redis is unavailable."""
    client = get_client()
    if client is None:
        return None, None
    try:
        raw = client.get(f"cachever:{namespace}")
        version = raw.decode() if raw else "0"
        return client.get(f"cache:{namespace}:{version}:{key}"), version
    except Exception as exc:
        mark_down(exc)
        return None, None


def cache_store(namespace: str, key: str, value: bytes, ttl_seconds: int, version):
    client = get_client()
    if client is None or version is None:
        return
    try:
        client.setex(f"cache:{namespace}:{version}:{key}", ttl_seconds, value)
    except Exception as exc:
        mark_down(exc)


def cache_bump(namespace: str):
    client = get_client()
    if client is None:
        return
    try:
        client.incr(f"cachever:{namespace}")
    except Exception as exc:
        mark_down(exc)