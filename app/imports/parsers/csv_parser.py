"""CSV parser for the PF import module.

Supports UTF-8/UTF-8-BOM, comma delimiters, header aliases, multiple date
formats, debit/credit columns, negative amounts, and basic validation.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from app.imports.schemas import ColumnMapping


# Common CSV column aliases -> app field names.
COLUMN_ALIASES: dict[str, list[str]] = {
    "date": ["date", "transaction date", "posting date", "txn date", "value date"],
    "description": [
        "description",
        "narration",
        "details",
        "merchant",
        "payee",
        "counterparty",
        "transaction details",
    ],
    "amount": ["amount", "value", "total", "transaction amount"],
    "debit": ["debit", "debit amount", "money out"],
    "credit": ["credit", "credit amount", "money in"],
    "transaction_type": ["type", "transaction type", "txn type", "debit/credit"],
    "account": ["account", "account name", "account number", "from account"],
    "category": ["category", "expense category", "income category"],
    "reference": ["reference", "ref", "transaction id", "txn id", "reference number"],
    "currency": ["currency", "ccy"],
    "balance": ["balance", "running balance"],
}

DATE_FORMATS = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d-%b-%Y",
    "%d-%B-%Y",
]


class ParsedCSVRow:
    """Result of parsing a single CSV row."""

    def __init__(self, row_number: int, raw_data: dict[str, Any]):
        self.row_number = row_number
        self.raw_data = raw_data
        self.parsed_data: dict[str, Any] = {}
        self.validation_errors: list[str] = []
        self.status = "valid"

    def add_error(self, message: str) -> None:
        self.validation_errors.append(message)
        self.status = "invalid"


def _normalize_header(header: str) -> str:
    """Normalize a CSV header for alias matching."""
    return re.sub(r"\s+", " ", header.strip().lower().replace("_", " "))


def _detect_mapping(headers: list[str], hint: ColumnMapping) -> dict[str, str]:
    """Detect which CSV column maps to each app field.

    Explicit hints take priority over automatic detection.
    """
    normalized = {h: _normalize_header(h) for h in headers}
    mapping: dict[str, str] = {}

    # Apply explicit hints first.
    for field, column_name in hint.model_dump(exclude_none=True).items():
        if column_name in headers:
            mapping[field] = column_name
        else:
            norm = _normalize_header(column_name)
            for h, h_norm in normalized.items():
                if h_norm == norm:
                    mapping[field] = h
                    break

    # Auto-detect missing fields.
    for field, aliases in COLUMN_ALIASES.items():
        if field in mapping:
            continue
        for h, h_norm in normalized.items():
            if h_norm in aliases:
                mapping[field] = h
                break

    return mapping


def _parse_date(value: Any) -> Optional[date]:
    """Parse a date string using common formats."""
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_decimal(value: Any) -> Optional[Decimal]:
    """Parse a decimal amount, allowing commas as thousands separators."""
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip().replace(",", "")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _build_duplicate_key(parsed: dict[str, Any]) -> str:
    """Build a deterministic duplicate-detection key for a parsed row."""
    date_str = parsed.get("date")
    if isinstance(date_str, date):
        date_str = date_str.isoformat()
    amount = parsed.get("amount")
    description = re.sub(r"\s+", " ", str(parsed.get("description", "")).strip().lower())
    reference = str(parsed.get("reference", "")).strip().lower()
    return f"{date_str}|{amount}|{description}|{reference}"


class CSVParser:
    """Stateful CSV parser for import jobs."""

    def __init__(self, file_content: str, mapping_hint: Optional[ColumnMapping] = None):
        self.file_content = file_content
        self.mapping_hint = mapping_hint or ColumnMapping()

    def parse(self) -> dict[str, Any]:
        """Parse the CSV content and return a structured result.

        Returns:
            {
                "headers": [...],
                "mapping": {field: header, ...},
                "rows": [ParsedCSVRow, ...],
                "total_rows": int,
                "valid_rows": int,
                "invalid_rows": int,
            }
        """
        # Remove UTF-8 BOM if present.
        content = self.file_content.lstrip("\ufeff")
        reader = csv.DictReader(io.StringIO(content))
        headers = reader.fieldnames or []
        mapping = _detect_mapping(headers, self.mapping_hint)

        rows: list[ParsedCSVRow] = []
        row_number = 1  # header is row 0

        for raw in reader:
            row_number += 1
            # Skip completely empty lines.
            if not any(v is not None and str(v).strip() for v in raw.values()):
                continue

            parsed_row = ParsedCSVRow(row_number, {k: v for k, v in raw.items()})
            self._parse_row(parsed_row, mapping)
            rows.append(parsed_row)

        valid_rows = sum(1 for r in rows if r.status == "valid")
        invalid_rows = len(rows) - valid_rows

        return {
            "headers": headers,
            "mapping": mapping,
            "rows": rows,
            "total_rows": len(rows),
            "valid_rows": valid_rows,
            "invalid_rows": invalid_rows,
        }

    def _parse_row(self, parsed_row: ParsedCSVRow, mapping: dict[str, str]) -> None:
        raw = parsed_row.raw_data
        parsed = parsed_row.parsed_data

        # Date
        date_col = mapping.get("date")
        if date_col:
            parsed_date = _parse_date(raw.get(date_col))
            if parsed_date:
                parsed["date"] = parsed_date.isoformat()
            else:
                parsed_row.add_error(f"Could not parse date from '{date_col}'")
        else:
            parsed_row.add_error("No date column detected")

        # Description
        desc_col = mapping.get("description")
        if desc_col:
            description = str(raw.get(desc_col, "")).strip()
            if description:
                parsed["description"] = description
            else:
                parsed_row.add_error("Description is empty")
        else:
            parsed_row.add_error("No description column detected")

        # Amount handling: single amount, debit/credit columns, or negative amount.
        amount = self._resolve_amount(raw, mapping)
        if amount is None:
            parsed_row.add_error("Could not resolve a valid non-zero amount")
        else:
            parsed["amount"] = str(amount)
            parsed["amount_decimal"] = str(amount)
            if amount < 0:
                parsed["transaction_type"] = "expense"
            elif amount > 0:
                parsed["transaction_type"] = "income"
            else:
                parsed_row.add_error("Amount must be non-zero")

        # Explicit transaction type override.
        type_col = mapping.get("transaction_type")
        if type_col:
            txn_type = str(raw.get(type_col, "")).strip().lower()
            if txn_type in ("expense", "debit", "out"):
                parsed["transaction_type"] = "expense"
            elif txn_type in ("income", "credit", "in"):
                parsed["transaction_type"] = "income"

        # Account / category columns (kept as raw text for later lookup).
        for field in ("account", "category", "reference", "currency", "balance"):
            col = mapping.get(field)
            if col and raw.get(col) is not None:
                parsed[field] = str(raw.get(col)).strip()

        parsed_row.parsed_data = parsed
        parsed_row.duplicate_key = _build_duplicate_key(parsed)

    def _resolve_amount(
        self, raw: dict[str, Any], mapping: dict[str, str]
    ) -> Optional[Decimal]:
        """Resolve amount from a single amount column or debit/credit columns."""
        amount_col = mapping.get("amount")
        if amount_col:
            amount = _parse_decimal(raw.get(amount_col))
            if amount is not None and amount != 0:
                return amount

        debit_col = mapping.get("debit")
        credit_col = mapping.get("credit")
        debit = _parse_decimal(raw.get(debit_col)) if debit_col else None
        credit = _parse_decimal(raw.get(credit_col)) if credit_col else None

        # Prefer debit/credit when both are present.
        if debit is not None and debit != 0 and credit is not None and credit != 0:
            # Ambiguous; treat as invalid.
            return None
        if debit is not None and debit != 0:
            return -abs(debit)
        if credit is not None and credit != 0:
            return abs(credit)

        return None


def parse_csv_import(file_content: str, mapping_hint: Optional[ColumnMapping] = None) -> dict[str, Any]:
    """Convenience function to parse CSV content."""
    parser = CSVParser(file_content, mapping_hint)
    return parser.parse()


def compute_file_hash(content: str) -> str:
    """Return a SHA-256 hash of the file content for duplicate-file detection."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
