"""SMS bank alert parser for Omani banks.

Parses pasted or forwarded SMS messages from common Omani banks into a
normalized structure that can be fed into the existing ImportJob/ImportedRow
workflow. The parser is rule-based (no AI/LLM) and uses bank-specific regex
patterns plus a generic fallback for unknown messages.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional


# Date formats we attempt for free-form SMS date strings.
DATE_FORMATS = [
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d-%b-%Y",
    "%d-%B-%Y",
    "%Y-%m-%d",
]

# Arabic-Indic digits sometimes appear in SMS messages from local operators.
ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
WESTERN_DIGITS = "0123456789"
ARABIC_TO_WESTERN = str.maketrans(ARABIC_DIGITS, WESTERN_DIGITS)


@dataclass
class ParsedSMS:
    """Result of parsing a single SMS message."""

    bank: Optional[str] = None
    masked_account: Optional[str] = None
    transaction_type: str = "unknown"
    amount: Optional[Decimal] = None
    currency: str = "OMR"
    date: Optional[date] = None
    time: Optional[str] = None
    description: Optional[str] = None
    reference: Optional[str] = None
    balance: Optional[Decimal] = None
    raw_message: str = ""
    confidence: str = "low"
    validation_errors: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        """Return 'valid' if there are no validation errors, else 'invalid'."""
        return "invalid" if self.validation_errors else "valid"

    def to_dict(self) -> dict[str, Any]:
        """Convert parsed SMS to a JSON-serializable dict."""
        return {
            "bank": self.bank,
            "masked_account": self.masked_account,
            "transaction_type": self.transaction_type,
            "amount": str(self.amount) if self.amount is not None else None,
            "amount_decimal": str(self.amount) if self.amount is not None else None,
            "currency": self.currency,
            "date": self.date.isoformat() if self.date else None,
            "time": self.time,
            "description": self.description,
            "reference": self.reference,
            "balance": str(self.balance) if self.balance is not None else None,
            "raw_message": self.raw_message,
            "confidence": self.confidence,
        }

    def compute_duplicate_key(self) -> Optional[str]:
        """Build a deterministic duplicate key for import duplicate detection."""
        if self.date is None or self.amount is None:
            return None
        description = re.sub(
            r"\s+",
            " ",
            str(self.description or "").strip().lower(),
        )
        reference = str(self.reference or "").strip().lower()
        account = str(self.masked_account or "").strip().lower()
        return f"{self.date.isoformat()}|{self.amount}|{description}|{reference}|{account}"


def _normalize_text(text: str) -> str:
    """Normalize whitespace and translate Arabic digits to Western digits."""
    text = text.translate(ARABIC_TO_WESTERN)
    text = re.sub(r"\s+", " ", text.strip())
    return text


def _parse_amount(value: Optional[str]) -> Optional[Decimal]:
    """Parse an amount string, allowing commas as thousands separators."""
    if value is None:
        return None
    text = value.strip().replace(",", "")
    # Sometimes amounts appear as "1,234.567" or "OMR 45.000".
    text = re.sub(r"[^0-9.\-]", "", text)
    if not text:
        return None
    try:
        amount = Decimal(text)
        return amount
    except InvalidOperation:
        return None


def _parse_date(value: Optional[str]) -> Optional[date]:
    """Parse a date string using common SMS formats."""
    if value is None:
        return None
    text = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _extract_time(text: str) -> Optional[str]:
    """Extract a time string (HH:MM or HH:MM:SS) from text if present."""
    match = re.search(r"\b(\d{1,2}:\d{2}(?::\d{2})?)\b", text)
    if match:
        return match.group(1)
    return None


def _extract_masked_account(text: str) -> Optional[str]:
    """Extract a masked account number such as ****1234 or XX1234."""
    match = re.search(r"(?:\*{4}|x{4}|xx|\\*\*\*\*|XXXX)(\d{3,4})", text, re.IGNORECASE)
    if match:
        return f"****{match.group(1)}"
    # Some banks use "account 1234" without masking.
    match = re.search(r"(?:account|acct|a/c)\s*#?\s*(\d{4})", text, re.IGNORECASE)
    if match:
        return f"****{match.group(1)}"
    return None


def _extract_reference(text: str) -> Optional[str]:
    """Extract a reference number from common SMS phrasing."""
    patterns = [
        r"(?:Ref|Reference)\s*[.:\-]?\s*([A-Za-z0-9\-]+)",
        r"(?:Ref#|Reference#)\s*([A-Za-z0-9\-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _extract_balance(text: str) -> Optional[Decimal]:
    """Extract an available/current balance from SMS text."""
    patterns = [
        r"(?:Available balance|Avl Bal|Balance|Bal)\s*[:\-]?\s*(?:OMR)?\s*([\d,]+\.\d{1,3})",
        r"(?:Bal|Balance)\s*[:\-]?\s*OMR\s*([\d,]+\.\d{1,3})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _parse_amount(match.group(1))
    return None


def _infer_transaction_type(text: str, amount: Optional[Decimal]) -> str:
    """Infer transaction type from keywords in the message."""
    lower = text.lower()
    debit_keywords = [
        "debited",
        "debit",
        "purchase",
        "purchased",
        "withdrawn",
        "withdrawal",
        "charges",
        "charge",
        "fee",
        "paid",
        "payment",
        "spent",
    ]
    credit_keywords = [
        "credited",
        "credit",
        "deposit",
        "salary",
        "received",
        "transfer in",
    ]
    if any(kw in lower for kw in debit_keywords):
        return "expense"
    if any(kw in lower for kw in credit_keywords):
        return "income"
    if amount is not None:
        return "expense" if amount < 0 else "income"
    return "unknown"


def _extract_currency(text: str) -> str:
    """Extract currency code or default to OMR."""
    match = re.search(r"\b(OMR|USD|AED|SAR|BHD|KWD|QAR|GBP|EUR)\b", text, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return "OMR"


def _extract_description(text: str, bank: Optional[str]) -> Optional[str]:
    """Extract a human-readable description/merchant from SMS text."""
    # Try common patterns: "at MERCHANT", "Ref: MERCHANT", "from account ... Ref: X".
    patterns = [
        r"(?:at|from|to|@)\s+([A-Za-z][A-Za-z0-9\s&\-]{2,40})(?:\s+on\s|\s+Ref|\s+Avl|\s+Balance|\.|$)",
        r"(?:Ref|Reference)[:\-]?\s*([A-Za-z][A-Za-z0-9\s&\-]{2,40})(?:\s+on\s|\s+Avl|\s+Balance|\.|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    # Fallback: use bank name and a generic description.
    if bank:
        return f"{bank} transaction"
    return "SMS transaction"


# Bank-specific regex patterns. Each pattern must capture at least `amount` and `date`.
BANK_PATTERNS: list[dict[str, Any]] = [
    {
        "bank": "Bank Muscat",
        "regex": re.compile(
            r"Bank\s*Muscat.*?(?:account\s+(\*{4}\d+)).*?"
            r"(?:debited|credited|charged).*?"
            r"(?:OMR)?\s*([\d,]+\.\d{1,3}).*?"
            r"on\s+(\d{1,2}[-/][A-Za-z0-9]+[-/]\d{2,4}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
            re.IGNORECASE | re.DOTALL,
        ),
    },
    {
        "bank": "BankDhofar",
        "regex": re.compile(
            r"BankDhofar.*?(?:Acct\s+(\*{4}\d+)).*?"
            r"(?:credited|debited).*?"
            r"(?:with\s+)?(?:OMR)?\s*([\d,]+\.\d{1,3}).*?"
            r"on\s+(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
            re.IGNORECASE | re.DOTALL,
        ),
    },
    {
        "bank": "Oman Arab Bank",
        "regex": re.compile(
            r"OAB.*?(?:Purchase|Withdrawal|Transfer|Deposit).*?"
            r"(?:OMR)?\s*([\d,]+\.\d{1,3}).*?"
            r"(?:at|from)\s+([A-Za-z][A-Za-z0-9\s&\-]{2,40}).*?"
            r"account\s+(\*{4}\d+).*?"
            r"on\s+(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
            re.IGNORECASE | re.DOTALL,
        ),
    },
    {
        "bank": "Alizz Islamic Bank",
        "regex": re.compile(
            r"Alizz\s+Islamic\s+Bank.*?"
            r"(?:OMR)?\s*([\d,]+\.\d{1,3}).*?"
            r"(?:charges|debited|credited).*?"
            r"account\s+(\*{4}\d+).*?"
            r"on\s+(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
            re.IGNORECASE | re.DOTALL,
        ),
    },
    {
        "bank": "Sohar International",
        "regex": re.compile(
            r"Sohar\s+International.*?"
            r"(?:account\s+(\*{4}\d+))?.*?"
            r"(?:OMR)?\s*([\d,]+\.\d{1,3}).*?"
            r"(?:debited|credited).*?"
            r"on\s+(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
            re.IGNORECASE | re.DOTALL,
        ),
    },
    {
        "bank": "National Bank of Oman",
        "regex": re.compile(
            r"NBO.*?"
            r"(?:account\s+(\*{4}\d+))?.*?"
            r"(?:OMR)?\s*([\d,]+\.\d{1,3}).*?"
            r"(?:debited|credited|paid).*?"
            r"on\s+(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
            re.IGNORECASE | re.DOTALL,
        ),
    },
]


def _apply_bank_patterns(text: str) -> Optional[ParsedSMS]:
    """Try bank-specific regex patterns and return a ParsedSMS if matched."""
    for pattern in BANK_PATTERNS:
        match = pattern["regex"].search(text)
        if not match:
            continue

        bank = pattern["bank"]
        groups = match.groups()

        # Different patterns capture groups in different orders.
        if bank == "Oman Arab Bank":
            amount_str, description, account, date_str = groups
            # Clean trailing connector words sometimes captured by the merchant regex.
            description = re.sub(r"\s+\b(from|on|ref|avl|balance)\b.*$", "", description, flags=re.IGNORECASE).strip()
            parsed = ParsedSMS(
                bank=bank,
                masked_account=account,
                amount=_parse_amount(amount_str),
                date=_parse_date(date_str),
                raw_message=text,
                confidence="high",
                description=description,
            )
        elif bank == "Alizz Islamic Bank":
            amount_str, account, date_str = groups
            parsed = ParsedSMS(
                bank=bank,
                masked_account=account,
                amount=_parse_amount(amount_str),
                date=_parse_date(date_str),
                raw_message=text,
                confidence="high",
            )
        else:
            # Bank Muscat, BankDhofar, Sohar, NBO share a similar group layout.
            account = groups[0]
            amount_str = groups[1]
            date_str = groups[2]
            parsed = ParsedSMS(
                bank=bank,
                masked_account=account,
                amount=_parse_amount(amount_str),
                date=_parse_date(date_str),
                raw_message=text,
                confidence="high",
            )

        parsed.currency = _extract_currency(text)
        parsed.time = _extract_time(text)
        parsed.reference = _extract_reference(text)
        parsed.balance = _extract_balance(text)
        if parsed.description is None:
            parsed.description = _extract_description(text, bank)
        parsed.transaction_type = _infer_transaction_type(text, parsed.amount)
        return parsed

    return None


def _generic_parse(text: str) -> ParsedSMS:
    """Generic fallback parser when no bank-specific pattern matches."""
    parsed = ParsedSMS(raw_message=text, confidence="low")
    parsed.currency = _extract_currency(text)
    parsed.time = _extract_time(text)
    parsed.masked_account = _extract_masked_account(text)
    parsed.reference = _extract_reference(text)
    parsed.balance = _extract_balance(text)

    # Try to find an amount anywhere in the message.
    amount_match = re.search(
        r"(?:OMR|USD|AED|SAR|BHD|KWD|QAR)?\s*([\d,]+\.\d{1,3})",
        text,
        re.IGNORECASE,
    )
    if amount_match:
        parsed.amount = _parse_amount(amount_match.group(1))

    # Try to find a date anywhere in the message.
    date_match = re.search(
        r"\b(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2})\b",
        text,
    )
    if date_match:
        parsed.date = _parse_date(date_match.group(1))

    parsed.description = _extract_description(text, parsed.bank)
    parsed.transaction_type = _infer_transaction_type(text, parsed.amount)
    return parsed


def _validate(parsed: ParsedSMS) -> None:
    """Validate a parsed SMS and populate validation_errors."""
    if parsed.bank is None and parsed.confidence == "low":
        parsed.validation_errors.append("Could not identify bank from message")
    if parsed.amount is None or parsed.amount == 0:
        parsed.validation_errors.append("Could not parse a valid non-zero amount")
    if parsed.date is None:
        parsed.validation_errors.append("Could not parse a valid date")
    if parsed.description is None or not parsed.description.strip():
        parsed.validation_errors.append("Could not extract a description")


def parse_sms(text: str) -> ParsedSMS:
    """Parse a single SMS message into a ParsedSMS object."""
    normalized = _normalize_text(text)
    parsed = _apply_bank_patterns(normalized)
    if parsed is None:
        parsed = _generic_parse(normalized)
    _validate(parsed)
    return parsed


def _split_messages(text: str) -> list[str]:
    """Split pasted text into individual SMS messages.

    Messages may be separated by newlines, double newlines, or common SMS
    delimiters such as "---". Empty messages are discarded.
    """
    # Normalize line endings.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Split on double newlines or lines that look like dividers.
    parts = re.split(r"\n\s*\n|\n---+|\r?\n---+", text)
    messages: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # If a single line looks like a complete SMS, keep it as one message.
        # Otherwise split further on single newlines if each line is short enough.
        lines = [line.strip() for line in part.split("\n") if line.strip()]
        if len(lines) == 1:
            messages.append(lines[0])
        else:
            # Heuristic: if lines look like separate bank SMSs (each contains an
            # amount and date), split them; otherwise treat the block as one.
            for line in lines:
                if re.search(r"\d+\.\d{1,3}", line) and _parse_date_from_line(line):
                    messages.append(line)
                else:
                    # Append to the previous message if it exists, otherwise start new.
                    if messages and not re.search(r"\d+\.\d{1,3}", messages[-1]):
                        messages[-1] += " " + line
                    else:
                        messages.append(line)
    return messages


def _parse_date_from_line(line: str) -> Optional[date]:
    """Helper used by message splitter to detect date-bearing lines."""
    match = re.search(
        r"\b(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2})\b",
        line,
    )
    if match:
        return _parse_date(match.group(1))
    return None


def parse_sms_messages(text: str) -> list[ParsedSMS]:
    """Parse one or more pasted SMS messages."""
    messages = _split_messages(text)
    if not messages:
        # Try treating the whole text as a single message.
        messages = [_normalize_text(text)]
    return [parse_sms(msg) for msg in messages if msg.strip()]


def compute_sms_hash(text: str) -> str:
    """Return a SHA-256 hash of the raw SMS text for duplicate-file detection."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
