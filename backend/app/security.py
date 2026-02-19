"""
Security utilities: JWT handling, password hashing, token management,
and cryptographic helpers following OWASP best practices.
"""

import hashlib
import hmac
import secrets
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

settings = get_settings()

# ─── Password Hashing ─────────────────────────────────────────────────────────
# bcrypt with cost factor 12 for strong hashing
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash using constant-time comparison."""
    return pwd_context.verify(plain_password, hashed_password)


def validate_password_strength(password: str) -> Tuple[bool, list[str]]:
    """
    Validate password meets security requirements.
    Returns (is_valid, list_of_errors).
    """
    errors = []

    if len(password) < settings.MIN_PASSWORD_LENGTH:
        errors.append(
            f"Password must be at least {settings.MIN_PASSWORD_LENGTH} characters"
        )
    if settings.REQUIRE_UPPERCASE and not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter")
    if settings.REQUIRE_LOWERCASE and not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter")
    if settings.REQUIRE_DIGITS and not re.search(r"\d", password):
        errors.append("Password must contain at least one digit")
    if settings.REQUIRE_SPECIAL_CHARS and not re.search(
        r"[!@#$%^&*(),.?\":{}|<>]", password
    ):
        errors.append("Password must contain at least one special character")

    # Check for common weak patterns
    if re.search(r"(.)\1{3,}", password):
        errors.append("Password must not contain 4+ consecutive identical characters")

    return len(errors) == 0, errors


# ─── JWT Token Management ──────────────────────────────────────────────────────


def create_access_token(
    subject: str,
    additional_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Create a signed JWT access token.

    Args:
        subject: Usually the user's ID or email
        additional_claims: Extra payload data (roles, permissions, etc.)
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": str(subject),
        "iat": now,
        "exp": expire,
        "jti": str(uuid4()),  # Unique token ID for revocation support
        "type": "access",
    }

    if additional_claims:
        payload.update(additional_claims)

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(subject: str) -> str:
    """Create a long-lived refresh token."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": str(subject),
        "iat": now,
        "exp": expire,
        "jti": str(uuid4()),
        "type": "refresh",
    }

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    """
    Decode and validate a JWT token.

    Raises:
        JWTError: If token is invalid or expired
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        return payload
    except JWTError as exc:
        raise JWTError(f"Token validation failed: {exc}") from exc


def create_password_reset_token(email: str) -> str:
    """Create a time-limited password reset token."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": email,
        "exp": expire,
        "jti": str(uuid4()),
        "type": "password_reset",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


# ─── File Security ────────────────────────────────────────────────────────────


def generate_secure_filename(original_filename: str, user_id: str) -> str:
    """
    Generate a secure, unpredictable filename to prevent path traversal
    and information disclosure.
    """
    ext = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else ""
    random_part = secrets.token_urlsafe(32)
    user_hash = hashlib.sha256(user_id.encode()).hexdigest()[:8]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    if ext:
        return f"{timestamp}_{user_hash}_{random_part}.{ext}"
    return f"{timestamp}_{user_hash}_{random_part}"


def compute_file_hash(file_bytes: bytes) -> str:
    """Compute SHA-256 hash of file contents for integrity verification."""
    return hashlib.sha256(file_bytes).hexdigest()


def generate_secure_token(length: int = 32) -> str:
    """Generate a cryptographically secure random token."""
    return secrets.token_urlsafe(length)


def constant_time_compare(a: str, b: str) -> bool:
    """Compare two strings in constant time to prevent timing attacks."""
    return hmac.compare_digest(a.encode(), b.encode())