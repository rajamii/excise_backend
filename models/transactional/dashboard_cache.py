import logging
import time
from functools import wraps
from urllib.parse import urlencode
from django.conf import settings
from django.core.cache import cache
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)

DASHBOARD_COUNTS_CACHE_PREFIX = "dashboard_counts"
DEFAULT_DASHBOARD_COUNTS_CACHE_TIMEOUT = 600
DEFAULT_DASHBOARD_CACHE_FAILURE_COOLDOWN = 60
IGNORED_CACHE_QUERY_PARAMS = {"cb", "_", "_t", "cache_buster", "cachebuster"}
BYPASS_CACHE_QUERY_PARAMS = {"cb", "_", "cache_buster", "cachebuster"}

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

def _validate_dashboard_query_params(request):
    """
    Validates 'year' and 'month' parameters to prevent Integer Overflow (500)
    and Application Error issues identified in the security audit.
    """
    query_params = getattr(request, 'query_params', getattr(request, 'GET', {}))
    
    # Validate 'year' parameter
    year_str = query_params.get('year')
    if year_str is not None:
        try:
            year_val = int(year_str)
            if year_val < 1900 or year_val > 2100:
                return Response(
                    {"detail": "Invalid 'year' parameter value. Must be between 1900 and 2100."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except (ValueError, TypeError, OverflowError):
            return Response(
                {"detail": "Invalid 'year' parameter value. Integer overflow or invalid format."},
                status=status.HTTP_400_BAD_REQUEST
            )

    # Validate 'month' parameter
    month_str = query_params.get('month')
    if month_str is not None:
        try:
            month_val = int(month_str)
            if month_val < 1 or month_val > 12:
                return Response(
                    {"detail": "Invalid 'month' parameter value. Must be between 1 and 12."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except (ValueError, TypeError, OverflowError):
            return Response(
                {"detail": "Invalid 'month' parameter value. Integer overflow or invalid format."},
                status=status.HTTP_400_BAD_REQUEST
            )

    return None

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

def get_cached_api_response(request, namespace: str):
    cache_key = _request_cache_key(request, namespace)
    query_params = getattr(request, 'query_params', request.GET if hasattr(request, 'GET') else {})
    has_cache_buster = any(k in query_params for k in BYPASS_CACHE_QUERY_PARAMS)
    if not _dashboard_cache_available() or has_cache_buster:
        return None
    try:
        return cache.get(cache_key)
    except Exception as exc:
        _mark_dashboard_cache_unavailable()
        logger.info("API response cache unavailable; using database fallback: %s", exc)
        return None

def _mark_cache_response(response, status_value: str):
    """
    Applies secure HTTP headers mandated by the security audit report:
    - Cross-Origin-Embedder-Policy (COEP)
    - Cross-Origin-Opener-Policy (COOP)
    - Cross-Origin-Resource-Policy (CORP)
    - Content-Security-Policy (CSP)
    - Referrer-Policy
    """
    try:
        response["X-Redis-Cache"] = status_value
        response["Cross-Origin-Embedder-Policy"] = "require-corp"
        response["Cross-Origin-Opener-Policy"] = "same-origin"
        response["Cross-Origin-Resource-Policy"] = "same-origin"
        response["Content-Security-Policy"] = "default-src 'self'"
        response["Referrer-Policy"] = "strict-origin-when-cross-origin"
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
    if not _dashboard_cache_available():
        return
    cache_key = _request_cache_key(request, namespace)
    try:
        cache.set(cache_key, response_data, timeout=timeout)
    except Exception as exc:
        _mark_dashboard_cache_unavailable()
        logger.info("API response cache unavailable; skipped cache write: %s", exc)

def dashboard_counts_cache(namespace: str):
    timeout = getattr(
        settings,
        "DASHBOARD_COUNTS_CACHE_TIMEOUT",
        DEFAULT_DASHBOARD_COUNTS_CACHE_TIMEOUT,
    )
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Enforce input bounds validation on incoming parameters
            invalid_param_response = _validate_dashboard_query_params(request)
            if invalid_param_response is not None:
                return _mark_cache_response(invalid_param_response, "BYPASS")

            cached_data = get_cached_api_response(request, namespace)
            if cached_data is not None:
                return _mark_cache_response(Response(cached_data), "HIT")

            try:
                response = view_func(request, *args, **kwargs)
            except (ValueError, TypeError, OverflowError) as exc:
                logger.error("Data error during dashboard count calculation: %s", exc)
                return _mark_cache_response(
                    Response({"detail": "Invalid query parameter supplied."}, status=status.HTTP_400_BAD_REQUEST),
                    "BYPASS"
                )

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