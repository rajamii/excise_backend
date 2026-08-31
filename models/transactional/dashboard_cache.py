import logging
import time
from functools import wraps
from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache
from rest_framework.response import Response

logger = logging.getLogger(__name__)

DASHBOARD_COUNTS_CACHE_PREFIX = "dashboard_counts"
DEFAULT_DASHBOARD_COUNTS_CACHE_TIMEOUT = 600
DEFAULT_DASHBOARD_CACHE_FAILURE_COOLDOWN = 60
IGNORED_CACHE_QUERY_PARAMS = {
    "cb",
    "_",
    "_t",
    "cache_buster",
    "cachebuster",
    "nocache",
    "refresh",
    "force_refresh",
    "bypass_cache",
}
BYPASS_CACHE_QUERY_PARAMS = {"nocache", "refresh", "force_refresh", "bypass_cache"}
_cache_disabled_until = 0.0
_memory_fallback_cache: dict[str, tuple[any, float]] = {}


def _dashboard_cache_available() -> bool:
    return time.monotonic() >= _cache_disabled_until


def _mark_dashboard_cache_unavailable() -> None:
    global _cache_disabled_until
    cooldown = getattr(
        settings,
        "DASHBOARD_CACHE_FAILURE_COOLDOWN",
        DEFAULT_DASHBOARD_CACHE_FAILURE_COOLDOWN,
    )
    _cache_disabled_until = time.monotonic() + max(1, int(cooldown))


def _clean_expired_memory_fallback() -> None:
    now = time.time()
    expired = [k for k, (_, exp) in _memory_fallback_cache.items() if exp < now]
    for k in expired:
        _memory_fallback_cache.pop(k, None)


def _request_cache_key(request, namespace: str) -> str:
    user = getattr(request, "user", None)
    role = getattr(user, "role", None)
    query_params = getattr(request, "query_params", request.GET if hasattr(request, "GET") else None)
    query_items = []
    if query_params is not None:
        if hasattr(query_params, "lists"):
            raw_items = query_params.lists()
        elif hasattr(query_params, "items"):
            raw_items = [(k, [v] if not isinstance(v, list) else v) for k, v in query_params.items()]
        else:
            raw_items = []

        query_items = sorted(
            (key, value)
            for key, values in raw_items
            if str(key).lower() not in IGNORED_CACHE_QUERY_PARAMS
            for value in (values if isinstance(values, list) else [values])
        )

    query_string = urlencode(query_items, doseq=True)
    return ":".join(
        [
            DASHBOARD_COUNTS_CACHE_PREFIX,
            namespace,
            f"user:{getattr(user, 'id', 'anonymous')}",
            f"role:{getattr(role, 'id', 'none')}",
            f"qs:{query_string or 'none'}",
        ]
    )


def get_cached_api_response(request, namespace: str):
    query_params = getattr(request, "query_params", request.GET if hasattr(request, "GET") else {})
    has_cache_buster = any(k in query_params for k in BYPASS_CACHE_QUERY_PARAMS)
    if has_cache_buster:
        return None

    cache_key = _request_cache_key(request, namespace)

    # 1. Try Redis cache if available
    if _dashboard_cache_available():
        try:
            val = cache.get(cache_key)
            if val is not None:
                return val
        except Exception as exc:
            _mark_dashboard_cache_unavailable()
            logger.info("Redis cache unavailable; falling back to memory/DB: %s", exc)

    # 2. Check in-memory fallback cache
    _clean_expired_memory_fallback()
    cached_entry = _memory_fallback_cache.get(cache_key)
    if cached_entry:
        data, exp = cached_entry
        if exp >= time.time():
            return data
        _memory_fallback_cache.pop(cache_key, None)

    return None


def _mark_cache_response(response, status_value: str):
    try:
        response["X-Redis-Cache"] = status_value
    except Exception:
        pass
    return response


def set_cached_api_response(request, namespace: str, response_data, timeout=None) -> None:
    if response_data is None:
        return

    if timeout is None:
        timeout = getattr(
            settings,
            "DASHBOARD_COUNTS_CACHE_TIMEOUT",
            DEFAULT_DASHBOARD_COUNTS_CACHE_TIMEOUT,
        )

    cache_key = _request_cache_key(request, namespace)

    # 1. Always store in local memory fallback
    _memory_fallback_cache[cache_key] = (response_data, time.time() + timeout)

    # 2. Store in Redis cache if available
    if _dashboard_cache_available():
        try:
            cache.set(cache_key, response_data, timeout=timeout)
        except Exception as exc:
            _mark_dashboard_cache_unavailable()
            logger.info("Redis cache unavailable; skipped Redis write: %s", exc)


def dashboard_counts_cache(namespace: str):
    """
    Cache dashboard count and list API responses per user/role/query string.

    Cache failures are deliberately non-fatal so Redis outages never block the
    dashboard; callers fall back to in-memory/database paths transparently.
    """
    timeout = getattr(
        settings,
        "DASHBOARD_COUNTS_CACHE_TIMEOUT",
        DEFAULT_DASHBOARD_COUNTS_CACHE_TIMEOUT,
    )

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            query_params = getattr(request, "query_params", request.GET if hasattr(request, "GET") else {})
            has_cache_buster = any(k in query_params for k in BYPASS_CACHE_QUERY_PARAMS)
            if not has_cache_buster:
                cached_data = get_cached_api_response(request, namespace)
                if cached_data is not None:
                    return _mark_cache_response(Response(cached_data), "HIT")

            response = view_func(request, *args, **kwargs)

            status_code = getattr(response, "status_code", 200)
            response_data = getattr(response, "data", None)
            if 200 <= status_code < 300 and isinstance(response_data, (dict, list)):
                cached_payload = dict(response_data) if isinstance(response_data, dict) else list(response_data)
                set_cached_api_response(request, namespace, cached_payload, timeout=timeout)
                _mark_cache_response(response, "MISS")
            else:
                _mark_cache_response(response, "BYPASS")

            return response

        return wrapper

    return decorator


def invalidate_dashboard_counts_cache() -> None:
    global _memory_fallback_cache
    _memory_fallback_cache.clear()

    if _dashboard_cache_available():
        try:
            from django_redis import get_redis_connection
            con = get_redis_connection("default")
            con.delete_pattern(f"{DASHBOARD_COUNTS_CACHE_PREFIX}:*")
        except Exception as exc:
            try:
                from django.core.cache import cache as django_cache
                django_cache.clear()
                logger.info("Django cache cleared as fallback.")
            except Exception as e2:
                _mark_dashboard_cache_unavailable()
                logger.info("Skipped Redis invalidation; local memory cache cleared: %s", e2)
