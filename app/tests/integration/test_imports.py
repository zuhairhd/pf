"""CSV import module tests.

Covers the CSV parser, the import job lifecycle, tenant isolation, RLS, and
confirmed journal-entry creation.
"""

from __future__ import annotations

import base64
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select, text

from app.imports.parsers.csv_parser import CSVParser, compute_file_hash, parse_csv_import
from app.imports.parsers.sms_parser import (
    compute_sms_hash,
    parse_sms,
    parse_sms_messages,
)
from app.imports.schemas import ColumnMapping
from app.tests.helpers import (
    assert_rls_enabled,
    auth_headers_for,
    create_test_organization,
    create_test_user,
)


FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "imports"


def _read_csv(filename: str) -> str:
    return (FIXTURES_DIR / filename).read_text(encoding="utf-8")


def _csv_payload(filename: str) -> dict:
    content = _read_csv(filename)
    return {
        "original_filename": filename,
        "file_content": content,
        "mapping": {},
        "currency": "OMR",
    }


def _read_sms(filename: str) -> str:
    return (FIXTURES_DIR / filename).read_text(encoding="utf-8")


def _sms_payload(filename: str) -> dict:
    return {
        "original_filename": filename,
        "sms_text": _read_sms(filename),
    }


@pytest.mark.unit
@pytest.mark.anyio
async def test_csv_parser_handles_utf8_bom():
    """A UTF-8 BOM must not break header detection."""
    content = "\ufeffDate,Description,Amount\n2026-06-01,Test,10.000\n"
    result = parse_csv_import(content)
    assert result["headers"] == ["Date", "Description", "Amount"]
    assert result["total_rows"] == 1
    assert result["rows"][0].status == "valid"


@pytest.mark.unit
@pytest.mark.anyio
async def test_csv_parser_handles_common_date_formats():
    """Multiple date formats are parsed correctly."""
    samples = [
        ("2026-07-01", "%Y-%m-%d"),
        ("01/07/2026", "%d/%m/%Y"),
        ("01-07-2026", "%d-%m-%Y"),
        ("01-Jul-2026", "%d-%b-%Y"),
        ("01-July-2026", "%d-%B-%Y"),
    ]
    for value, _ in samples:
        content = f"Date,Description,Amount\n{value},Test,-12.500\n"
        result = parse_csv_import(content)
        assert result["rows"][0].status == "valid", f"failed for {value}"
        assert result["rows"][0].parsed_data["date"] == "2026-07-01"


@pytest.mark.unit
@pytest.mark.anyio
async def test_csv_parser_handles_debit_credit_columns():
    """Debit/credit columns resolve to signed amounts."""
    content = _read_csv("sample_debit_credit.csv")
    result = parse_csv_import(content)

    by_description = {r.parsed_data["description"]: r for r in result["rows"]}
    assert len(by_description) == 3

    salary = by_description["Salary"]
    assert salary.status == "valid"
    assert Decimal(salary.parsed_data["amount_decimal"]) == Decimal("1500.000")
    assert salary.parsed_data["transaction_type"] == "income"

    grocery = by_description["Grocery store"]
    assert grocery.status == "valid"
    assert Decimal(grocery.parsed_data["amount_decimal"]) == Decimal("-45.500")
    assert grocery.parsed_data["transaction_type"] == "expense"

    atm = by_description["ATM withdrawal"]
    assert atm.status == "valid"
    assert Decimal(atm.parsed_data["amount_decimal"]) == Decimal("-100.000")


@pytest.mark.unit
@pytest.mark.anyio
async def test_csv_parser_handles_negative_amount_column():
    """Negative amounts in a single amount column are treated as expenses."""
    content = _read_csv("sample_bank_statement.csv")
    result = parse_csv_import(content)

    rows = {r.parsed_data["description"]: r for r in result["rows"]}
    assert Decimal(rows["Salary deposit"].parsed_data["amount_decimal"]) == Decimal(
        "1500.000"
    )
    assert rows["Salary deposit"].parsed_data["transaction_type"] == "income"
    assert Decimal(rows["Grocery store"].parsed_data["amount_decimal"]) == Decimal(
        "-45.500"
    )
    assert rows["Grocery store"].parsed_data["transaction_type"] == "expense"


@pytest.mark.unit
@pytest.mark.anyio
async def test_csv_parser_invalid_rows_are_captured():
    """Rows with missing date, missing description, or zero amount are invalid."""
    content = _read_csv("sample_invalid_rows.csv")
    result = parse_csv_import(content)

    assert result["total_rows"] == 3
    assert result["valid_rows"] == 0
    assert result["invalid_rows"] == 3
    errors = [e for r in result["rows"] for e in r.validation_errors]
    assert any("date" in e.lower() for e in errors)
    assert any("description" in e.lower() for e in errors)
    assert any("non-zero" in e.lower() for e in errors)


