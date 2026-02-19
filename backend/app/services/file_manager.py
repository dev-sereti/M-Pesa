"""
File Manager: Secure handling of uploaded and generated files.
Implements automatic cleanup, access control, and secure storage.
"""

import asyncio
import logging
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import aiofiles

from app.config import get_settings
from app.security import compute_file_hash, generate_secure_filename

settings = get_settings()
logger = logging.getLogger(__name__)


class FileManager:
    """Manages the lifecycle of uploaded PDFs and generated Excel files."""

    def __init__(self):
        self.upload_dir = Path(settings.UPLOAD_DIR)
        self.output_dir = Path(settings.OUTPUT_DIR)
        self._ensure_directories()

    def _ensure_directories(self):
        """Create storage directories with restricted permissions."""
        for directory in [self.upload_dir, self.output_dir]:
            directory.mkdir(parents=True, exist_ok=True)
            # Restrict to owner read/write/execute only
            os.chmod(directory, 0o700)

    async def save_upload(
        self,
        file_bytes: bytes,
        original_filename: str,
        user_id: str,
    ) -> tuple[str, str]:
        """
        Securely save an uploaded file.

        Returns:
            Tuple of (secure_filename, file_hash)
        """
        secure_name = generate_secure_filename(original_filename, user_id)
        file_path = self.upload_dir / secure_name
        file_hash = compute_file_hash(file_bytes)

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(file_bytes)

        # Restrict file permissions to owner-only
        os.chmod(file_path, 0o600)

        logger.info(
            f"Saved upload: {secure_name} ({len(file_bytes)} bytes, "
            f"hash: {file_hash[:16]}...)"
        )
        return secure_name, file_hash

    async def read_upload(self, secure_filename: str) -> bytes:
        """Read an uploaded file. Validates path to prevent traversal."""
        file_path = self._safe_path(self.upload_dir, secure_filename)

        async with aiofiles.open(file_path, "rb") as f:
            return await f.read()

    async def save_output(
        self,
        excel_bytes: bytes,
        user_id: str,
        job_id: str,
    ) -> str:
        """Save a generated Excel file and return its filename."""
        filename = f"mpesa_statement_{job_id[:8]}_{user_id[:8]}.xlsx"
        file_path = self.output_dir / filename

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(excel_bytes)

        os.chmod(file_path, 0o600)
        logger.info(f"Saved output: {filename}")
        return filename

    async def read_output(self, filename: str) -> bytes:
        """Read a generated Excel output file."""
        file_path = self._safe_path(self.output_dir, filename)

        async with aiofiles.open(file_path, "rb") as f:
            return await f.read()

    async def delete_file(self, directory: Path, filename: str) -> bool:
        """Securely delete a file."""
        try:
            file_path = self._safe_path(directory, filename)
            if file_path.exists():
                # Overwrite before deletion (basic secure delete)
                size = file_path.stat().st_size
                async with aiofiles.open(file_path, "wb") as f:
                    await f.write(b"\x00" * size)
                file_path.unlink()
                logger.info(f"Deleted file: {filename}")
                return True
        except Exception as exc:
            logger.error(f"Failed to delete {filename}: {exc}")
        return False

    async def delete_upload(self, secure_filename: str) -> bool:
        """Delete an uploaded PDF file."""
        return await self.delete_file(self.upload_dir, secure_filename)

    async def delete_output(self, filename: str) -> bool:
        """Delete a generated Excel file."""
        return await self.delete_file(self.output_dir, filename)

    async def cleanup_expired_files(self, retention_hours: int = None):
        """
        Remove files older than the retention period.
        Should be called by a scheduled task.
        """
        hours = retention_hours or settings.FILE_RETENTION_HOURS
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        for directory in [self.upload_dir, self.output_dir]:
            for file_path in directory.iterdir():
                if file_path.is_file():
                    mtime = datetime.fromtimestamp(
                        file_path.stat().st_mtime, tz=timezone.utc
                    )
                    if mtime < cutoff:
                        try:
                            file_path.unlink()
                            logger.info(f"Cleaned up expired file: {file_path.name}")
                        except Exception as exc:
                            logger.error(f"Cleanup failed for {file_path.name}: {exc}")

    def _safe_path(self, base_dir: Path, filename: str) -> Path:
        """
        Validate path to prevent directory traversal attacks.
        Only allows files directly within the base directory.
        """
        # Sanitize filename
        safe_name = Path(filename).name  # Strip any path components
        full_path = (base_dir / safe_name).resolve()

        # Ensure the resolved path is within the base directory
        if not str(full_path).startswith(str(base_dir.resolve())):
            raise PermissionError(
                f"Access denied: path traversal detected for '{filename}'"
            )

        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {safe_name}")

        return full_path