"""Tests for PDF processing functionality."""
import io
import pytest
from unittest.mock import MagicMock, patch
from app.services.pdf_processor import PDFProcessor, InvalidPINError, PDFProcessingError


class TestPDFProcessor:
    def setup_method(self):
        self.processor = PDFProcessor()

    def test_validate_pdf_file_valid(self):
        """Valid PDF headers should pass validation."""
        fake_pdf = b"%PDF-1.4 fake content"
        with patch("pikepdf.open"):
            self.processor.validate_pdf_file(fake_pdf, "test.pdf")

    def test_validate_pdf_file_invalid_extension(self):
        """Non-PDF files should be rejected."""
        with pytest.raises(PDFProcessingError, match="Only PDF files"):
            self.processor.validate_pdf_file(b"some content", "file.docx")

    def test_validate_pdf_file_invalid_header(self):
        """Files without PDF magic bytes should be rejected."""
        with pytest.raises(PDFProcessingError, match="valid PDF"):
            self.processor.validate_pdf_file(b"Not a PDF file", "file.pdf")

    def test_decrypt_pdf_wrong_pin(self):
        """Wrong PIN should raise InvalidPINError."""
        import pikepdf
        with patch("pikepdf.open", side_effect=pikepdf.PasswordError("wrong")):
            with pytest.raises(InvalidPINError):
                self.processor.decrypt_pdf(b"%PDF-fake", "wrongpin")

    def test_is_pdf_encrypted_returns_true(self):
        """Encrypted PDF detection."""
        import pikepdf
        with patch("pikepdf.open", side_effect=pikepdf.PasswordError("enc")):
            assert self.processor.is_pdf_encrypted(b"fake") is True

    def test_is_pdf_encrypted_returns_false(self):
        """Non-encrypted PDF detection."""
        with patch("pikepdf.open") as mock_open:
            mock_open.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_open.return_value.__exit__ = MagicMock(return_value=False)
            assert self.processor.is_pdf_encrypted(b"fake") is False