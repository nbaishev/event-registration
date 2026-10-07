import logging
import secrets

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.common.config import Settings, get_settings
from app.common.errors import AppError, error_response

logger = logging.getLogger(__name__)

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def validate_unsafe_request(request: Request, settings: Settings) -> None:
    if request.method not in UNSAFE_METHODS:
        return
    cookie = request.cookies.get("csrf_token", "")
    header = request.headers.get("X-CSRF-Token", "")
    # Byte comparison also rejects mismatching non-ASCII inputs without raising.
    if (
        not cookie
        or not header
        or not secrets.compare_digest(cookie.encode("utf-8"), header.encode("utf-8"))
        or request.headers.get("origin") != settings.app_origin
    ):
        raise AppError(403, "CSRF_INVALID", "Invalid CSRF token or origin.")


class AuthSecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response: Response
        try:
            validate_unsafe_request(request, get_settings())
            response = await call_next(request)
        except AppError as exc:
            response = error_response(exc.status, exc.code, exc.message)
        except Exception as exc:
            if not request.url.path.startswith("/api/auth/"):
                raise
            # Never log exception text/tracebacks: they can contain submitted
            # credentials or database row values even with hidden SQL parameters.
            logger.error("Unhandled auth request error (%s).", type(exc).__name__)
            response = error_response(500, "INTERNAL_ERROR", "Internal server error.")
        cancellation_request = (
            request.method == "DELETE"
            and request.url.path.startswith("/api/events/")
            and request.url.path.rstrip("/").endswith("/registration")
        )
        if request.url.path.startswith("/api/auth/") or cancellation_request:
            response.headers["Cache-Control"] = "no-store"
        return response
