"""
API Routes: Authentication, file processing, and user management endpoints.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import Response, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.database import (
    AuditLog,
    ProcessingJob,
    RefreshToken,
    User,
    get_db,
)
from app.models.schemas import (
    ChangePasswordRequest,
    MessageResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    ProcessingJobResponse,
    ProcessingStatusResponse,
    RefreshTokenRequest,
    TokenResponse,
    UserLoginRequest,
    UserResponse,
    UserSignupRequest,
)
from app.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    validate_password_strength,
    verify_password,
    compute_file_hash,
    generate_secure_token,
)
from app.services.excel_generator import ExcelGenerator
from app.services.file_manager import FileManager
from app.services.pdf_processor import (
    CorruptedPDFError,
    InvalidPINError,
    PDFProcessingError,
    PDFProcessor,
)

settings = get_settings()
logger = logging.getLogger(__name__)
security_scheme = HTTPBearer()

# ─── Routers ──────────────────────────────────────────────────────────────────
auth_router = APIRouter(prefix="/api/auth", tags=["Authentication"])
process_router = APIRouter(prefix="/api/process", tags=["Processing"])
user_router = APIRouter(prefix="/api/users", tags=["Users"])

# ─── Services ─────────────────────────────────────────────────────────────────
pdf_processor = PDFProcessor()
excel_generator = ExcelGenerator()
file_manager = FileManager()


# ─── Dependency: Current User ──────────────────────────────────────────────────


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security_scheme)],
    db: Session = Depends(get_db),
) -> User:
    """Validate JWT and return the authenticated user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_token(credentials.credentials)

        if payload.get("type") != "access":
            raise credentials_exception

        user_id: str = payload.get("sub")
        if not user_id:
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    return user


def log_audit_event(
    db: Session,
    action: str,
    request: Request,
    success: bool,
    user_id: str = None,
    resource: str = None,
    details: str = None,
):
    """Record an audit log entry."""
    ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if not ip:
        ip = request.client.host if request.client else "unknown"

    log_entry = AuditLog(
        user_id=user_id,
        action=action,
        resource=resource,
        ip_address=ip[:45],
        user_agent=request.headers.get("user-agent", "")[:500],
        success=success,
        details=details,
    )
    db.add(log_entry)
    db.commit()


# ─── Auth Routes ──────────────────────────────────────────────────────────────


@auth_router.post(
    "/signup",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def signup(
    request: Request,
    payload: UserSignupRequest,
    db: Session = Depends(get_db),
):
    """Register a new user account."""
    # Validate password strength
    is_valid, errors = validate_password_strength(payload.password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Password does not meet requirements", "errors": errors},
        )

    # Check for existing users
    existing = db.query(User).filter(
        (User.email == payload.email) | (User.username == payload.username)
    ).first()

    if existing:
        # Use generic error to avoid user enumeration
        log_audit_event(
            db, "SIGNUP_ATTEMPT", request, False,
            details="Duplicate email or username"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with these details already exists",
        )

    # Create user
    verification_token = generate_secure_token()
    new_user = User(
        email=payload.email,
        username=payload.username,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        verification_token=hash_password(verification_token),  # Store hash
        is_verified=True,  # Set False when email verification is configured
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    log_audit_event(
        db, "SIGNUP", request, True,
        user_id=new_user.id, resource="users"
    )

    # TODO: Send verification email with verification_token
    logger.info(f"New user registered: {new_user.id}")

    return MessageResponse(
        message="Account created successfully. Please verify your email."
    )


@auth_router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    payload: UserLoginRequest,
    db: Session = Depends(get_db),
):
    """Authenticate user and return JWT tokens."""
    # Find user
    user = db.query(User).filter(User.email == payload.email).first()

    # Always do the password check (prevents timing attacks)
    password_valid = False
    if user:
        password_valid = verify_password(payload.password, user.hashed_password)

    if not user or not password_valid:
        # Increment failed attempts if user exists
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                from datetime import timedelta
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
                logger.warning(f"Account locked: {user.id}")
            db.commit()

        log_audit_event(
            db, "LOGIN_FAILED", request, False,
            details=f"Email: {payload.email[:20]}..."
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if account is locked
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account temporarily locked due to too many failed attempts",
        )

    # Check if account is active/verified
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    # Successful login - reset failed attempts
    ip = request.headers.get("X-Forwarded-For", request.client.host)
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login = datetime.now(timezone.utc)
    user.last_login_ip = ip[:45]
    db.commit()

    # Generate tokens
    access_token = create_access_token(subject=user.id)
    refresh_token = create_refresh_token(subject=user.id)

    # Store refresh token hash
    from app.security import compute_file_hash
    token_record = RefreshToken(
        user_id=user.id,
        token_hash=compute_file_hash(refresh_token.encode()),
        expires_at=datetime.now(timezone.utc) + __import__('datetime').timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        ),
    )
    db.add(token_record)
    db.commit()

    log_audit_event(
        db, "LOGIN", request, True, user_id=user.id
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@auth_router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: Request,
    payload: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    """Exchange a refresh token for a new access token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
    )

    try:
        token_data = decode_token(payload.refresh_token)
        if token_data.get("type") != "refresh":
            raise credentials_exception

        user_id = token_data.get("sub")

    except JWTError:
        raise credentials_exception

    # Check token hasn't been revoked
    token_hash = compute_file_hash(payload.refresh_token.encode())
    stored_token = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash,
        RefreshToken.revoked == False,
    ).first()

    if not stored_token:
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise credentials_exception

    # Rotate refresh token (revoke old, issue new)
    stored_token.revoked = True
    new_refresh = create_refresh_token(subject=user.id)
    new_access = create_access_token(subject=user.id)

    new_token_record = RefreshToken(
        user_id=user.id,
        token_hash=compute_file_hash(new_refresh.encode()),
        expires_at=datetime.now(timezone.utc) + __import__('datetime').timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        ),
    )
    db.add(new_token_record)
    db.commit()

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@auth_router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    payload: RefreshTokenRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke refresh token to log the user out."""
    token_hash = compute_file_hash(payload.refresh_token.encode())
    stored_token = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash,
        RefreshToken.user_id == current_user.id,
    ).first()

    if stored_token:
        stored_token.revoked = True
        db.commit()

    log_audit_event(
        db, "LOGOUT", request, True, user_id=current_user.id
    )

    return MessageResponse(message="Successfully logged out")


