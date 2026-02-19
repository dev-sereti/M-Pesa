"""
Excel Report Generator: Creates formatted Excel workbooks from parsed MPesa data.
"""

import io
import logging
from datetime import datetime, timezone
from typing import Optional

import openpyxl
from openpyxl.styles import (
    Alignment,
    Border,
    Font,
    PatternFill,
    Side,
)
from openpyxl.utils import get_column_letter

from app.models.schemas import StatementSummary

logger = logging.getLogger(__name__)

# ─── Color Palette ────────────────────────────────────────────────────────────
MPESA_GREEN = "4CAF50"
HEADER_BG = "1B5E20"
SUBHEADER_BG = "388E3C"
ALT_ROW_BG = "F1F8E9"
WHITE = "FFFFFF"
DARK_GRAY = "263238"
CREDIT_COLOR = "1B5E20"
DEBIT_COLOR = "B71C1C"
NEUTRAL_COLOR = "37474F"


class ExcelGenerator:
    """Generates formatted Excel reports from parsed MPesa statement data."""

    def generate(
        self,
        summary: StatementSummary,
        original_filename: str = "statement",
    ) -> bytes:
        """
        Create a formatted Excel workbook from statement data.

        Args:
            summary: Parsed statement summary
            original_filename: Used for sheet naming

        Returns:
            Excel file as bytes
        """
        wb = openpyxl.Workbook()
        wb.remove(wb.active)  # Remove default sheet

        # Create sheets
        self._create_summary_sheet(wb, summary)
        self._create_transactions_sheet(wb, summary)
        self._create_charts_sheet(wb, summary)

        # Save to bytes
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer.read()

    def _create_summary_sheet(self, wb: openpyxl.Workbook, summary: StatementSummary):
        """Create the Summary overview sheet."""
        ws = wb.create_sheet("Summary", 0)

        # ─── Header ───────────────────────────────────────────────────────────
        ws.merge_cells("A1:D1")
        title_cell = ws["A1"]
        title_cell.value = "MPesa Statement Summary"
        title_cell.font = Font(
            name="Calibri", size=18, bold=True, color=WHITE
        )
        title_cell.fill = PatternFill(
            start_color=HEADER_BG, end_color=HEADER_BG, fill_type="solid"
        )
        title_cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 40

        # Generated timestamp
        ws.merge_cells("A2:D2")
        ts_cell = ws["A2"]
        ts_cell.value = (
            f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        )
        ts_cell.font = Font(name="Calibri", size=10, italic=True, color=DARK_GRAY)
        ts_cell.alignment = Alignment(horizontal="center")
        ts_cell.fill = PatternFill(
            start_color="E8F5E9", end_color="E8F5E9", fill_type="solid"
        )

        # ─── Account Information ───────────────────────────────────────────────
        row = 4
        self._write_section_header(ws, row, "Account Information", "A", "D")
        row += 1

        info_data = [
            ("Account Holder", summary.account_holder or "N/A"),
            ("Phone Number", summary.phone_number or "N/A"),
            ("Statement From", summary.period_from or "N/A"),
            ("Statement To", summary.period_to or "N/A"),
        ]

        for label, value in info_data:
            self._write_key_value_row(ws, row, label, value)
            row += 1

        # ─── Financial Summary ─────────────────────────────────────────────────
        row += 1
        self._write_section_header(ws, row, "Financial Summary", "A", "D")
        row += 1

        financial_data = [
            ("Total Transactions", summary.total_transactions, "count"),
            ("Total Money In (KES)", summary.total_paid_in, "currency"),
            ("Total Money Out (KES)", summary.total_withdrawn, "currency"),
            ("Total Charges (KES)", summary.total_charges, "currency"),
            (
                "Net Balance Change (KES)",
                summary.total_paid_in - summary.total_withdrawn,
                "currency",
            ),
        ]

        for label, value, fmt in financial_data:
            self._write_financial_row(ws, row, label, value, fmt)
            row += 1

        # ─── Column Widths ────────────────────────────────────────────────────
        ws.column_dimensions["A"].width = 30
        ws.column_dimensions["B"].width = 25
        ws.column_dimensions["C"].width = 20
        ws.column_dimensions["D"].width = 20

    def _create_transactions_sheet(
        self, wb: openpyxl.Workbook, summary: StatementSummary
    ):
        """Create the detailed transactions sheet."""
        ws = wb.create_sheet("Transactions", 1)

        # ─── Headers ──────────────────────────────────────────────────────────
        headers = [
            "No.",
            "Receipt Number",
            "Completion Time",
            "Details",
            "Status",
            "Paid In (KES)",
            "Withdrawn (KES)",
            "Transaction Cost (KES)",
            "Balance (KES)",
        ]

        header_fill = PatternFill(
            start_color=HEADER_BG, end_color=HEADER_BG, fill_type="solid"
        )
        header_font = Font(name="Calibri", size=11, bold=True, color=WHITE)
        header_alignment = Alignment(
            horizontal="center", vertical="center", wrap_text=True
        )

        thin_border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        )

        for col_num, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_num, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
            cell.border = thin_border

        ws.row_dimensions[1].height = 35
        ws.freeze_panes = "A2"  # Freeze header row

        # ─── Transaction Rows ──────────────────────────────────────────────────
        alt_fill = PatternFill(
            start_color=ALT_ROW_BG, end_color=ALT_ROW_BG, fill_type="solid"
        )
        white_fill = PatternFill(
            start_color=WHITE, end_color=WHITE, fill_type="solid"
        )

        for row_num, txn in enumerate(summary.transactions, start=2):
            is_alt = (row_num % 2 == 0)
            row_fill = alt_fill if is_alt else white_fill

            row_data = [
                row_num - 1,
                txn.receipt_number,
                txn.completion_time,
                txn.details,
                txn.transaction_status,
                txn.paid_in,
                txn.withdrawn,
                txn.transaction_cost,
                txn.balance,
            ]

            for col_num, value in enumerate(row_data, start=1):
                cell = ws.cell(row=row_num, column=col_num, value=value)
                cell.fill = row_fill
                cell.border = thin_border
                cell.font = Font(name="Calibri", size=10)

                # Format monetary columns
                if col_num in (6, 7, 8, 9) and value is not None:
                    cell.number_format = '#,##0.00'
                    cell.alignment = Alignment(horizontal="right")

                    # Color credit green, debit red
                    if col_num == 6 and value and value > 0:  # Paid In
                        cell.font = Font(
                            name="Calibri", size=10, color=CREDIT_COLOR, bold=True
                        )
                    elif col_num == 7 and value and value > 0:  # Withdrawn
                        cell.font = Font(
                            name="Calibri", size=10, color=DEBIT_COLOR, bold=True
                        )
                elif col_num == 1:
                    cell.alignment = Alignment(horizontal="center")
                elif col_num == 5:  # Status
                    cell.alignment = Alignment(horizontal="center")
                    status = str(value).lower()
                    if status == "completed":
                        cell.font = Font(
                            name="Calibri", size=10, color=CREDIT_COLOR, bold=True
                        )
                    elif status in ("failed", "reversed"):
                        cell.font = Font(
                            name="Calibri", size=10, color=DEBIT_COLOR, bold=True
                        )
                else:
                    cell.alignment = Alignment(
                        horizontal="left", wrap_text=True
                    )

        # ─── Totals Row ────────────────────────────────────────────────────────
        if summary.transactions:
            total_row = len(summary.transactions) + 2
            ws.cell(row=total_row, column=1, value="TOTALS").font = Font(
                bold=True, name="Calibri", size=10
            )

            totals_fill = PatternFill(
                start_color=SUBHEADER_BG, end_color=SUBHEADER_BG, fill_type="solid"
            )
            totals_font = Font(name="Calibri", size=10, bold=True, color=WHITE)

            for col in range(1, len(headers) + 1):
                cell = ws.cell(row=total_row, column=col)
                cell.fill = totals_fill
                cell.font = totals_font
                cell.border = thin_border

            # Sum formulas
            last_data_row = total_row - 1
            ws.cell(
                row=total_row, column=6,
                value=f"=SUM(F2:F{last_data_row})"
            ).number_format = '#,##0.00'
            ws.cell(
                row=total_row, column=7,
                value=f"=SUM(G2:G{last_data_row})"
            ).number_format = '#,##0.00'
            ws.cell(
                row=total_row, column=8,
                value=f"=SUM(H2:H{last_data_row})"
            ).number_format = '#,##0.00'

            for col in (6, 7, 8):
                ws.cell(row=total_row, column=col).alignment = Alignment(
                    horizontal="right"
                )

        # ─── Column Widths ────────────────────────────────────────────────────
        column_widths = [8, 18, 22, 45, 14, 18, 18, 22, 18]
        for i, width in enumerate(column_widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = width

        ws.row_dimensions[1].height = 40
        # Auto-fit row heights for data rows
        for row in range(2, len(summary.transactions) + 2):
            ws.row_dimensions[row].height = 20

    def _create_charts_sheet(
        self, wb: openpyxl.Workbook, summary: StatementSummary
    ):
        """Create a statistics/charts data sheet."""
        ws = wb.create_sheet("Statistics", 2)

        ws["A1"] = "Transaction Statistics"
        ws["A1"].font = Font(name="Calibri", size=14, bold=True, color=DARK_GRAY)
        ws.merge_cells("A1:C1")

        # Category breakdown
        categories: dict = {}
        for txn in summary.transactions:
            cat = self._categorize_transaction(txn.details)
            if cat not in categories:
                categories[cat] = {"count": 0, "total_in": 0.0, "total_out": 0.0}
            categories[cat]["count"] += 1
            categories[cat]["total_in"] += txn.paid_in or 0.0
            categories[cat]["total_out"] += txn.withdrawn or 0.0

        ws["A3"] = "Category"
        ws["B3"] = "Count"
        ws["C3"] = "Total In (KES)"
        ws["D3"] = "Total Out (KES)"

        for col, header in [("A", "Category"), ("B", "Count"),
                             ("C", "Total In (KES)"), ("D", "Total Out (KES)")]:
            cell = ws[f"{col}3"]
            cell.value = header
            cell.font = Font(bold=True, name="Calibri", color=WHITE)
            cell.fill = PatternFill(
                start_color=HEADER_BG, end_color=HEADER_BG, fill_type="solid"
            )

        for row, (cat, data) in enumerate(categories.items(), start=4):
            ws.cell(row=row, column=1, value=cat)
            ws.cell(row=row, column=2, value=data["count"])
            ws.cell(
                row=row, column=3, value=round(data["total_in"], 2)
            ).number_format = '#,##0.00'
            ws.cell(
                row=row, column=4, value=round(data["total_out"], 2)
            ).number_format = '#,##0.00'

        ws.column_dimensions["A"].width = 30
        ws.column_dimensions["B"].width = 12
        ws.column_dimensions["C"].width = 20
        ws.column_dimensions["D"].width = 20

    def _categorize_transaction(self, details: str) -> str:
        """Categorize a transaction based on its details string."""
        details_lower = details.lower()
        categories = {
            "Send Money": ["send", "transfer to", "sent to"],
            "Receive Money": ["received from", "receive"],
            "Pay Bill": ["pay bill", "paybill", "bill payment"],
            "Buy Goods": ["buy goods", "till", "merchant"],
            "Airtime": ["airtime", "bundle", "data"],
            "Withdraw": ["withdraw", "agent"],
            "Deposit": ["deposit"],
            "Charges": ["charge", "fee", "cost"],
        }

        for category, keywords in categories.items():
            if any(kw in details_lower for kw in keywords):
                return category

        return "Other"

    def _write_section_header(
        self, ws, row: int, title: str, col_start: str, col_end: str
    ):
        """Write a section header row."""
        ws.merge_cells(f"{col_start}{row}:{col_end}{row}")
        cell = ws[f"{col_start}{row}"]
        cell.value = title
        cell.font = Font(name="Calibri", size=12, bold=True, color=WHITE)
        cell.fill = PatternFill(
            start_color=SUBHEADER_BG, end_color=SUBHEADER_BG, fill_type="solid"
        )
        cell.alignment = Alignment(horizontal="left", indent=1)
        ws.row_dimensions[row].height = 25

    def _write_key_value_row(self, ws, row: int, key: str, value):
        """Write a label-value pair row."""
        ws.cell(row=row, column=1, value=key).font = Font(
            name="Calibri", size=10, bold=True, color=DARK_GRAY
        )
        ws.cell(row=row, column=2, value=value).font = Font(
            name="Calibri", size=10, color=DARK_GRAY
        )
        ws.row_dimensions[row].height = 20

    def _write_financial_row(
        self, ws, row: int, label: str, value, fmt: str
    ):
        """Write a financial summary row with appropriate formatting."""
        label_cell = ws.cell(row=row, column=1, value=label)
        label_cell.font = Font(name="Calibri", size=10, bold=True, color=DARK_GRAY)

        value_cell = ws.cell(row=row, column=2, value=value)

        if fmt == "currency":
            value_cell.number_format = '#,##0.00'
            value_cell.alignment = Alignment(horizontal="right")
            if isinstance(value, (int, float)):
                color = CREDIT_COLOR if value >= 0 else DEBIT_COLOR
                value_cell.font = Font(
                    name="Calibri", size=11, bold=True, color=color
                )
        else:
            value_cell.font = Font(name="Calibri", size=11, bold=True, color=DARK_GRAY)

        ws.row_dimensions[row].height = 22