@pytest.mark.unit
@pytest.mark.anyio
async def test_csv_parser_duplicate_rows_detected():
    """Identical rows are flagged as duplicates."""
    content = _read_csv("sample_duplicates.csv")
    parser = CSVParser(content)
    parsed = parser.parse()

    assert parsed["total_rows"] == 2
    assert parsed["rows"][0].status == "valid"
    assert parsed["rows"][1].status == "valid"
    assert parsed["rows"][1].duplicate_key == parsed["rows"][0].duplicate_key


@pytest.mark.integration
@pytest.mark.anyio
async def test_upload_detects_duplicate_rows(client, auth_headers):
    """Uploading a file with duplicate rows marks the second as duplicate."""
    response = await client.post(
        "/imports/csv/upload",
        json=_csv_payload("sample_duplicates.csv"),
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["summary"]["total_rows"] == 2
    assert data["summary"]["valid_rows"] == 1
    assert data["summary"]["duplicate_rows"] == 1


@pytest.mark.integration
@pytest.mark.anyio
async def test_upload_requires_auth(client):
    """Anonymous users cannot upload CSV files."""
    response = await client.post(
        "/imports/csv/upload",
        json=_csv_payload("sample_bank_statement.csv"),
    )
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_upload_creates_job_and_rows(client, auth_headers):
    """An authenticated tenant user can upload a CSV and receive a preview."""
    response = await client.post(
        "/imports/csv/upload",
        json=_csv_payload("sample_bank_statement.csv"),
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "job_id" in data
    assert data["summary"]["total_rows"] == 3
    assert data["summary"]["valid_rows"] == 3
    assert data["summary"]["import_type"] == "csv"
    assert len(data["rows"]) == 3


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_cannot_see_other_tenant_import_job(client, db, unique):
    """Tenant A's import job is invisible to a user from Tenant B."""
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_a, password_a = await create_test_user(db, org_a)
    user_b, password_b = await create_test_user(db, org_b)

    headers_a = await auth_headers_for(client, user_a.email, password_a)
    headers_b = await auth_headers_for(client, user_b.email, password_b)

    upload_response = await client.post(
        "/imports/csv/upload",
        json=_csv_payload("sample_bank_statement.csv"),
        headers=headers_a,
    )
    assert upload_response.status_code == 200
    job_id = upload_response.json()["job_id"]

    response_b = await client.get(f"/imports/{job_id}", headers=headers_b)
    assert response_b.status_code == 404


@pytest.mark.integration
@pytest.mark.anyio
async def test_rls_active_on_import_tables(db):
    """Both import tables must have RLS and FORCE RLS enabled."""
    await assert_rls_enabled(db, "import_jobs")
    await assert_rls_enabled(db, "imported_rows")


@pytest.mark.integration
@pytest.mark.anyio
async def test_confirm_imports_valid_rows_into_journal_entries(
    client, auth_headers, test_user, db, tenant_context
):
    """Confirming an import creates journal entries for valid rows."""
    # Create the accounts required by the confirm payload.
    accounts = [
        {"code": "BANK", "name": "Bank Muscat", "account_type": "Asset", "is_bank_account": True},
        {"code": "SAL", "name": "Salary", "account_type": "Income"},
        {"code": "GRO", "name": "Food & Groceries", "account_type": "Expense"},
        {"code": "CASH", "name": "Wallet", "account_type": "Asset"},
    ]
    created_accounts = []
    for account in accounts:
        response = await client.post("/accounts/", json=account, headers=auth_headers)
        assert response.status_code == 200, response.text
        created_accounts.append(response.json())

    bank_account = next(a for a in created_accounts if a["code"] == "BANK")
    income_account = next(a for a in created_accounts if a["code"] == "SAL")
    expense_account = next(a for a in created_accounts if a["code"] == "GRO")

    # Upload the CSV.
    upload_response = await client.post(
        "/imports/csv/upload",
        json=_csv_payload("sample_bank_statement.csv"),
        headers=auth_headers,
    )
    assert upload_response.status_code == 200, upload_response.text
    job_id = upload_response.json()["job_id"]

    # Confirm the import.
    confirm_payload = {
        "bank_account_id": bank_account["id"],
        "default_income_account_id": income_account["id"],
        "default_expense_account_id": expense_account["id"],
        "import_duplicates": False,
    }
    confirm_response = await client.post(
        f"/imports/{job_id}/confirm",
        json=confirm_payload,
        headers=auth_headers,
    )
    assert confirm_response.status_code == 200, confirm_response.text
    confirm_data = confirm_response.json()
    assert confirm_data["status"] == "completed"
    assert confirm_data["imported_rows"] == 3

    # Verify journal entries were created in the test user's tenant context.
    from app.models import JournalEntry

    await tenant_context(test_user.organization_id)
    result = await db.execute(
        select(JournalEntry)
        .where(JournalEntry.tenant_id == test_user.organization_id)
        .where(JournalEntry.source == "import")
    )
    entries = result.scalars().all()
    assert len(entries) == 3


@pytest.mark.integration
@pytest.mark.anyio
async def test_cancel_import_job(client, auth_headers):
    """An import job can be cancelled before confirmation."""
    upload_response = await client.post(
        "/imports/csv/upload",
        json=_csv_payload("sample_bank_statement.csv"),
        headers=auth_headers,
    )
    assert upload_response.status_code == 200
    job_id = upload_response.json()["job_id"]

    cancel_response = await client.post(
        f"/imports/{job_id}/cancel",
        headers=auth_headers,
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"

    # Confirming a cancelled job should fail.
    confirm_response = await client.post(
        f"/imports/{job_id}/confirm",
        json={
            "bank_account_id": 1,
            "default_income_account_id": 1,
            "default_expense_account_id": 1,
        },
        headers=auth_headers,
    )
    assert confirm_response.status_code == 400


# ---------------------------------------------------------------------------
# SMS parser unit tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.anyio
async def test_sms_parser_bank_muscat_debit():
    """Bank Muscat debit SMS is parsed as an expense."""
    text = _read_sms("sample_sms_bank_muscat.txt")
    parsed = parse_sms(text)

    assert parsed.bank == "Bank Muscat"
    assert parsed.masked_account == "****1234"
    assert parsed.amount == Decimal("45.000")
    assert parsed.currency == "OMR"
    assert parsed.date == date(2026, 7, 1)
    assert parsed.transaction_type == "expense"
    assert parsed.description == "CARREFOUR"
    assert parsed.balance == Decimal("1234.567")
    assert parsed.confidence == "high"
    assert not parsed.validation_errors


@pytest.mark.unit
@pytest.mark.anyio
async def test_sms_parser_bankdhofar_credit():
    """BankDhofar credit SMS is parsed as income."""
    text = _read_sms("sample_sms_bankdhofar.txt")
    parsed = parse_sms(text)

    assert parsed.bank == "BankDhofar"
    assert parsed.masked_account == "****5678"
    assert parsed.amount == Decimal("250.000")
    assert parsed.date == date(2026, 7, 2)
    assert parsed.transaction_type == "income"
    assert parsed.description == "SALARY"
    assert parsed.confidence == "high"
    assert not parsed.validation_errors


@pytest.mark.unit
@pytest.mark.anyio
async def test_sms_parser_oab_purchase():
    """OAB purchase SMS extracts merchant, account and balance."""
    text = _read_sms("sample_sms_oab.txt")
    parsed = parse_sms(text)

    assert parsed.bank == "Oman Arab Bank"
    assert parsed.masked_account == "****1111"
    assert parsed.amount == Decimal("12.500")
    assert parsed.date == date(2026, 7, 2)
    assert parsed.transaction_type == "expense"
    assert parsed.description == "Lulu Hypermarket"
    assert parsed.balance == Decimal("900.000")
    assert parsed.confidence == "high"
    assert not parsed.validation_errors


@pytest.mark.unit
@pytest.mark.anyio
async def test_sms_parser_invalid_message():
    """A non-bank message is marked invalid with validation errors."""
    text = _read_sms("sample_sms_invalid.txt")
    parsed = parse_sms(text)

    assert parsed.bank is None
    assert parsed.confidence == "low"
    assert parsed.status == "invalid"
    assert any("bank" in e.lower() for e in parsed.validation_errors)
    assert any("amount" in e.lower() for e in parsed.validation_errors)
    assert any("date" in e.lower() for e in parsed.validation_errors)


@pytest.mark.unit
@pytest.mark.anyio
async def test_sms_parser_multiple_messages():
    """Multiple pasted SMS messages create separate parsed records."""
    text = _read_sms("sample_sms_bank_muscat.txt") + "\n\n" + _read_sms("sample_sms_bankdhofar.txt")
    parsed_list = parse_sms_messages(text)

    assert len(parsed_list) == 2
    assert parsed_list[0].bank == "Bank Muscat"
    assert parsed_list[1].bank == "BankDhofar"


@pytest.mark.unit
@pytest.mark.anyio
async def test_sms_parser_amount_with_comma():
    """Amounts containing commas are parsed correctly."""
    text = (
        "Bank Muscat: Your account ****1234 has been debited OMR 1,234.567 "
        "on 01-JUL-2026. Ref: GROCERY"
    )
    parsed = parse_sms(text)

    assert parsed.amount == Decimal("1234.567")
    assert parsed.transaction_type == "expense"


@pytest.mark.unit
@pytest.mark.anyio
async def test_sms_parser_date_formats():
    """Common SMS date formats are parsed correctly."""
    samples = [
        ("01/07/2026", "%d/%m/%Y"),
        ("01-07-2026", "%d-%m-%Y"),
        ("01-JUL-2026", "%d-%b-%Y"),
        ("2026-07-01", "%Y-%m-%d"),
    ]
    for value, _ in samples:
        text = f"Bank Muscat: debited OMR 10.000 on {value}. Ref: TEST"
        parsed = parse_sms(text)
        assert parsed.date == date(2026, 7, 1), f"failed for {value}"


@pytest.mark.unit
@pytest.mark.anyio
async def test_sms_duplicate_key_deterministic():
    """Duplicate key is deterministic for identical SMS messages."""
    text = _read_sms("sample_sms_bank_muscat.txt")
    key_a = parse_sms(text).compute_duplicate_key()
    key_b = parse_sms(text).compute_duplicate_key()
    assert key_a == key_b
    assert key_a is not None


# ---------------------------------------------------------------------------
# SMS import integration tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.anyio
async def test_sms_parse_endpoint_requires_auth(client):
    """Anonymous users cannot parse SMS messages."""
    response = await client.post(
        "/imports/sms/parse",
        json=_sms_payload("sample_sms_bank_muscat.txt"),
    )
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_sms_parse_creates_sms_job_and_rows(client, auth_headers):
    """An authenticated tenant user can parse SMS and receive a preview."""
    response = await client.post(
        "/imports/sms/parse",
        json=_sms_payload("sample_sms_bank_muscat.txt"),
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "job_id" in data
    assert data["summary"]["import_type"] == "sms"
    assert data["summary"]["total_rows"] == 1
    assert data["summary"]["valid_rows"] == 1
    assert len(data["rows"]) == 1
    assert data["rows"][0]["parsed_data"]["bank"] == "Bank Muscat"


@pytest.mark.integration
@pytest.mark.anyio
async def test_sms_parse_invalid_message_creates_invalid_row(client, auth_headers):
    """Invalid SMS messages are stored with validation errors."""
    response = await client.post(
        "/imports/sms/parse",
        json=_sms_payload("sample_sms_invalid.txt"),
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["summary"]["total_rows"] == 1
    assert data["summary"]["valid_rows"] == 0
    assert data["summary"]["invalid_rows"] == 1
    assert data["rows"][0]["status"] == "invalid"
    assert data["rows"][0]["validation_errors"]


@pytest.mark.integration
@pytest.mark.anyio
async def test_sms_parse_detects_duplicates(client, auth_headers):
    """Duplicate pasted SMS messages are flagged as duplicates."""
    text = _read_sms("sample_sms_bank_muscat.txt")
    response = await client.post(
        "/imports/sms/parse",
        json={"original_filename": "dupes.txt", "sms_text": f"{text}\n\n{text}"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["summary"]["total_rows"] == 2
    assert data["summary"]["valid_rows"] == 1
    assert data["summary"]["duplicate_rows"] == 1


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_cannot_see_other_tenant_sms_job(client, db, unique):
    """Tenant A's SMS import job is invisible to a user from Tenant B."""
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_a, password_a = await create_test_user(db, org_a)
    user_b, password_b = await create_test_user(db, org_b)

    headers_a = await auth_headers_for(client, user_a.email, password_a)
    headers_b = await auth_headers_for(client, user_b.email, password_b)

    upload_response = await client.post(
        "/imports/sms/parse",
        json=_sms_payload("sample_sms_bank_muscat.txt"),
        headers=headers_a,
    )
    assert upload_response.status_code == 200
    job_id = upload_response.json()["job_id"]

    response_b = await client.get(f"/imports/{job_id}", headers=headers_b)
    assert response_b.status_code == 404


@pytest.mark.integration
@pytest.mark.anyio
async def test_confirm_sms_posts_valid_rows_to_journal_entries(
    client, auth_headers, test_user, db, tenant_context
):
    """Confirming an SMS import creates journal entries for valid rows."""
    from app.models import JournalEntry

    accounts = [
        {"code": "BANK", "name": "Bank Muscat", "account_type": "Asset", "is_bank_account": True},
        {"code": "SAL", "name": "Salary", "account_type": "Income"},
        {"code": "GRO", "name": "Food & Groceries", "account_type": "Expense"},
    ]
    created_accounts = []
    for account in accounts:
        response = await client.post("/accounts/", json=account, headers=auth_headers)
        assert response.status_code == 200, response.text
        created_accounts.append(response.json())

    bank_account = next(a for a in created_accounts if a["code"] == "BANK")
    income_account = next(a for a in created_accounts if a["code"] == "SAL")
    expense_account = next(a for a in created_accounts if a["code"] == "GRO")

    # Parse both a debit and a credit SMS so we exercise both posting paths.
    text = (
        _read_sms("sample_sms_bank_muscat.txt") + "\n\n" +
        _read_sms("sample_sms_bankdhofar.txt")
    )
    parse_response = await client.post(
        "/imports/sms/parse",
        json={"original_filename": "mixed.txt", "sms_text": text},
        headers=auth_headers,
    )
    assert parse_response.status_code == 200, parse_response.text
    job_id = parse_response.json()["job_id"]

    confirm_payload = {
        "bank_account_id": bank_account["id"],
        "default_income_account_id": income_account["id"],
        "default_expense_account_id": expense_account["id"],
        "import_duplicates": False,
    }
    confirm_response = await client.post(
        f"/imports/{job_id}/confirm",
        json=confirm_payload,
        headers=auth_headers,
    )
    assert confirm_response.status_code == 200, confirm_response.text
    confirm_data = confirm_response.json()
    assert confirm_data["status"] == "completed"
    assert confirm_data["imported_rows"] == 2

    await tenant_context(test_user.organization_id)
    result = await db.execute(
        select(JournalEntry)
        .where(JournalEntry.tenant_id == test_user.organization_id)
        .where(JournalEntry.source == "import")
    )
    entries = result.scalars().all()
    assert len(entries) == 2


@pytest.mark.integration
@pytest.mark.anyio
async def test_confirm_sms_skips_invalid_and_duplicate_rows(
    client, auth_headers, test_user, db, tenant_context
):
    """Only valid, non-duplicate SMS rows are posted."""
    from app.models import JournalEntry

    accounts = [
        {"code": "BANK", "name": "Bank Muscat", "account_type": "Asset", "is_bank_account": True},
        {"code": "GRO", "name": "Food & Groceries", "account_type": "Expense"},
    ]
    created_accounts = []
    for account in accounts:
        response = await client.post("/accounts/", json=account, headers=auth_headers)
        assert response.status_code == 200, response.text
        created_accounts.append(response.json())

    bank_account = next(a for a in created_accounts if a["code"] == "BANK")
    expense_account = next(a for a in created_accounts if a["code"] == "GRO")

    # One valid debit, one duplicate of it, one invalid message.
    valid_text = _read_sms("sample_sms_bank_muscat.txt")
    invalid_text = _read_sms("sample_sms_invalid.txt")
    text = f"{valid_text}\n\n{valid_text}\n\n{invalid_text}"
    parse_response = await client.post(
        "/imports/sms/parse",
        json={"original_filename": "mixed.txt", "sms_text": text},
        headers=auth_headers,
    )
    assert parse_response.status_code == 200, parse_response.text
    job_id = parse_response.json()["job_id"]
    summary = parse_response.json()["summary"]
    assert summary["valid_rows"] == 1
    assert summary["duplicate_rows"] == 1
    assert summary["invalid_rows"] == 1

    confirm_payload = {
        "bank_account_id": bank_account["id"],
        "default_income_account_id": None,
        "default_expense_account_id": expense_account["id"],
        "import_duplicates": False,
    }
    confirm_response = await client.post(
        f"/imports/{job_id}/confirm",
        json=confirm_payload,
        headers=auth_headers,
    )
    assert confirm_response.status_code == 200, confirm_response.text
    confirm_data = confirm_response.json()
    assert confirm_data["imported_rows"] == 1

    await tenant_context(test_user.organization_id)
    result = await db.execute(
        select(JournalEntry)
        .where(JournalEntry.tenant_id == test_user.organization_id)
        .where(JournalEntry.source == "import")
    )
    entries = result.scalars().all()
    assert len(entries) == 1
