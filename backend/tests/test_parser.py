"""Tests for MPesa statement parsing."""
import pytest
from app.services.statement_parser import StatementParser


class TestStatementParser:
    def setup_method(self):
        self.parser = StatementParser()

    def test_parse_basic_transaction(self):
        """Parser should extract basic transaction data."""
        sample_text = """
Customer Name: John Doe
Statement Period: 01/01/2024 To 31/01/2024

Receipt No | Completion Time | Details | Status | Paid In | Withdrawn | Cost | Balance
RGH12345AB 01/01/2024 9:00 AM Send Money to Jane 254712345678 Completed - 500.00 5.00 2,495.00
QWE98765ZX 02/01/2024 10:30 AM Received from Bob 254798765432 Completed 1,000.00 - - 3,495.00
        """
        result = self.parser.parse(sample_text)
        assert result.account_holder == "John Doe"
        assert result.period_from == "01/01/2024"
        assert result.period_to == "31/01/2024"

    def test_parse_empty_text(self):
        """Empty text should return zero transactions."""
        result = self.parser.parse("")
        assert result.total_transactions == 0

    def test_categorize_transaction(self):
        """Transaction categorization should work correctly."""
        assert self.parser._categorize_transaction("Send Money to John") == "Send Money"
        assert self.parser._categorize_transaction("Pay Bill KCB Bank") == "Pay Bill"
        assert self.parser._categorize_transaction("Buy Goods Naivas") == "Buy Goods"
        assert self.parser._categorize_transaction("Airtime Purchase") == "Airtime"

    def test_extract_phone_number(self):
        """Phone numbers should be extracted correctly."""
        text = "Account: +254712345678 registered"
        assert self.parser._extract_phone_number(text) == "+254712345678"

    def test_parse_amounts(self):
        """Amount extraction should handle formatted numbers."""
        text = "REC123456AB 01/01/2024 Details Completed 1,500.00 0.00 10.00 5,490.00"
        amounts = self.parser._extract_amounts_from_block(text)
        assert "balance" in amounts