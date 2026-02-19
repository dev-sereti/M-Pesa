"""
Pydantic schemas for request/response validation.
Strict input validation is our first line of defense.
"""

import re
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


# ─── Auth Schemas ─────────────────────────────────────────────────────────────


class UserSignupRequest(BaseModel):
    email: EmailStr
    username: str = Field(
        min_length=3,
        max_length=50,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Alphanumeric, hyphens, underscores only",
    )
    full_name: Optional[str] = Field(None, max_length=100)
    password: str = Field(min_length=12, max_length=128)
    confirm_password: str

    @field_validator("username")
    @classmethod
    def username_no_reserved(cls, v: str) -> str:
        reserved = {"admin", "root", "superuser", "system", "api", "null", "undefined"}
        if v.lower() in reserved:
            raise ValueError("Username is reserved")
        return v

    @model_validator(mode="after")
    def passwords_match(self) -> "UserSignupRequest":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    # Optional: For rate limiting / IP binding
    remember_me: bool = False


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=12, max_length=128)
    confirm_password: str

    @model_validator(mode="after")
    def passwords_match(self) -> "PasswordResetConfirm":
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=128)
    confirm_password: str

    @model_validator(mode="after")
    def passwords_match(self) -> "ChangePasswordRequest":
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


# ─── User Schemas ─────────────────────────────────────────────────────────────


class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    full_name: Optional[str]
    is_active: bool
    is_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── File Processing Schemas ──────────────────────────────────────────────────


class ProcessingRequest(BaseModel):
    """Request to process an uploaded PDF statement."""
    pdf_pin: str = Field(
        min_length=4,
        max_length=20,
        description="PIN to unlock the PDF statement",
    )

    @field_validator("pdf_pin")
    @classmethod
    def pin_must_be_numeric_or_phone(cls, v: str) -> str:
        # MPesa PINs are typically phone numbers or numeric PINs
        cleaned = re.sub(r"[\s\-+]", "", v)
        if not cleaned.isalnum():
            raise ValueError("PIN must contain only alphanumeric characters")
        return cleaned


class ProcessingJobResponse(BaseModel):
    job_id: str
    status: str
    original_filename: str
    created_at: datetime
    transaction_count: Optional[int] = None
    error_message: Optional[str] = None

    model_config = {"from_attributes": True}


class ProcessingStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: Optional[int] = None
    message: Optional[str] = None
    transaction_count: Optional[int] = None
    download_url: Optional[str] = None


class TransactionRecord(BaseModel):
    """Represents a single MPesa transaction."""
    receipt_number: str
    completion_time: str
    details: str
    transaction_status: str
    paid_in: Optional[float] = None
    withdrawn: Optional[float] = None
    transaction_cost: Optional[float] = None
    balance: Optional[float] = None


class StatementSummary(BaseModel):
    """Summary statistics for an MPesa statement."""
    period_from: Optional[str] = None
    period_to: Optional[str] = None
    account_holder: Optional[str] = None
    phone_number: Optional[str] = None
    total_transactions: int
    total_paid_in: float
    total_withdrawn: float
    total_charges: float
    transactions: List[TransactionRecord]


# ─── Common Response Schemas ──────────────────────────────────────────────────


class MessageResponse(BaseModel):
    message: str
    success: bool = True


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None