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
IGNORED_CACHE_QUERY_PARAMS = {"cb", "_", "cache_buster", "cachebuster"}
_cache_disabled_until = 0.0


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


def _request_cache_key(request, namespace: str) -> str:
    user = getattr(request, "user", None)
    role = getattr(user, "role", None)
    query_params = getattr(request, "query_params", None)
    query_items = []
    if query_params is not None:
        query_items = sorted(
            (key, value)
            for key, values in query_params.lists()
            if str(key).lower() not in IGNORED_CACHE_QUERY_PARAMS
            for value in values
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


def dashboard_counts_cache(namespace: str):
    """
    Cache dashboard count API responses per user/role/query string.

    Cache failures are deliberately non-fatal so Redis outages never block the
    dashboard; callers fall back to the database path transparently.
    """
    timeout = getattr(
        settings,
        "DASHBOARD_COUNTS_CACHE_TIMEOUT",
        DEFAULT_DASHBOARD_COUNTS_CACHE_TIMEOUT,
    )

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            cache_key = _request_cache_key(request, namespace)
            cached_data = None

            if _dashboard_cache_available():
                try:
                    cached_data = cache.get(cache_key)
                except Exception as exc:
                    _mark_dashboard_cache_unavailable()
                    logger.info("Dashboard cache unavailable; using database fallback: %s", exc)

            if cached_data is not None:
                return Response(cached_data)

            response = view_func(request, *args, **kwargs)

            status_code = getattr(response, "status_code", 200)
            response_data = getattr(response, "data", None)
            if _dashboard_cache_available() and 200 <= status_code < 300 and isinstance(response_data, dict):
                try:
                    cache.set(cache_key, dict(response_data), timeout=timeout)
                except Exception as exc:
                    _mark_dashboard_cache_unavailable()
                    logger.info("Dashboard cache unavailable; skipped cache write: %s", exc)

            return response

        return wrapper

    return decorator


def invalidate_dashboard_counts_cache() -> None:
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
                logger.info("Skipped cache invalidation; using database fallback: %s", e2)