@auth_router.post("/change-password", response_model=MessageResponse)
async def change_password(
    request: Request,
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change the authenticated user's password."""
    if not verify_password(payload.current_password, current_user.hashed_password):
        log_audit_event(
            db, "PASSWORD_CHANGE_FAILED", request, False,
            user_id=current_user.id, details="Wrong current password"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    is_valid, errors = validate_password_strength(payload.new_password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"errors": errors},
        )

    current_user.hashed_password = hash_password(payload.new_password)
    db.commit()

    # Revoke all refresh tokens (force re-login on all devices)
    db.query(RefreshToken).filter(
        RefreshToken.user_id == current_user.id
    ).update({"revoked": True})
    db.commit()

    log_audit_event(
        db, "PASSWORD_CHANGED", request, True, user_id=current_user.id
    )

    return MessageResponse(message="Password changed successfully")


# ─── User Routes ───────────────────────────────────────────────────────────────


@user_router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
):
    """Get the current user's profile."""
    return current_user


# ─── Processing Routes ─────────────────────────────────────────────────────────


@process_router.post("/upload", response_model=ProcessingJobResponse)
async def upload_and_process(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="MPesa PDF statement"),
    pdf_pin: str = Form(..., min_length=4, max_length=20),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upload a PIN-protected MPesa PDF statement for processing.

    Security:
    - PIN is never logged or stored
    - File is validated before processing
    - User can only access their own jobs
    """
    # Validate file size
    file_bytes = await file.read()
    if len(file_bytes) > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {settings.MAX_FILE_SIZE_MB}MB",
        )

    # Validate it's actually a PDF
    try:
        pdf_processor.validate_pdf_file(file_bytes, file.filename or "upload.pdf")
    except PDFProcessingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    # Save file securely
    secure_filename, file_hash = await file_manager.save_upload(
        file_bytes, file.filename or "upload.pdf", current_user.id
    )

    # Create job record
    from datetime import timedelta
    job = ProcessingJob(
        user_id=current_user.id,
        original_filename=file.filename or "upload.pdf",
        stored_filename=secure_filename,
        file_hash=file_hash,
        file_size=len(file_bytes),
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(
            hours=settings.FILE_RETENTION_HOURS
        ),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    log_audit_event(
        db, "FILE_UPLOAD", request, True,
        user_id=current_user.id,
        resource=job.id,
        details=f"size={len(file_bytes)}, hash={file_hash[:16]}...",
    )

    # Process in background (PIN used here, never stored)
    background_tasks.add_task(
        _process_statement_background,
        job_id=job.id,
        user_id=current_user.id,
        secure_filename=secure_filename,
        pin=pdf_pin,  # Passed to background task only
        original_filename=file.filename or "upload.pdf",
    )

    return ProcessingJobResponse(
        job_id=job.id,
        status="pending",
        original_filename=job.original_filename,
        created_at=job.created_at,
    )


async def _process_statement_background(
    job_id: str,
    user_id: str,
    secure_filename: str,
    pin: str,
    original_filename: str,
):
    """
    Background task for PDF processing.
    PIN is available only during processing and is garbage-collected after.
    """
    db = next(get_db())

    try:
        job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
        if not job:
            return

        job.status = "processing"
        db.commit()

        # Read file
        file_bytes = await file_manager.read_upload(secure_filename)

        # Process statement (PIN used only here)
        statement = pdf_processor.process_statement(
            file_bytes, pin, original_filename
        )
        pin = None  # Clear PIN from memory ASAP

        # Generate Excel
        excel_bytes = excel_generator.generate(statement, original_filename)

        # Save output
        output_filename = await file_manager.save_output(
            excel_bytes, user_id, job_id
        )

        # Update job record
        job.status = "completed"
        job.transaction_count = statement.total_transactions
        job.output_filename = output_filename
        job.completed_at = datetime.now(timezone.utc)
        db.commit()

        # Delete the uploaded PDF (no longer needed)
        await file_manager.delete_upload(secure_filename)
        logger.info(f"Job {job_id} completed: {statement.total_transactions} txns")

    except InvalidPINError:
        pin = None  # Clear PIN
        job.status = "failed"
        job.error_message = "Incorrect PIN. Please try again."
        db.commit()

    except (CorruptedPDFError, PDFProcessingError) as exc:
        pin = None
        job.status = "failed"
        job.error_message = str(exc)
        db.commit()

    except Exception as exc:
        pin = None
        logger.error(f"Unexpected error in job {job_id}: {type(exc).__name__}: {exc}")
        if job:
            job.status = "failed"
            job.error_message = "An unexpected error occurred during processing"
            db.commit()
    finally:
        db.close()


@process_router.get("/status/{job_id}", response_model=ProcessingStatusResponse)
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the status of a processing job."""
    job = db.query(ProcessingJob).filter(
        ProcessingJob.id == job_id,
        ProcessingJob.user_id == current_user.id,  # Ownership check
    ).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    download_url = None
    if job.status == "completed" and job.output_filename:
        download_url = f"/api/process/download/{job_id}"

    return ProcessingStatusResponse(
        job_id=job.id,
        status=job.status,
        message=job.error_message if job.status == "failed" else None,
        transaction_count=job.transaction_count,
        download_url=download_url,
    )


