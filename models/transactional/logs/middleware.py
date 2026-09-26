import threading

_thread_locals = threading.local()


def get_current_request():
    """Returns the current HTTP request stored in thread-local storage."""
    return getattr(_thread_locals, 'request', None)


def get_current_user():
    """Returns the current authenticated user from thread-local request, if available."""
    request = get_current_request()
    if request and hasattr(request, 'user') and getattr(request.user, 'is_authenticated', False):
        return request.user
    return None


class ThreadLocalRequestMiddleware:
    """
    Middleware that captures the current HTTP request in thread-local storage
    so model signals and services can access the active user and request metadata.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _thread_locals.request = request
        try:
            response = self.get_response(request)
        finally:
            _thread_locals.request = None
        return response
