"""
MPesa Statement Parser: Extracts structured transaction data from raw PDF text.
Handles various MPesa statement formats with robust regex patterns.
"""

import logging
import re
from datetime import datetime
from typing import List, Optional, Tuple

from app.models.schemas import StatementSummary, TransactionRecord

logger = logging.getLogger(__name__)


class StatementParser:
    """
    Parses raw text extracted from MPesa PDF statements into structured data.

    MPesa statement format typically contains:
    - Header with account info, period, etc.
    - Transaction table with columns:
      Receipt No | Completion Time | Details | Transaction Status |
      Paid In | Withdrawn | Transaction Cost | Balance
    """

    # ─── Regex Patterns ────────────────────────────────────────────────────────

    # MPesa receipt numbers: 10 alphanumeric characters starting with letters
    RECEIPT_PATTERN = re.compile(r"\b([A-Z0-9]{10})\b")

    # Date/time patterns used in MPesa statements
    DATETIME_PATTERN = re.compile(
        r"(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}\s*(?:AM|PM)?)"
        r"|(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})",
        re.IGNORECASE,
    )

    # Money amounts: optional leading minus, digits with optional comma separators
    AMOUNT_PATTERN = re.compile(r"-?[\d,]+\.?\d*")

    # Phone number pattern
    PHONE_PATTERN = re.compile(r"(?:\+254|0)[17]\d{8}")

    # Account holder name (after "Customer Name:" or similar)
    CUSTOMER_NAME_PATTERN = re.compile(
        r"(?:Customer\s+Name|Name|Account\s+Holder)[:\s]+([A-Za-z\s]+?)(?:\n|$)",
        re.IGNORECASE,
    )

    # Statement period
    PERIOD_PATTERN = re.compile(
        r"(?:Statement\s+Period|Period|From)[:\s]+"
        r"(\d{1,2}/\d{1,2}/\d{4})"
        r"\s*(?:To|–|-)\s*"
        r"(\d{1,2}/\d{1,2}/\d{4})",
        re.IGNORECASE,
    )

    # Transaction status values
    TRANSACTION_STATUSES = {
        "completed",
        "failed",
        "reversed",
        "pending",
        "cancelled",
    }

    def parse(self, raw_text: str) -> StatementSummary:
        """
        Parse raw PDF text into a StatementSummary.

        Args:
            raw_text: Full text extracted from the PDF

        Returns:
            StatementSummary with all parsed data
        """
        # Normalize text: fix common PDF extraction artifacts
        normalized = self._normalize_text(raw_text)

        # Extract header information
        account_holder = self._extract_account_holder(normalized)
        phone_number = self._extract_phone_number(normalized)
        period_from, period_to = self._extract_period(normalized)

        # Extract transactions
        transactions = self._extract_transactions(normalized)

        if not transactions:
            logger.warning("No transactions found. Attempting fallback parsing...")
            transactions = self._fallback_parse(normalized)

        # Calculate summary statistics
        total_paid_in = sum(t.paid_in or 0.0 for t in transactions)
        total_withdrawn = sum(t.withdrawn or 0.0 for t in transactions)
        total_charges = sum(t.transaction_cost or 0.0 for t in transactions)

        return StatementSummary(
            period_from=period_from,
            period_to=period_to,
            account_holder=account_holder,
            phone_number=phone_number,
            total_transactions=len(transactions),
            total_paid_in=round(total_paid_in, 2),
            total_withdrawn=round(total_withdrawn, 2),
            total_charges=round(total_charges, 2),
            transactions=transactions,
        )

    def _normalize_text(self, text: str) -> str:
        """Clean and normalize extracted PDF text."""
        # Fix common PDF extraction issues
        lines = text.split("\n")
        cleaned_lines = []

        for line in lines:
            # Remove excessive whitespace
            line = re.sub(r"\s{3,}", "  ", line.strip())
            # Skip empty lines and page headers
            if line and not re.match(r"^-{3,}\s*PAGE\s+\d+\s*-{3,}$", line):
                cleaned_lines.append(line)

        return "\n".join(cleaned_lines)

    def _extract_account_holder(self, text: str) -> Optional[str]:
        """Extract the account holder's name from the statement."""
        match = self.CUSTOMER_NAME_PATTERN.search(text)
        if match:
            name = match.group(1).strip()
            # Validate it looks like a name (2+ words, all alpha)
            if len(name.split()) >= 1 and all(
                part.isalpha() for part in name.split()
            ):
                return name.title()
        return None

    def _extract_phone_number(self, text: str) -> Optional[str]:
        """Extract MPesa phone number from the statement."""
        match = self.PHONE_PATTERN.search(text)
        if match:
            return match.group(0)
        return None

    def _extract_period(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract statement period (from date, to date)."""
        match = self.PERIOD_PATTERN.search(text)
        if match:
            return match.group(1), match.group(2)
        return None, None

    def _extract_transactions(self, text: str) -> List[TransactionRecord]:
        """
        Main transaction extraction using pattern-based line parsing.
        Handles the standard MPesa statement table format.
        """
        transactions = []
        lines = text.split("\n")

        i = 0
        while i < len(lines):
            line = lines[i]

            # Look for lines starting with an MPesa receipt number
            receipt_match = self.RECEIPT_PATTERN.match(line.strip())

            if receipt_match and self._looks_like_transaction_start(line):
                # Collect the full transaction (may span multiple lines)
                transaction_lines = [line]

                # Check if next lines are continuation of same transaction
                j = i + 1
                while j < len(lines) and j < i + 5:
                    next_line = lines[j].strip()
                    if (
                        next_line
                        and not self.RECEIPT_PATTERN.match(next_line)
                        and not self._is_header_line(next_line)
                    ):
                        transaction_lines.append(next_line)
                        j += 1
                    else:
                        break

                transaction = self._parse_transaction_block(
                    "\n".join(transaction_lines)
                )
                if transaction:
                    transactions.append(transaction)

                i = j
            else:
                i += 1

        return transactions

    def _looks_like_transaction_start(self, line: str) -> bool:
        """Check if a line appears to be the start of a transaction record."""
        # Must contain a receipt number and at least one date or amount
        has_receipt = bool(self.RECEIPT_PATTERN.search(line))
        has_date = bool(self.DATETIME_PATTERN.search(line))
        has_amount = bool(re.search(r"\d{1,3}(?:,\d{3})*\.?\d{0,2}", line))
        return has_receipt and (has_date or has_amount)

    def _is_header_line(self, line: str) -> bool:
        """Detect table header lines to skip."""
        header_keywords = [
            "receipt", "completion", "details", "status",
            "paid in", "withdrawn", "cost", "balance",
            "transaction",
        ]
        lower_line = line.lower()
        return any(kw in lower_line for kw in header_keywords) and not any(
            char.isdigit() for char in line
        )

    def _parse_transaction_block(self, block: str) -> Optional[TransactionRecord]:
        """Parse a single transaction block into a TransactionRecord."""
        try:
            # Flatten the block for parsing
            flat = " ".join(block.split())

            # Extract receipt number (first 10-char alphanumeric)
            receipt_match = self.RECEIPT_PATTERN.search(flat)
            if not receipt_match:
                return None
            receipt_number = receipt_match.group(1)

            # Extract datetime
            dt_match = self.DATETIME_PATTERN.search(flat)
            completion_time = dt_match.group(0).strip() if dt_match else "Unknown"

            # Extract all money amounts
            amounts = self._extract_amounts_from_block(flat)

            # Extract transaction status
            status = self._extract_status(flat)

            # Extract details (everything between receipt/date and status/amounts)
            details = self._extract_details(flat, receipt_number, completion_time)

            return TransactionRecord(
                receipt_number=receipt_number,
                completion_time=completion_time,
                details=details or "N/A",
                transaction_status=status,
                paid_in=amounts.get("paid_in"),
                withdrawn=amounts.get("withdrawn"),
                transaction_cost=amounts.get("cost"),
                balance=amounts.get("balance"),
            )

        except Exception as exc:
            logger.debug(f"Could not parse transaction block: {exc}")
            return None

    def _extract_amounts_from_block(self, text: str) -> dict:
        """
        Extract monetary amounts from a transaction line.

        MPesa statement columns (right side):
        Paid In | Withdrawn | Transaction Cost | Balance
        """
        # Find all number sequences that look like amounts
        amount_pattern = re.compile(r"\b(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\b")
        all_amounts = amount_pattern.findall(text)

        result = {}
        numeric_amounts = []

        for amount_str in all_amounts:
            try:
                value = float(amount_str.replace(",", ""))
                if 0.01 <= value <= 10_000_000:  # Reasonable MPesa range
                    numeric_amounts.append(value)
            except ValueError:
                continue

        # MPesa format: Paid In | Withdrawn | Cost | Balance
        # Typically the last 4 amounts in a row
        if len(numeric_amounts) >= 4:
            result["paid_in"] = numeric_amounts[-4] if numeric_amounts[-4] > 0 else None
            result["withdrawn"] = (
                numeric_amounts[-3] if numeric_amounts[-3] > 0 else None
            )
            result["cost"] = numeric_amounts[-2] if numeric_amounts[-2] > 0 else None
            result["balance"] = numeric_amounts[-1]
        elif len(numeric_amounts) >= 2:
            result["balance"] = numeric_amounts[-1]
            # Guess whether it's credit or debit from context
            if "paid in" in text.lower() or "receive" in text.lower():
                result["paid_in"] = numeric_amounts[-2]
            else:
                result["withdrawn"] = numeric_amounts[-2]

        return result

    def _extract_status(self, text: str) -> str:
        """Extract transaction status from text."""
        lower_text = text.lower()
        for status in self.TRANSACTION_STATUSES:
            if status in lower_text:
                return status.title()
        return "Completed"  # Default for MPesa (successful transactions are listed)

    def _extract_details(
        self,
        text: str,
        receipt_number: str,
        completion_time: str,
    ) -> str:
        """Extract the human-readable transaction details/description."""
        # Remove receipt number and time from the text
        detail_text = text.replace(receipt_number, "").strip()
        if completion_time != "Unknown":
            detail_text = detail_text.replace(completion_time, "").strip()

        # Remove amount patterns to isolate the description
        detail_text = re.sub(r"\b\d{1,3}(?:,\d{3})*(?:\.\d{2})?\b", "", detail_text)
        detail_text = re.sub(r"\s{2,}", " ", detail_text).strip()

        # Remove common status words
        for status in self.TRANSACTION_STATUSES:
            detail_text = re.sub(status, "", detail_text, flags=re.IGNORECASE)

        # Keep only meaningful content (at least 5 chars)
        detail_text = detail_text.strip(" .|,-")
        return detail_text[:200] if len(detail_text) > 5 else "Transaction"

    def _fallback_parse(self, text: str) -> List[TransactionRecord]:
        """
        Fallback parser for non-standard statement formats.
        Uses more aggressive pattern matching.
        """
        logger.info("Using fallback parser")
        transactions = []

        # Look for any line with a receipt-like pattern and numbers
        for line in text.split("\n"):
            if self.RECEIPT_PATTERN.search(line) and re.search(r"\d+\.\d{2}", line):
                transaction = self._parse_transaction_block(line)
                if transaction:
                    transactions.append(transaction)

        return transactions