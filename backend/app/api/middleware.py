"""
FastAPI middleware: Request logging, security headers, rate limiting,
and request ID tracking.
"""

import logging
import time
import uuid
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# ─── Rate Limiter ─────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all HTTP responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Enable XSS protection
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        # Control referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Content Security Policy
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "frame-ancestors 'none';"
        )
        # HSTS (only in production)
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )
        # Remove server information
        response.headers.pop("server", None)
        response.headers.pop("x-powered-by", None)

        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log all requests with timing, request ID, and sanitized details."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = str(uuid.uuid4())
        start_time = time.perf_counter()

        # Attach request ID for tracing
        request.state.request_id = request_id

        # Log request (never log request bodies - may contain PINs)
        logger.info(
            f"REQUEST [{request_id}] {request.method} {request.url.path} "
            f"IP={self._get_client_ip(request)}"
        )

        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error(
                f"REQUEST [{request_id}] UNHANDLED ERROR: {type(exc).__name__}"
            )
            raise

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"RESPONSE [{request_id}] {response.status_code} "
            f"took={elapsed_ms:.1f}ms"
        )

        response.headers["X-Request-ID"] = request_id
        return response

    def _get_client_ip(self, request: Request) -> str:
        """Extract real client IP considering reverse proxy headers."""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        return request.client.host if request.client else "unknown"


class ContentTypeValidationMiddleware(BaseHTTPMiddleware):
    """Reject requests with unexpected content types for sensitive endpoints."""

    PROTECTED_PATHS = ["/api/auth/", "/api/process/"]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        if request.method == "POST":
            content_type = request.headers.get("content-type", "")
            is_protected = any(
                path.startswith(p) for p in self.PROTECTED_PATHS
            )

            # File upload endpoints must be multipart
            if "/upload" in path and "multipart/form-data" not in content_type:
                return JSONResponse(
                    status_code=415,
                    content={"error": "Unsupported Media Type"},
                )

        return await call_next(request)