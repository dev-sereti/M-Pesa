"""
PDF Processing Service: Handles encrypted MPesa PDF statements.
Security: PINs are never logged or stored; files are processed in memory.
"""

import io
import logging
import re
import tempfile
from pathlib import Path
from typing import Optional, Tuple

import pikepdf
import pdfplumber

from app.models.schemas import StatementSummary, TransactionRecord
from app.services.statement_parser import StatementParser

logger = logging.getLogger(__name__)


class PDFProcessingError(Exception):
    """Raised when PDF processing fails."""
    pass


class InvalidPINError(PDFProcessingError):
    """Raised when the provided PIN is incorrect."""
    pass


class CorruptedPDFError(PDFProcessingError):
    """Raised when the PDF file is corrupted or invalid."""
    pass


class PDFProcessor:
    """
    Handles secure extraction of text from PIN-protected MPesa PDF statements.

    Security considerations:
    - PINs are never logged or persisted
    - Files are processed in temporary memory buffers
    - Temporary files are securely deleted after processing
    """

    def __init__(self):
        self.parser = StatementParser()

    def is_pdf_encrypted(self, file_bytes: bytes) -> bool:
        """Check if a PDF file is encrypted without decrypting it."""
        try:
            with pikepdf.open(io.BytesIO(file_bytes)) as pdf:
                return False  # Opened without password → not encrypted
        except pikepdf.PasswordError:
            return True
        except Exception as exc:
            logger.warning(f"Could not check encryption status: {exc}")
            return False

    def decrypt_pdf(self, file_bytes: bytes, pin: str) -> bytes:
        """
        Decrypt an encrypted PDF using the provided PIN.

        Args:
            file_bytes: Raw PDF file bytes
            pin: PDF password/PIN (never logged)

        Returns:
            Decrypted PDF as bytes

        Raises:
            InvalidPINError: If PIN is incorrect
            CorruptedPDFError: If PDF is malformed
        """
        output_buffer = io.BytesIO()

        try:
            with pikepdf.open(io.BytesIO(file_bytes), password=pin) as pdf:
                # Remove encryption and write to buffer
                pdf.save(output_buffer)
                output_buffer.seek(0)
                return output_buffer.read()

        except pikepdf.PasswordError:
            # Don't include the PIN in error messages
            raise InvalidPINError(
                "The provided PIN is incorrect. Please check and try again."
            )
        except pikepdf.PdfError as exc:
            raise CorruptedPDFError(f"PDF file appears to be corrupted: {exc}") from exc
        except Exception as exc:
            logger.error(f"Unexpected error during PDF decryption: {type(exc).__name__}")
            raise PDFProcessingError("Failed to process PDF file") from exc

    def extract_text(self, pdf_bytes: bytes) -> str:
        """
        Extract all text content from a decrypted PDF.

        Args:
            pdf_bytes: Decrypted PDF bytes

        Returns:
            Extracted text as a single string
        """
        full_text = []

        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                logger.info(f"Processing PDF with {len(pdf.pages)} pages")

                for page_num, page in enumerate(pdf.pages, start=1):
                    try:
                        # Extract text with layout preservation
                        text = page.extract_text(
                            x_tolerance=3,
                            y_tolerance=3,
                            layout=False,
                        )
                        if text:
                            full_text.append(f"--- PAGE {page_num} ---\n{text}")

                        # Also try table extraction for structured data
                        tables = page.extract_tables()
                        if tables:
                            for table in tables:
                                for row in table:
                                    if row and any(cell for cell in row if cell):
                                        clean_row = [
                                            cell.strip() if cell else ""
                                            for cell in row
                                        ]
                                        full_text.append("|".join(clean_row))

                    except Exception as exc:
                        logger.warning(
                            f"Could not extract text from page {page_num}: {exc}"
                        )
                        continue

        except Exception as exc:
            raise PDFProcessingError(f"Failed to extract PDF text: {exc}") from exc

        return "\n".join(full_text)

    def process_statement(
        self,
        file_bytes: bytes,
        pin: str,
        original_filename: str = "statement.pdf",
    ) -> StatementSummary:
        """
        Full pipeline: decrypt → extract text → parse transactions.

        Args:
            file_bytes: Raw PDF bytes
            pin: Statement PIN (handled securely, never logged)
            original_filename: Used only for logging purposes

        Returns:
            Parsed statement summary with transactions

        Raises:
            InvalidPINError, CorruptedPDFError, PDFProcessingError
        """
        logger.info(f"Starting processing for file: {original_filename}")

        # Step 1: Check if encrypted
        is_encrypted = self.is_pdf_encrypted(file_bytes)
        logger.info(f"PDF encrypted: {is_encrypted}")

        # Step 2: Decrypt if necessary
        if is_encrypted:
            decrypted_bytes = self.decrypt_pdf(file_bytes, pin)
        else:
            decrypted_bytes = file_bytes
            logger.warning("PDF is not encrypted - processing as-is")

        # Step 3: Extract text
        raw_text = self.extract_text(decrypted_bytes)

        if not raw_text.strip():
            raise PDFProcessingError(
                "No text could be extracted from the PDF. "
                "The file may be image-based or corrupted."
            )

        logger.info(f"Extracted {len(raw_text)} characters of text")

        # Step 4: Parse transactions
        statement = self.parser.parse(raw_text)

        logger.info(
            f"Processing complete. Found {statement.total_transactions} transactions."
        )

        return statement

    def validate_pdf_file(self, file_bytes: bytes, filename: str) -> None:
        """
        Validate that the uploaded file is a genuine PDF.

        Args:
            file_bytes: File contents
            filename: Original filename for extension check

        Raises:
            PDFProcessingError: If file is not a valid PDF
        """
        # Check file extension
        if not filename.lower().endswith(".pdf"):
            raise PDFProcessingError("Only PDF files are accepted")

        # Check PDF magic bytes (%PDF-)
        if not file_bytes.startswith(b"%PDF-"):
            raise PDFProcessingError(
                "File does not appear to be a valid PDF (invalid header)"
            )

        # Try to open with pikepdf to verify structure
        try:
            with pikepdf.open(io.BytesIO(file_bytes)) as _:
                pass  # Valid PDF
        except pikepdf.PasswordError:
            pass  # Encrypted but valid
        except pikepdf.PdfError as exc:
            raise CorruptedPDFError(f"PDF validation failed: {exc}") from exc