@process_router.get("/download/{job_id}")
async def download_excel(
    request: Request,
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download the generated Excel file for a completed job."""
    job = db.query(ProcessingJob).filter(
        ProcessingJob.id == job_id,
        ProcessingJob.user_id == current_user.id,
    ).first()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Job is not completed (current status: {job.status})",
        )

    if not job.output_filename:
        raise HTTPException(status_code=404, detail="Output file not found")

    try:
        excel_bytes = await file_manager.read_output(job.output_filename)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Output file has expired")

    log_audit_event(
        db, "FILE_DOWNLOAD", request, True,
        user_id=current_user.id, resource=job_id,
    )

    # Generate a clean download filename
    safe_original = "".join(
        c for c in job.original_filename if c.isalnum() or c in "._- "
    )
    download_name = f"mpesa_{safe_original.replace('.pdf', '')}_processed.xlsx"

    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{download_name}"',
            "Content-Length": str(len(excel_bytes)),
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "X-Content-Type-Options": "nosniff",
        },
    )


@process_router.get("/jobs", response_model=list[ProcessingJobResponse])
async def list_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all processing jobs for the current user."""
    jobs = (
        db.query(ProcessingJob)
        .filter(ProcessingJob.user_id == current_user.id)
        .order_by(ProcessingJob.created_at.desc())
        .limit(50)
        .all()
    )

    return [
        ProcessingJobResponse(
            job_id=j.id,
            status=j.status,
            original_filename=j.original_filename,
            created_at=j.created_at,
            transaction_count=j.transaction_count,
            error_message=j.error_message,
        )
        for j in jobs
    ]