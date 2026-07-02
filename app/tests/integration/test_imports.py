"""CSV import module tests.

Covers the CSV parser, the import job lifecycle, tenant isolation, RLS, and
confirmed journal-entry creation.
"""

from __future__ import annotations

import base64
import os
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select, text

from app.imports.parsers.csv_parser import CSVParser, compute_file_hash, parse_csv_import
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
