"""Document upload, storage, OCR, and linking integration tests.

Uses synthetic fake files only. No real financial documents are used.
"""

from __future__ import annotations

from datetime import date
from io import BytesIO

import pytest

from app.core.rls import set_tenant_context_async
from app.models import Document
from app.tests.helpers import (
    assert_rls_enabled,
    auth_headers_for,
    create_test_account,
    create_test_organization,
    create_test_user,
)


def _file_tuple(name: str, content: bytes, content_type: str = "text/plain"):
    return (name, BytesIO(content), content_type)


async def _create_bill(client, headers):
    response = await client.post(
        "/bills",
        json={
            "name": "Electricity",
            "provider": "Majan",
            "typical_amount": "45.000",
            "due_date": (date.today()).isoformat(),
            "frequency": "monthly",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _create_accounts_and_journal_entry(client, headers):
    asset = await client.post(
        "/accounts/",
        json={"code": "1100", "name": "Bank", "account_type": "Asset"},
        headers=headers,
    )
    assert asset.status_code == 200, asset.text
    income = await client.post(
        "/accounts/",
        json={"code": "4100", "name": "Salary", "account_type": "Income"},
        headers=headers,
    )
    assert income.status_code == 200, income.text

    entry = await client.post(
        "/transactions/",
        json={
            "date": date.today().isoformat(),
            "narration": "Salary deposit",
            "lines": [
                {"account_id": asset.json()["id"], "debit": "1000.000"},
                {"account_id": income.json()["id"], "credit": "1000.000"},
            ],
        },
        headers=headers,
    )
    assert entry.status_code == 200, entry.text
    return entry.json()


@pytest.mark.integration
@pytest.mark.anyio
async def test_upload_requires_auth(client):
    response = await client.post(
        "/documents/upload",
        files={"file": _file_tuple("receipt.txt", b"hello")},
    )
    assert response.status_code in (401, 403)


@pytest.mark.integration
@pytest.mark.anyio
async def test_valid_upload_creates_document_row(client, db, auth_headers, unique):
    content = b"Fake receipt content"
    response = await client.post(
        "/documents/upload",
        files={"file": _file_tuple("receipt.txt", content)},
        data={"document_type": "receipt", "category": "utilities"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["original_filename"] == "receipt.txt"
    assert data["document_type"] == "receipt"
    assert data["category"] == "utilities"
    assert data["status"] == "uploaded"
    assert data["file_size"] == len(content)
    assert data["checksum"] is not None

    # Cleanup
    await client.delete(f"/documents/{data['id']}", headers=auth_headers)


@pytest.mark.integration
@pytest.mark.anyio
async def test_unsupported_extension_rejected(client, auth_headers):
    response = await client.post(
        "/documents/upload",
        files={"file": _file_tuple("malware.exe", b"binary content")},
        headers=auth_headers,
    )
    assert response.status_code == 400


@pytest.mark.integration
@pytest.mark.anyio
async def test_oversized_file_rejected(client, auth_headers):
    # Default max upload size is 10 MB; upload 11 MB.
    big_content = b"x" * (11 * 1024 * 1024)
    response = await client.post(
        "/documents/upload",
        files={"file": _file_tuple("big.txt", big_content)},
        headers=auth_headers,
    )
    assert response.status_code == 413


@pytest.mark.integration
@pytest.mark.anyio
async def test_path_traversal_filename_sanitized(client, auth_headers, unique):
    response = await client.post(
        "/documents/upload",
        files={"file": _file_tuple("../evil.txt", b"safe content")},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert ".." not in data["original_filename"]
    assert data["original_filename"] == "evil.txt"
    await client.delete(f"/documents/{data['id']}", headers=auth_headers)


@pytest.mark.integration
@pytest.mark.anyio
async def test_list_and_get_documents_scoped_to_tenant(
    client, db, auth_headers, unique
):
    response = await client.post(
        "/documents/upload",
        files={"file": _file_tuple("stmt.txt", b"statement")},
        headers=auth_headers,
    )
    assert response.status_code == 200
    doc_id = response.json()["id"]

    list_response = await client.get("/documents/", headers=auth_headers)
    assert list_response.status_code == 200
    ids = {d["id"] for d in list_response.json()}
    assert doc_id in ids

    get_response = await client.get(f"/documents/{doc_id}", headers=auth_headers)
    assert get_response.status_code == 200
    assert get_response.json()["id"] == doc_id

    await client.delete(f"/documents/{doc_id}", headers=auth_headers)


@pytest.mark.integration
@pytest.mark.anyio
async def test_download_requires_tenant_access(client, db, auth_headers, unique):
    content = b"Downloadable content"
    response = await client.post(
        "/documents/upload",
        files={"file": _file_tuple("download.txt", content)},
        headers=auth_headers,
    )
    assert response.status_code == 200
    doc_id = response.json()["id"]

    download = await client.get(f"/documents/{doc_id}/download", headers=auth_headers)
    assert download.status_code == 200
    assert download.content == content

    await client.delete(f"/documents/{doc_id}", headers=auth_headers)


@pytest.mark.integration
@pytest.mark.anyio
async def test_archive_and_delete_document(client, db, auth_headers, unique):
    response = await client.post(
        "/documents/upload",
        files={"file": _file_tuple("temp.txt", b"temp")},
        headers=auth_headers,
    )
    assert response.status_code == 200
    doc_id = response.json()["id"]

    archive = await client.post(f"/documents/{doc_id}/archive", headers=auth_headers)
    assert archive.status_code == 200
    assert archive.json()["status"] == "archived"

    list_response = await client.get("/documents/", headers=auth_headers)
    assert doc_id not in {d["id"] for d in list_response.json()}

    delete = await client.delete(f"/documents/{doc_id}", headers=auth_headers)
    assert delete.status_code == 204

    get_response = await client.get(f"/documents/{doc_id}", headers=auth_headers)
    assert get_response.status_code == 404


@pytest.mark.integration
@pytest.mark.anyio
async def test_text_ocr_extraction(client, db, auth_headers, unique):
    content = b"Extract this text"
    response = await client.post(
        "/documents/upload",
        files={"file": _file_tuple("ocr.txt", content)},
        headers=auth_headers,
    )
    assert response.status_code == 200
    doc_id = response.json()["id"]

    ocr_response = await client.post(f"/documents/{doc_id}/ocr", headers=auth_headers)
    assert ocr_response.status_code == 200, ocr_response.text
    data = ocr_response.json()
    assert data["ocr_status"] == "success"
    assert "Extract this text" in data["ocr_text"]

    await client.delete(f"/documents/{doc_id}", headers=auth_headers)


@pytest.mark.integration
@pytest.mark.anyio
async def test_unsupported_ocr_type_handled_safely(
    client, db, auth_headers, unique
):
    response = await client.post(
        "/documents/upload",
        files={"file": _file_tuple("image.png", b"fake image bytes", "image/png")},
        headers=auth_headers,
    )
    assert response.status_code == 200
    doc_id = response.json()["id"]

    ocr_response = await client.post(f"/documents/{doc_id}/ocr", headers=auth_headers)
    assert ocr_response.status_code == 200, ocr_response.text
    data = ocr_response.json()
    assert data["ocr_status"] in ("unsupported", "pending", "failed")

    await client.delete(f"/documents/{doc_id}", headers=auth_headers)


@pytest.mark.integration
@pytest.mark.anyio
async def test_link_document_to_bill(client, db, auth_headers, unique):
    bill = await _create_bill(client, auth_headers)
    response = await client.post(
        "/documents/upload",
        files={"file": _file_tuple("bill_receipt.txt", b"bill receipt")},
        headers=auth_headers,
    )
    assert response.status_code == 200
    doc_id = response.json()["id"]

    link = await client.post(
        f"/documents/{doc_id}/link",
        json={"related_entity_type": "bill", "related_entity_id": bill["id"]},
        headers=auth_headers,
    )
    assert link.status_code == 200, link.text
    data = link.json()
    assert data["related_entity_type"] == "bill"
    assert data["related_entity_id"] == bill["id"]

    unlink = await client.post(f"/documents/{doc_id}/unlink", headers=auth_headers)
    assert unlink.status_code == 200
    assert unlink.json()["related_entity_type"] is None

    await client.delete(f"/documents/{doc_id}", headers=auth_headers)


@pytest.mark.integration
@pytest.mark.anyio
async def test_link_document_to_transaction(client, db, auth_headers, unique):
    entry = await _create_accounts_and_journal_entry(client, auth_headers)
    response = await client.post(
        "/documents/upload",
        files={"file": _file_tuple("txn_proof.txt", b"proof")},
        headers=auth_headers,
    )
    assert response.status_code == 200
    doc_id = response.json()["id"]

    link = await client.post(
        f"/documents/{doc_id}/link",
        json={"related_entity_type": "transaction", "related_entity_id": entry["id"]},
        headers=auth_headers,
    )
    assert link.status_code == 200, link.text
    assert link.json()["related_entity_type"] == "transaction"

    await client.delete(f"/documents/{doc_id}", headers=auth_headers)


@pytest.mark.integration
@pytest.mark.anyio
async def test_link_rejects_unsupported_entity_type(
    client, db, auth_headers, unique
):
    response = await client.post(
        "/documents/upload",
        files={"file": _file_tuple("link.txt", b"link")},
        headers=auth_headers,
    )
    assert response.status_code == 200
    doc_id = response.json()["id"]

    link = await client.post(
        f"/documents/{doc_id}/link",
        json={"related_entity_type": "unsupported", "related_entity_id": 1},
        headers=auth_headers,
    )
    assert link.status_code == 400

    await client.delete(f"/documents/{doc_id}", headers=auth_headers)


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_see_tenant_b_document(
    client, db, unique
):
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    user_a, password_a = await create_test_user(
        db, org_a, email=unique("a") + "@example.com", role="owner"
    )
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_b, password_b = await create_test_user(
        db, org_b, email=unique("b") + "@example.com", role="owner"
    )

    headers_a = await auth_headers_for(client, user_a.email, password_a)
    headers_b = await auth_headers_for(client, user_b.email, password_b)

    response = await client.post(
        "/documents/upload",
        files={"file": _file_tuple("private.txt", b"private")},
        headers=headers_a,
    )
    assert response.status_code == 200
    doc_id = response.json()["id"]

    get_b = await client.get(f"/documents/{doc_id}", headers=headers_b)
    assert get_b.status_code == 404

    download_b = await client.get(f"/documents/{doc_id}/download", headers=headers_b)
    assert download_b.status_code == 404

    list_b = await client.get("/documents/", headers=headers_b)
    assert doc_id not in {d["id"] for d in list_b.json()}

    await client.delete(f"/documents/{doc_id}", headers=headers_a)


@pytest.mark.integration
@pytest.mark.anyio
async def test_tenant_a_cannot_link_to_tenant_b_entity(
    client, db, unique
):
    org_a = await create_test_organization(db, name=unique("Org A"), slug=unique("org-a"))
    user_a, password_a = await create_test_user(
        db, org_a, email=unique("a") + "@example.com", role="owner"
    )
    org_b = await create_test_organization(db, name=unique("Org B"), slug=unique("org-b"))
    user_b, password_b = await create_test_user(
        db, org_b, email=unique("b") + "@example.com", role="owner"
    )

    headers_a = await auth_headers_for(client, user_a.email, password_a)
    headers_b = await auth_headers_for(client, user_b.email, password_b)

    doc_response = await client.post(
        "/documents/upload",
        files={"file": _file_tuple("link_cross.txt", b"cross")},
        headers=headers_a,
    )
    assert doc_response.status_code == 200
    doc_id = doc_response.json()["id"]

    bill_b = await _create_bill(client, headers_b)

    link = await client.post(
        f"/documents/{doc_id}/link",
        json={"related_entity_type": "bill", "related_entity_id": bill_b["id"]},
        headers=headers_a,
    )
    assert link.status_code == 404

    await client.delete(f"/documents/{doc_id}", headers=headers_a)


@pytest.mark.integration
@pytest.mark.anyio
async def test_rls_active_on_documents_table(db):
    await assert_rls_enabled(db, "documents")
