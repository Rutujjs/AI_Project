"""Tests for Member 5: Supplier Management Backend (Phase 5B).

Verifies:
1. Supplier Listing, Search, Category/Tier/Risk Filtering & Pagination
2. Aggregate KPI Statistics (Total, High Risk, Expiring Docs, Avg ESG Score)
3. Strict Multi-Tenant Isolation (Cross-organization isolation)
4. Role-Based Access Control (RBAC: Admin, Auditor, Viewer)
5. Supplier Onboarding & CRUD Lifecycle (including duplicate code check)
6. Supplier Document Upload & Expiry Tracking (VALID, EXPIRING_SOON, EXPIRED)
7. Compliance Findings & ISO 31000 Risk Recalculation (Member 2 alignment)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import io
import os
import sys
import uuid

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
os.environ.setdefault("GEMINI_API_KEY", "test-key-for-supplier-tests")

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.platform.database import SessionLocal, init_db
from app.platform.models import Organization, Supplier, User, UserRole
from app.platform.security import create_access_token, hash_password


@pytest.fixture(scope="module")
def client():
    """Return a TestClient against the main FastAPI application."""
    init_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def seeded_tokens(client):
    """Authenticate the 4 core seeded accounts and return their tokens."""
    roles = ["admin", "auditor", "developer", "viewer"]
    tokens = {}
    for role in roles:
        resp = client.post("/api/auth/login", json={"username": role, "password": "esg2026"})
        assert resp.status_code == 200, f"Failed to login as {role}: {resp.text}"
        tokens[role] = resp.json()["access_token"]
    return tokens


@pytest.fixture(scope="module")
def tenant_fixture():
    """Create two isolated organizations with dedicated admin users for tenant isolation testing."""
    db = SessionLocal()
    try:
        suffix = uuid.uuid4().hex[:6]
        org_a = Organization(name=f"Tenant A {suffix}", slug=f"tenant-a-{suffix}")
        org_b = Organization(name=f"Tenant B {suffix}", slug=f"tenant-b-{suffix}")
        db.add_all([org_a, org_b])
        db.commit()
        db.refresh(org_a)
        db.refresh(org_b)

        user_a = User(
            organization_id=org_a.id,
            username=f"admin_a_{suffix}",
            email=f"admin_a_{suffix}@test.local",
            role=UserRole.ADMIN.value,
            hashed_password=hash_password("esg2026"),
            is_active=True,
        )
        user_b = User(
            organization_id=org_b.id,
            username=f"admin_b_{suffix}",
            email=f"admin_b_{suffix}@test.local",
            role=UserRole.ADMIN.value,
            hashed_password=hash_password("esg2026"),
            is_active=True,
        )
        db.add_all([user_a, user_b])
        db.commit()
        db.refresh(user_a)
        db.refresh(user_b)

        token_a = create_access_token(
    data={
        "sub": user_a.username,
        "user_id": user_a.id,
        "org_id": org_a.id,
        "role": user_a.role,
    }
)

        token_b = create_access_token(      
    data={
        "sub": user_b.username,
        "user_id": user_b.id,
        "org_id": org_b.id,
        "role": user_b.role,
    }
)

        return {
            "org_a": org_a,
            "org_b": org_b,
            "token_a": token_a,
            "token_b": token_b,
        }
    finally:
        db.close()


# ─── 1. Listing, Filtering & Statistics ───────────────────────────────────────

class TestSupplierListingAndStats:
    def test_supplier_stats_endpoint(self, client, seeded_tokens):
        headers = {"Authorization": f"Bearer {seeded_tokens['viewer']}"}
        resp = client.get("/api/suppliers/stats", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_suppliers" in data
        assert "high_risk_count" in data
        assert "expiring_documents_count" in data
        assert "average_esg_score" in data
        assert data["total_suppliers"] >= 5
        assert data["high_risk_count"] >= 1  # Vertex Manufacturing is high risk

    def test_list_suppliers_pagination(self, client, seeded_tokens):
        headers = {"Authorization": f"Bearer {seeded_tokens['viewer']}"}
        resp = client.get("/api/suppliers?page=1&page_size=2", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert len(data["items"]) == 2
        assert data["total"] >= 5
        assert data["total_pages"] >= 3

    def test_search_suppliers(self, client, seeded_tokens):
        headers = {"Authorization": f"Bearer {seeded_tokens['viewer']}"}
        resp = client.get("/api/suppliers?search=Vertex", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) >= 1
        assert any("Vertex" in s["name"] for s in data["items"])

    def test_filter_suppliers_by_category(self, client, seeded_tokens):
        headers = {"Authorization": f"Bearer {seeded_tokens['viewer']}"}
        resp = client.get("/api/suppliers?category=Packaging", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert "Packaging" in item["category"]

    def test_filter_suppliers_by_risk_level(self, client, seeded_tokens):
        headers = {"Authorization": f"Bearer {seeded_tokens['viewer']}"}
        resp = client.get("/api/suppliers?risk_level=HIGH", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) >= 1
        for item in data["items"]:
            assert item["risk_level"] == "HIGH"


# ─── 2. Multi-Tenant Isolation ────────────────────────────────────────────────

class TestSupplierTenantIsolation:
    def test_cross_tenant_isolation(self, client, tenant_fixture):
        token_a = tenant_fixture["token_a"]
        token_b = tenant_fixture["token_b"]

        # Org A onboards a supplier
        sup_data = {
            "name": "Tenant A Exclusive Supplier",
            "code": f"TEA-{uuid.uuid4().hex[:4]}",
            "category": "Raw Materials",
            "tier": "Tier 1",
            "country": "Germany",
            "contact_email": "supply@tenant-a.com",
            "status": "Active",
        }
        res_create = client.post(
            "/api/suppliers",
            json=sup_data,
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert res_create.status_code == 201
        created_id = res_create.json()["id"]

        # Org A can see the supplier
        res_get_a = client.get(
            f"/api/suppliers/{created_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert res_get_a.status_code == 200

        # Org B listing must NOT show Org A's supplier
        res_list_b = client.get(
            "/api/suppliers",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert res_list_b.status_code == 200
        b_ids = [s["id"] for s in res_list_b.json()["items"]]
        assert created_id not in b_ids

        # Org B direct GET must return 404 (multi-tenant boundary)
        res_get_b = client.get(
            f"/api/suppliers/{created_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert res_get_b.status_code == 404

        # Org B direct PUT must return 404
        res_put_b = client.put(
            f"/api/suppliers/{created_id}",
            json={"name": "Hacked Name"},
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert res_put_b.status_code == 404

        # Org B direct DELETE must return 404
        res_del_b = client.delete(
            f"/api/suppliers/{created_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert res_del_b.status_code == 404


# ─── 3. RBAC Enforcement ──────────────────────────────────────────────────────

class TestSupplierRBAC:
    def test_viewer_cannot_mutate(self, client, seeded_tokens):
        viewer_h = {"Authorization": f"Bearer {seeded_tokens['viewer']}"}

        # Viewer cannot create
        r_create = client.post(
            "/api/suppliers",
            json={
                "name": "Unauthorized Supplier",
                "code": "UNAUTH-01",
                "category": "IT",
                "tier": "Tier 3",
                "country": "UK",
                "contact_email": "unauth@test.com",
            },
            headers=viewer_h,
        )
        assert r_create.status_code == 403

        # Viewer cannot update
        r_update = client.put(
            "/api/suppliers/1",
            json={"name": "New Name"},
            headers=viewer_h,
        )
        assert r_update.status_code == 403

        # Viewer cannot delete
        r_del = client.delete("/api/suppliers/1", headers=viewer_h)
        assert r_del.status_code == 403

    def test_auditor_can_create_and_update_but_cannot_delete(self, client, seeded_tokens):
        auditor_h = {"Authorization": f"Bearer {seeded_tokens['auditor']}"}
        code = f"AUD-{uuid.uuid4().hex[:4]}"

        # Auditor can create
        r_create = client.post(
            "/api/suppliers",
            json={
                "name": f"Auditor Created {code}",
                "code": code,
                "category": "Logistics",
                "tier": "Tier 2",
                "country": "France",
                "contact_email": f"audit_{code}@test.com",
            },
            headers=auditor_h,
        )
        assert r_create.status_code == 201
        new_id = r_create.json()["id"]

        # Auditor can update
        r_update = client.put(
            f"/api/suppliers/{new_id}",
            json={"tier": "Tier 1"},
            headers=auditor_h,
        )
        assert r_update.status_code == 200
        assert r_update.json()["tier"] == "Tier 1"

        # Auditor CANNOT delete (Admin only safeguard)
        r_del = client.delete(f"/api/suppliers/{new_id}", headers=auditor_h)
        assert r_del.status_code == 403

        # Admin can delete
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}
        r_del_admin = client.delete(f"/api/suppliers/{new_id}", headers=admin_h)
        assert r_del_admin.status_code == 200


# ─── 4. Supplier CRUD & Duplicate Rejection ───────────────────────────────────

class TestSupplierCRUD:
    def test_duplicate_code_rejected(self, client, seeded_tokens):
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}
        code = f"DUP-{uuid.uuid4().hex[:4]}"

        r1 = client.post(
            "/api/suppliers",
            json={
                "name": "Supplier One",
                "code": code,
                "category": "Manufacturing",
                "tier": "Tier 1",
                "country": "Germany",
                "contact_email": "dup1@test.com",
            },
            headers=admin_h,
        )
        assert r1.status_code == 201

        # Second create with duplicate code must fail with 400
        r2 = client.post(
            "/api/suppliers",
            json={
                "name": "Supplier Duplicate",
                "code": code.lower(),  # test case-insensitivity
                "category": "Manufacturing",
                "tier": "Tier 1",
                "country": "Germany",
                "contact_email": "dup2@test.com",
            },
            headers=admin_h,
        )
        assert r2.status_code == 400
        assert "already exists" in r2.json()["detail"]


# ─── 5. Document Uploads & Expiry Tracking ────────────────────────────────────

class TestSupplierDocumentsAndExpiry:
    def test_document_upload_and_expiry_statuses(self, client, seeded_tokens):
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}

        # 1. Create a dedicated test supplier
        code = f"DOC-{uuid.uuid4().hex[:4]}"
        r_sup = client.post(
            "/api/suppliers",
            json={
                "name": f"Document Test Supplier {code}",
                "code": code,
                "category": "Electronics & Hardware",
                "tier": "Tier 1",
                "country": "Sweden",
                "contact_email": f"doc_{code}@test.com",
            },
            headers=admin_h,
        )
        sup_id = r_sup.json()["id"]

        # Helper to upload doc
        def upload(title: str, doc_type: str, expiry: str):
            file_bytes = b"%PDF-1.4 test certificate binary content for audit"
            return client.post(
                f"/api/suppliers/{sup_id}/documents",
                headers=admin_h,
                data={
                    "title": title,
                    "document_type": doc_type,
                    "expiry_date": expiry,
                    "notes": "Automated verification test",
                },
                files={"file": ("certificate.pdf", io.BytesIO(file_bytes), "application/pdf")},
            )

        now = datetime.now(timezone.utc)
        valid_date = (now + timedelta(days=120)).strftime("%Y-%m-%d")
        expiring_date = (now + timedelta(days=10)).strftime("%Y-%m-%d")
        expired_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")

        # Upload Valid Doc
        r_valid = upload("Valid ISO 14001", "ISO 14001", valid_date)
        assert r_valid.status_code == 201
        assert r_valid.json()["expiry_status"] == "VALID"
        assert r_valid.json()["days_until_expiry"] > 30

        # Upload Expiring Soon Doc
        r_expiring = upload("Expiring Fleet Audit", "Carbon Audit", expiring_date)
        assert r_expiring.status_code == 201
        assert r_expiring.json()["expiry_status"] == "EXPIRING_SOON"
        assert 0 <= r_expiring.json()["days_until_expiry"] <= 30

        # Upload Expired Doc
        r_expired = upload("Expired Labour Audit", "SA 8000", expired_date)
        assert r_expired.status_code == 201
        assert r_expired.json()["expiry_status"] == "EXPIRED"
        assert r_expired.json()["days_until_expiry"] < 0

        # Verify listing reflects all documents
        r_list = client.get(f"/api/suppliers/{sup_id}/documents", headers=admin_h)
        assert r_list.status_code == 200
        docs = r_list.json()
        assert len(docs) == 3


# ─── 6. Findings & ISO 31000 Risk Recalculation ───────────────────────────────

class TestSupplierFindingsAndRiskEvaluation:
    def test_iso31000_evaluation_consistency(self, client, seeded_tokens):
        auditor_h = {"Authorization": f"Bearer {seeded_tokens['auditor']}"}

        # 1. Create a dedicated test supplier
        code = f"RSK-{uuid.uuid4().hex[:4]}"
        r_sup = client.post(
            "/api/suppliers",
            json={
                "name": f"Risk Evaluation Supplier {code}",
                "code": code,
                "category": "Heavy Manufacturing",
                "tier": "Tier 1",
                "country": "Germany",
                "contact_email": f"risk_{code}@test.com",
            },
            headers=auditor_h,
        )
        sup_id = r_sup.json()["id"]

        # 2. Add a Critical finding: Likelihood 4, Impact 5
        # ISO 31000 formula: round(((4 * 5) / 25.0) * 100.0, 2) = 80.0 -> CRITICAL
        r_f1 = client.post(
            f"/api/suppliers/{sup_id}/findings",
            json={
                "title": "Severe chemical discharge without treatment",
                "category": "Environmental",
                "severity": "Critical",
                "likelihood": 4,
                "impact": 5,
                "description": "Unauthorized effluent discharge observed in river basin.",
                "recommendation": "Halt operation line 2 and implement filtration system.",
                "status": "Open",
            },
            headers=auditor_h,
        )
        assert r_f1.status_code == 201
        assert r_f1.json()["risk_score"] == 80.0

        # 3. Add a Moderate finding: Likelihood 3, Impact 3
        # ISO 31000 formula: round(((3 * 3) / 25.0) * 100.0, 2) = 36.0 -> MODERATE
        r_f2 = client.post(
            f"/api/suppliers/{sup_id}/findings",
            json={
                "title": "Working hours log inconsistency",
                "category": "Social",
                "severity": "Medium",
                "likelihood": 3,
                "impact": 3,
                "description": "Overtime logs in warehouse B contain manual gaps.",
                "recommendation": "Transition to digital biometric timekeeping.",
                "status": "Open",
            },
            headers=auditor_h,
        )
        assert r_f2.status_code == 201
        assert r_f2.json()["risk_score"] == 36.0

        # 4. Trigger evaluate endpoint (findings & certificate mode)
        r_eval = client.post(f"/api/suppliers/{sup_id}/evaluate?policy_comparison=false", headers=auditor_h)
        assert r_eval.status_code == 200
        eval_data = r_eval.json()

        # Average risk = (80 + 36) / 2 = 58.0 -> HIGH (since >= 40.0)
        assert eval_data["risk_score"] == 58.0
        assert eval_data["risk_level"] == "HIGH"
        # Environmental subscore = 100 - 80 = 20.0
        assert eval_data["environmental_score"] == 20.0
        # Social subscore = 100 - 36 = 64.0
        assert eval_data["social_score"] == 64.0
        # Governance baseline = 88.0
        assert eval_data["governance_score"] == 88.0
        # Overall = round((20.0 + 64.0 + 88.0) / 3.0, 2) = 57.33
        assert eval_data["overall_score"] == 57.33
        assert "ISO 31000" in eval_data["methodology"]

        # 5. Verify supplier record in DB updated
        r_sup_detail = client.get(f"/api/suppliers/{sup_id}", headers=auditor_h)
        assert r_sup_detail.status_code == 200
        sup_detail = r_sup_detail.json()
        assert sup_detail["risk_score"] == 58.0
        assert sup_detail["risk_level"] == "HIGH"
        assert sup_detail["overall_score"] == 57.33
        assert len(sup_detail["findings"]) == 2


# ─── 7. Phase 5C: Member 2 Deep Integration & Document Security ────────────────

import zipfile
import httpx


def _make_valid_docx() -> bytes:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types></Types>')
        z.writestr("word/document.xml", '<?xml version="1.0"?><w:document></w:document>')
    return bio.getvalue()


def _make_valid_xlsx() -> bytes:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types></Types>')
        z.writestr("xl/workbook.xml", '<?xml version="1.0"?><workbook></workbook>')
    return bio.getvalue()


class TestPhase5CSupplierRiskIntegrationAndSecurity:
    """Verifies Phase 5C Member 2 Risk Engine integration, fallback, and document security."""

    def test_baseline_policy_lifecycle_and_rbac(self, client, seeded_tokens):
        viewer_h = {"Authorization": f"Bearer {seeded_tokens['viewer']}"}
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}

        # 1. Viewer forbidden from uploading enterprise baseline policy (HTTP 403)
        dummy_pdf = b"%PDF-1.4 Enterprise Standard ESG Baseline 2026"
        r_forbidden = client.post(
            "/api/platform/organizations/current/baseline-policy",
            headers=viewer_h,
            files={"file": ("baseline.pdf", io.BytesIO(dummy_pdf), "application/pdf")},
        )
        assert r_forbidden.status_code == 403

        # 2. Admin successfully uploads enterprise baseline policy
        r_upload = client.post(
            "/api/platform/organizations/current/baseline-policy",
            headers=admin_h,
            files={"file": ("acme_baseline_policy.pdf", io.BytesIO(dummy_pdf), "application/pdf")},
        )
        assert r_upload.status_code == 200
        data = r_upload.json()
        assert data["is_configured"] is True
        assert data["baseline_policy_name"] == "acme_baseline_policy.pdf"

        # 3. Viewer can view baseline policy metadata
        r_get = client.get("/api/platform/organizations/current/baseline-policy", headers=viewer_h)
        assert r_get.status_code == 200
        assert r_get.json()["is_configured"] is True
        assert r_get.json()["baseline_policy_name"] == "acme_baseline_policy.pdf"

    def test_file_upload_security_restrictions(self, client, seeded_tokens):
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}

        # Create supplier for testing uploads
        code = f"SEC-{uuid.uuid4().hex[:4]}"
        r_sup = client.post(
            "/api/suppliers",
            json={
                "name": f"Security Test Supplier {code}",
                "code": code,
                "category": "Services",
                "tier": "Tier 1",
                "country": "Germany",
                "contact_email": f"sec_{code}@test.com",
            },
            headers=admin_h,
        )
        sup_id = r_sup.json()["id"]

        # 1. Reject unauthorized extension (.exe)
        r_exe = client.post(
            f"/api/suppliers/{sup_id}/documents",
            headers=admin_h,
            data={"title": "Malicious Exe", "document_type": "Environmental Policy"},
            files={"file": ("malware.exe", io.BytesIO(b"MZ\x90\x00executable"), "application/x-msdownload")},
        )
        assert r_exe.status_code == 400
        assert "not permitted" in r_exe.text

        # 2. Reject fake PDF without %PDF header
        r_fake_pdf = client.post(
            f"/api/suppliers/{sup_id}/documents",
            headers=admin_h,
            data={"title": "Fake PDF", "document_type": "Environmental Policy"},
            files={"file": ("fake.pdf", io.BytesIO(b"This is not a real PDF file"), "application/pdf")},
        )
        assert r_fake_pdf.status_code == 400
        assert "Missing %PDF" in r_fake_pdf.text

        # 3. Reject fake DOCX (ZIP without word/document.xml)
        fake_zip = io.BytesIO()
        with zipfile.ZipFile(fake_zip, "w") as z:
            z.writestr("random.txt", "just a text file inside zip")
        r_fake_docx = client.post(
            f"/api/suppliers/{sup_id}/documents",
            headers=admin_h,
            data={"title": "Fake DOCX", "document_type": "Environmental Policy"},
            files={"file": ("fake.docx", io.BytesIO(fake_zip.getvalue()), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert r_fake_docx.status_code == 400
        assert "Missing required OpenXML" in r_fake_docx.text

        # 4. Accept valid DOCX with OpenXML structure
        valid_docx = _make_valid_docx()
        r_valid_docx = client.post(
            f"/api/suppliers/{sup_id}/documents",
            headers=admin_h,
            data={"title": "Valid Policy Docx", "document_type": "Environmental Policy"},
            files={"file": ("valid_policy.docx", io.BytesIO(valid_docx), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert r_valid_docx.status_code == 201
        assert r_valid_docx.json()["document_category"] == "POLICY"

        # 5. Accept valid XLSX with OpenXML structure
        valid_xlsx = _make_valid_xlsx()
        r_valid_xlsx = client.post(
            f"/api/suppliers/{sup_id}/documents",
            headers=admin_h,
            data={"title": "Valid Audit Spreadsheet", "document_type": "ESG Audit"},
            files={"file": ("audit_metrics.xlsx", io.BytesIO(valid_xlsx), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert r_valid_xlsx.status_code == 201

        # 6. Reject text with null bytes
        r_null_txt = client.post(
            f"/api/suppliers/{sup_id}/documents",
            headers=admin_h,
            data={"title": "Corrupt Text", "document_type": "General"},
            files={"file": ("notes.txt", io.BytesIO(b"Hello\x00World"), "text/plain")},
        )
        assert r_null_txt.status_code == 400
        assert "null bytes" in r_null_txt.text

    def test_evaluate_rejects_certificate_for_policy_comparison(self, client, seeded_tokens):
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}

        code = f"CAT-{uuid.uuid4().hex[:4]}"
        r_sup = client.post(
            "/api/suppliers",
            json={
                "name": f"Category Test Supplier {code}",
                "code": code,
                "category": "Manufacturing",
                "tier": "Tier 1",
                "country": "Germany",
                "contact_email": f"cat_{code}@test.com",
            },
            headers=admin_h,
        )
        sup_id = r_sup.json()["id"]

        # Upload an ISO 14001 certificate
        r_cert = client.post(
            f"/api/suppliers/{sup_id}/documents",
            headers=admin_h,
            data={"title": "ISO 14001 Certificate", "document_type": "ISO 14001"},
            files={"file": ("iso14001.pdf", io.BytesIO(b"%PDF-1.4 Certificate"), "application/pdf")},
        )
        assert r_cert.status_code == 201
        cert_id = r_cert.json()["id"]
        assert r_cert.json()["document_category"] == "CERTIFICATE"

        # Calling evaluate with certificate document_id must fail with HTTP 400
        r_eval = client.post(
            f"/api/suppliers/{sup_id}/evaluate?document_id={cert_id}&policy_comparison=true",
            headers=admin_h,
        )
        assert r_eval.status_code == 400
        assert "classified as a CERTIFICATE" in r_eval.text

    def test_evaluate_requires_baseline_policy(self, client, tenant_fixture):
        # Tenant B has no baseline policy uploaded
        token_b = tenant_fixture["token_b"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        code = f"NOBASE-{uuid.uuid4().hex[:4]}"
        r_sup = client.post(
            "/api/suppliers",
            json={
                "name": f"Supplier Without Baseline {code}",
                "code": code,
                "category": "Logistics",
                "tier": "Tier 1",
                "country": "Germany",
                "contact_email": f"nobase_{code}@test.com",
            },
            headers=headers_b,
        )
        sup_id = r_sup.json()["id"]

        # Upload a policy document
        client.post(
            f"/api/suppliers/{sup_id}/documents",
            headers=headers_b,
            data={"title": "Supplier Code of Conduct", "document_type": "Code of Conduct"},
            files={"file": ("policy.pdf", io.BytesIO(b"%PDF-1.4 Policy"), "application/pdf")},
        )

        # Evaluating with policy_comparison=True must fail because Tenant B has no baseline policy configured
        r_eval = client.post(
            f"/api/suppliers/{sup_id}/evaluate?policy_comparison=true",
            headers=headers_b,
        )
        assert r_eval.status_code == 400
        assert "Enterprise baseline policy is not configured" in r_eval.text

    def test_evaluate_requires_supplier_policy(self, client, seeded_tokens):
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}

        # Seed organization has baseline policy configured from previous test
        code = f"NOPOL-{uuid.uuid4().hex[:4]}"
        r_sup = client.post(
            "/api/suppliers",
            json={
                "name": f"Supplier Without Policy {code}",
                "code": code,
                "category": "Logistics",
                "tier": "Tier 1",
                "country": "Germany",
                "contact_email": f"nopol_{code}@test.com",
            },
            headers=admin_h,
        )
        sup_id = r_sup.json()["id"]

        # Supplier has NO policy documents uploaded
        r_eval = client.post(
            f"/api/suppliers/{sup_id}/evaluate?policy_comparison=true",
            headers=admin_h,
        )
        assert r_eval.status_code == 400
        assert "No policy document found for this supplier" in r_eval.text

    def test_cross_tenant_document_download_isolation(self, client, tenant_fixture):
        token_a = tenant_fixture["token_a"]
        token_b = tenant_fixture["token_b"]

        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # Tenant A creates supplier & uploads document
        r_sup = client.post(
            "/api/suppliers",
            json={
                "name": "Tenant A Supplier",
                "code": f"TNA-{uuid.uuid4().hex[:4]}",
                "category": "Logistics",
                "tier": "Tier 1",
                "country": "Germany",
                "contact_email": "tna@test.com",
            },
            headers=headers_a,
        )
        sup_a_id = r_sup.json()["id"]

        r_doc = client.post(
            f"/api/suppliers/{sup_a_id}/documents",
            headers=headers_a,
            data={"title": "Confidential Tenant A Document", "document_type": "Environmental Policy"},
            files={"file": ("confidential.pdf", io.BytesIO(b"%PDF-1.4 Secret Tenant A Data"), "application/pdf")},
        )
        assert r_doc.status_code == 201
        doc_id = r_doc.json()["id"]

        # Tenant A can download the document
        r_dl_a = client.get(f"/api/suppliers/{sup_a_id}/documents/{doc_id}/download", headers=headers_a)
        assert r_dl_a.status_code == 200
        assert b"%PDF-1.4 Secret Tenant A Data" in r_dl_a.content

        # Tenant B cannot download Tenant A's document (HTTP 404)
        r_dl_b = client.get(f"/api/suppliers/{sup_a_id}/documents/{doc_id}/download", headers=headers_b)
        assert r_dl_b.status_code == 404

    def test_evaluate_member2_remote_api_success(self, client, seeded_tokens, monkeypatch):
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}

        code = f"M2OK-{uuid.uuid4().hex[:4]}"
        r_sup = client.post(
            "/api/suppliers",
            json={
                "name": f"Member 2 Remote Supplier {code}",
                "code": code,
                "category": "Packaging",
                "tier": "Tier 1",
                "country": "France",
                "contact_email": f"m2_{code}@test.com",
            },
            headers=admin_h,
        )
        sup_id = r_sup.json()["id"]

        # Upload a valid policy document
        r_doc = client.post(
            f"/api/suppliers/{sup_id}/documents",
            headers=admin_h,
            data={"title": "Supplier Environmental Policy", "document_type": "Environmental Policy"},
            files={"file": ("supplier_env_policy.pdf", io.BytesIO(b"%PDF-1.4 Supplier Policy"), "application/pdf")},
        )
        assert r_doc.status_code == 201
        doc_id = r_doc.json()["id"]

        # Mock Member 2 response conforming to its exact RiskReportResponse schema
        mock_m2_response = {
            "old_filename": "acme_baseline_policy.pdf",
            "new_filename": "supplier_env_policy.pdf",
            "risk_count": 2,
            "high_or_critical_count": 1,
            "risks": [
                {
                    "commitment_id": "ENV-01",
                    "category": "Environmental",
                    "classification": "Emissions Gap",
                    "severity": "High",
                    "likelihood": 4,
                    "impact": 4,
                    "risk_score": 64.0,
                    "explanation": "Supplier lacks Scope 3 reduction milestones present in enterprise baseline.",
                    "recommendation": "Adopt enterprise-aligned Scope 3 trajectory.",
                },
                {
                    "commitment_id": "SOC-01",
                    "category": "Social",
                    "classification": "Labour Audit Variance",
                    "severity": "Medium",
                    "likelihood": 3,
                    "impact": 3,
                    "risk_score": 36.0,
                    "explanation": "Audit frequency is biennial instead of annual.",
                    "recommendation": "Align audit cadence to annual standard.",
                },
            ],
            "esg_scores": {
                "environmental": 68.0,
                "social": 82.0,
                "governance": 85.0,
                "overall": 78.33,
                "method": "ISO 31000 + ESG Weighted",
            },
            "formula": {},
        }

        orig_send = httpx.Client.send

        def mock_send(self, request, *args, **kwargs):
            if "api/risk-report" in str(request.url):
                return httpx.Response(200, json=mock_m2_response, request=request)
            return orig_send(self, request, *args, **kwargs)

        monkeypatch.setattr(httpx.Client, "send", mock_send)

        # Trigger policy comparison evaluation
        r_eval = client.post(
            f"/api/suppliers/{sup_id}/evaluate?document_id={doc_id}&policy_comparison=true",
            headers=admin_h,
        )
        assert r_eval.status_code == 200
        res = r_eval.json()

        assert res["evaluation_mode"] == "MEMBER2_REMOTE_API"
        assert res["service_status"] == "ONLINE"
        assert "Member 2 Policy Risk Engine" in res["evaluated_by"]
        # Expected risk_score = arithmetic mean of (64.0 + 36.0) / 2 = 50.0 -> HIGH
        assert res["risk_score"] == 50.0
        assert res["risk_level"] == "HIGH"
        assert res["environmental_score"] == 68.0
        assert res["social_score"] == 82.0
        assert res["governance_score"] == 85.0
        assert res["overall_score"] == 78.33
        assert res["fallback_reason"] is None

        # Verify findings were ingested into database
        r_findings = client.get(f"/api/suppliers/{sup_id}/findings", headers=admin_h)
        assert r_findings.status_code == 200
        findings = r_findings.json()
        assert len(findings) >= 2
        titles = [f["title"] for f in findings]
        assert any("Emissions Gap" in t for t in titles)

    def test_evaluate_member2_connection_error_fallback(self, client, seeded_tokens, monkeypatch):
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}

        code = f"M2FB-{uuid.uuid4().hex[:4]}"
        r_sup = client.post(
            "/api/suppliers",
            json={
                "name": f"Fallback Supplier {code}",
                "code": code,
                "category": "Logistics",
                "tier": "Tier 1",
                "country": "Germany",
                "contact_email": f"fb_{code}@test.com",
            },
            headers=admin_h,
        )
        sup_id = r_sup.json()["id"]

        # Upload policy document
        r_doc = client.post(
            f"/api/suppliers/{sup_id}/documents",
            headers=admin_h,
            data={"title": "Supplier Labour Policy", "document_type": "Labour Policy"},
            files={"file": ("labour_policy.pdf", io.BytesIO(b"%PDF-1.4 Policy"), "application/pdf")},
        )
        assert r_doc.status_code == 201

        # Simulate network failure to Member 2 (ConnectError)
        orig_send = httpx.Client.send

        def mock_send_fail(self, request, *args, **kwargs):
            if "api/risk-report" in str(request.url):
                raise httpx.ConnectError("Connection refused by remote host")
            return orig_send(self, request, *args, **kwargs)

        monkeypatch.setattr(httpx.Client, "send", mock_send_fail)

        # Trigger evaluation — should engage graceful fallback
        r_eval = client.post(
            f"/api/suppliers/{sup_id}/evaluate?policy_comparison=true",
            headers=admin_h,
        )
        assert r_eval.status_code == 200
        res = r_eval.json()

        assert res["evaluation_mode"] == "LOCAL_ISO31000_ADAPTER_FALLBACK"
        assert res["service_status"] == "OFFLINE"
        assert "Member 5 ISO 31000 Fallback Adapter" in res["evaluated_by"]
        assert "Connection to Member 2 service failed" in res["fallback_reason"]

    def test_evaluate_member2_remote_500_raises_502(self, client, seeded_tokens, monkeypatch):
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}

        code = f"M2E500-{uuid.uuid4().hex[:4]}"
        r_sup = client.post(
            "/api/suppliers",
            json={
                "name": f"Error Supplier {code}",
                "code": code,
                "category": "Chemicals",
                "tier": "Tier 1",
                "country": "Germany",
                "contact_email": f"err_{code}@test.com",
            },
            headers=admin_h,
        )
        sup_id = r_sup.json()["id"]

        r_doc = client.post(
            f"/api/suppliers/{sup_id}/documents",
            headers=admin_h,
            data={"title": "Chemical Safety Policy", "document_type": "Environmental Policy"},
            files={"file": ("chem_policy.pdf", io.BytesIO(b"%PDF-1.4 Chem Safety"), "application/pdf")},
        )
        assert r_doc.status_code == 201

        orig_send = httpx.Client.send

        def mock_send_500(self, request, *args, **kwargs):
            if "api/risk-report" in str(request.url):
                return httpx.Response(500, text="Internal PDF parser crashed", request=request)
            return orig_send(self, request, *args, **kwargs)

        monkeypatch.setattr(httpx.Client, "send", mock_send_500)

        # Calling evaluate must NOT fall back silently — must raise HTTP 502
        r_eval = client.post(
            f"/api/suppliers/{sup_id}/evaluate?policy_comparison=true",
            headers=admin_h,
        )
        assert r_eval.status_code == 502
        assert "server error (500)" in r_eval.text

    def test_evaluate_member2_remote_400_raises_400(self, client, seeded_tokens, monkeypatch):
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}

        code = f"M2E400-{uuid.uuid4().hex[:4]}"
        r_sup = client.post(
            "/api/suppliers",
            json={
                "name": f"Bad Request Supplier {code}",
                "code": code,
                "category": "Logistics",
                "tier": "Tier 1",
                "country": "Germany",
                "contact_email": f"badr_{code}@test.com",
            },
            headers=admin_h,
        )
        sup_id = r_sup.json()["id"]

        r_doc = client.post(
            f"/api/suppliers/{sup_id}/documents",
            headers=admin_h,
            data={"title": "Corrupt Policy Document", "document_type": "Environmental Policy"},
            files={"file": ("corrupt_policy.pdf", io.BytesIO(b"%PDF-1.4 Corrupt stream"), "application/pdf")},
        )
        assert r_doc.status_code == 201

        orig_send = httpx.Client.send

        def mock_send_400(self, request, *args, **kwargs):
            if "api/risk-report" in str(request.url):
                return httpx.Response(400, text="PDF unreadable or password protected", request=request)
            return orig_send(self, request, *args, **kwargs)

        monkeypatch.setattr(httpx.Client, "send", mock_send_400)

        # Calling evaluate must return HTTP 400 with detail from Member 2
        r_eval = client.post(
            f"/api/suppliers/{sup_id}/evaluate?policy_comparison=true",
            headers=admin_h,
        )
        assert r_eval.status_code == 400
        assert "Member 2 risk engine rejected" in r_eval.text

    def test_evaluate_member2_schema_error_raises_502(self, client, seeded_tokens, monkeypatch):
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}

        code = f"M2ESCH-{uuid.uuid4().hex[:4]}"
        r_sup = client.post(
            "/api/suppliers",
            json={
                "name": f"Schema Error Supplier {code}",
                "code": code,
                "category": "Logistics",
                "tier": "Tier 1",
                "country": "Germany",
                "contact_email": f"esch_{code}@test.com",
            },
            headers=admin_h,
        )
        sup_id = r_sup.json()["id"]

        r_doc = client.post(
            f"/api/suppliers/{sup_id}/documents",
            headers=admin_h,
            data={"title": "Policy Document", "document_type": "Environmental Policy"},
            files={"file": ("policy.pdf", io.BytesIO(b"%PDF-1.4 Valid Policy"), "application/pdf")},
        )
        assert r_doc.status_code == 201

        orig_send = httpx.Client.send

        def mock_send_bad_schema(self, request, *args, **kwargs):
            if "api/risk-report" in str(request.url):
                # Returns 200 but missing 'esg_scores' and 'risks'
                return httpx.Response(200, json={"unexpected": "schema"}, request=request)
            return orig_send(self, request, *args, **kwargs)

        monkeypatch.setattr(httpx.Client, "send", mock_send_bad_schema)

        # Calling evaluate must fail with HTTP 502 schema contract violation
        r_eval = client.post(
            f"/api/suppliers/{sup_id}/evaluate?policy_comparison=true",
            headers=admin_h,
        )
        assert r_eval.status_code == 502
        assert "missing required contract fields" in r_eval.text


# ─── 8. Database Migration & Data Preservation Tests ─────────────────────────

class TestDatabaseMigrationAndPreservation:
    """Verifies that database schema migration preserves valid assessed and ambiguous
    historical records while safely migrating unassessed suppliers to NOT_ASSESSED.
    """

    def test_sqlite_migration_preserves_assessed_and_migrates_unassessed(self, tmp_path):
        import sqlite3
        from sqlalchemy import create_engine, text
        import app.platform.database as db_module

        # 1. Create an isolated SQLite database using the legacy pre-Phase 5C schema
        db_file = tmp_path / "legacy_migration_test.db"
        conn = sqlite3.connect(str(db_file))

        # Enable foreign keys initially
        conn.execute("PRAGMA foreign_keys = ON;")

        # Create organizations table
        conn.execute("""
            CREATE TABLE organizations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(255) NOT NULL,
                slug VARCHAR(100) UNIQUE NOT NULL,
                industry VARCHAR(150),
                reporting_period VARCHAR(50),
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
        """)

        # Create suppliers table with legacy NOT NULL constraints on risk_score and default 'LOW'
        conn.execute("""
            CREATE TABLE suppliers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                name VARCHAR(255) NOT NULL,
                code VARCHAR(50) NOT NULL,
                category VARCHAR(100) NOT NULL,
                tier VARCHAR(20) NOT NULL,
                country VARCHAR(100) NOT NULL,
                contact_person VARCHAR(255),
                contact_email VARCHAR(255) NOT NULL,
                contact_phone VARCHAR(50),
                status VARCHAR(50) NOT NULL,
                risk_score FLOAT NOT NULL DEFAULT 0.0,
                risk_level VARCHAR(50) NOT NULL DEFAULT 'LOW',
                environmental_score FLOAT NOT NULL DEFAULT 80.0,
                social_score FLOAT NOT NULL DEFAULT 80.0,
                governance_score FLOAT NOT NULL DEFAULT 80.0,
                overall_score FLOAT NOT NULL DEFAULT 80.0,
                last_assessment_date DATETIME,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
        """)
        conn.execute("CREATE INDEX ix_suppliers_id ON suppliers (id);")
        conn.execute("CREATE INDEX ix_suppliers_organization_id ON suppliers (organization_id);")
        conn.execute("CREATE INDEX ix_suppliers_name ON suppliers (name);")
        conn.execute("CREATE INDEX ix_suppliers_code ON suppliers (code);")

        # Create supplier_documents table
        conn.execute("""
            CREATE TABLE supplier_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                supplier_id INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
                document_type VARCHAR(100) NOT NULL,
                title VARCHAR(255) NOT NULL,
                file_path VARCHAR(500) NOT NULL,
                file_size INTEGER NOT NULL DEFAULT 0,
                mime_type VARCHAR(100) NOT NULL DEFAULT 'application/pdf',
                issue_date DATETIME,
                expiry_date DATETIME,
                verification_status VARCHAR(50) NOT NULL DEFAULT 'Verified',
                notes TEXT,
                uploaded_at DATETIME NOT NULL
            );
        """)

        # Create supplier_findings table
        conn.execute("""
            CREATE TABLE supplier_findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                supplier_id INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
                title VARCHAR(255) NOT NULL,
                category VARCHAR(50) NOT NULL DEFAULT 'Governance',
                severity VARCHAR(50) NOT NULL DEFAULT 'Medium',
                likelihood INTEGER NOT NULL DEFAULT 3,
                impact INTEGER NOT NULL DEFAULT 3,
                risk_score FLOAT NOT NULL DEFAULT 36.0,
                description TEXT NOT NULL,
                recommendation TEXT NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'Open',
                identified_date DATETIME NOT NULL,
                resolved_date DATETIME,
                created_at DATETIME NOT NULL
            );
        """)

        # Seed organization
        now_str = "2026-11-10 12:00:00"
        conn.execute(f"INSERT INTO organizations VALUES (1, 'Acme Corp', 'acme', 'Logistics', 'FY26', '{now_str}', '{now_str}');")

        # Seed:
        # 1. Assessed supplier (last_assessment_date IS NOT NULL, risk_score = 16.0, risk_level = 'LOW')
        conn.execute(f"""
            INSERT INTO suppliers VALUES (
                1, 1, 'Assessed Supplier Apex', 'SUP-001', 'Mfg', 'Tier 1', 'DE',
                'Hans', 'hans@apex.de', '123', 'Active',
                16.0, 'LOW', 85.0, 80.0, 85.0, 83.33, '2026-10-29 08:00:00',
                '{now_str}', '{now_str}'
            );
        """)

        # 2. Unassessed supplier (last_assessment_date IS NULL, risk_score = 0.0, risk_level = 'LOW', 0 findings)
        conn.execute(f"""
            INSERT INTO suppliers VALUES (
                2, 1, 'Unassessed Supplier New', 'SUP-002', 'Mfg', 'Tier 1', 'DE',
                'Fritz', 'fritz@new.de', '456', 'Active',
                0.0, 'LOW', 80.0, 80.0, 80.0, 80.0, NULL,
                '{now_str}', '{now_str}'
            );
        """)

        # 3. Ambiguous legacy supplier (last_assessment_date IS NULL, but risk_score = 52.0, risk_level = 'HIGH', has finding)
        conn.execute(f"""
            INSERT INTO suppliers VALUES (
                3, 1, 'Ambiguous Supplier Legacy', 'SUP-003', 'Mfg', 'Tier 2', 'FR',
                'Claire', 'claire@leg.fr', '789', 'Active',
                52.0, 'HIGH', 70.0, 75.0, 80.0, 75.0, NULL,
                '{now_str}', '{now_str}'
            );
        """)
        conn.execute(f"""
            INSERT INTO supplier_findings VALUES (
                1, 3, 'Legacy Finding', 'Social', 'High', 4, 4, 52.0, 'Desc', 'Rec', 'Open', '{now_str}', NULL, '{now_str}'
            );
        """)

        # Add document referencing supplier 1
        conn.execute(f"""
            INSERT INTO supplier_documents VALUES (
                1, 1, 'ISO 14001', 'Certificate 14001', 'uploads/test.pdf', 100, 'application/pdf', NULL, NULL, 'Verified', NULL, '{now_str}'
            );
        """)
        conn.commit()
        conn.close()

        # 2. Run _run_migrations using a fresh engine pointing to this db
        test_engine = create_engine(f"sqlite:///{db_file}")

        # Reset _migrations_applied flag to ensure test migration executes
        saved_flag = db_module._migrations_applied
        try:
            db_module._migrations_applied = False
            db_module._run_migrations(test_engine)
        finally:
            db_module._migrations_applied = saved_flag

        # 3. Inspect the migrated database
        conn = sqlite3.connect(str(db_file))
        cur = conn.cursor()

        # Verify PRAGMA foreign_key_check is completely clean
        fk_violations = cur.execute("PRAGMA foreign_key_check;").fetchall()
        assert fk_violations == [], f"Foreign key violations detected: {fk_violations}"

        # Verify risk_score is nullable (notnull == 0)
        table_info = cur.execute("PRAGMA table_info(suppliers);").fetchall()
        score_col = next(c for c in table_info if c[1] == "risk_score")
        assert score_col[3] == 0, f"Expected risk_score to be nullable, got {score_col}"

        # Verify newly added columns in other tables
        org_cols = [c[1] for c in cur.execute("PRAGMA table_info(organizations);").fetchall()]
        assert "baseline_policy_path" in org_cols
        assert "baseline_policy_name" in org_cols

        doc_cols = [c[1] for c in cur.execute("PRAGMA table_info(supplier_documents);").fetchall()]
        assert "document_category" in doc_cols

        # Verify data preservation
        rows = {r[0]: r for r in cur.execute("SELECT id, name, risk_score, risk_level, last_assessment_date FROM suppliers;").fetchall()}

        # Supplier 1: Assessed supplier must retain exact scores and levels
        assert rows[1][2] == 16.0
        assert rows[1][3] == "LOW"
        assert rows[1][4] == "2026-10-29 08:00:00"

        # Supplier 2: Unassessed supplier must be migrated to None and NOT_ASSESSED
        assert rows[2][2] is None
        assert rows[2][3] == "NOT_ASSESSED"
        assert rows[2][4] is None

        # Supplier 3: Ambiguous supplier must preserve assessment data (52.0, HIGH)
        assert rows[3][2] == 52.0
        assert rows[3][3] == "HIGH"

        # Verify inserting a new record with NULL risk_score succeeds without error
        cur.execute(f"""
            INSERT INTO suppliers (
                organization_id, name, code, category, tier, country, contact_email, status,
                risk_score, risk_level, environmental_score, social_score, governance_score,
                overall_score, created_at, updated_at
            ) VALUES (
                1, 'Null Insert Supplier', 'SUP-NULL', 'Mfg', 'Tier 1', 'DE', 'null@test.com', 'Active',
                NULL, 'NOT_ASSESSED', 80.0, 80.0, 80.0, 80.0, '{now_str}', '{now_str}'
            );
        """)
        conn.commit()
        conn.close()


# ─── 9. Supplier Risk Evaluation Correctness (NOT_ASSESSED vs Populated) ────

class TestSupplierRiskEvaluationCorrectness:
    """Verifies that empty Member 2 risk results produce NOT_ASSESSED with risk_score = None,
    while populated risk findings compute correct aggregate ISO 31000 risk scores.
    """

    def test_evaluate_member2_empty_risks_yields_not_assessed(self, client, seeded_tokens, monkeypatch):
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}

        # 1. Ensure enterprise baseline policy is configured
        client.post(
            "/api/platform/baseline-policy",
            headers=admin_h,
            files={"file": ("corp_baseline.pdf", io.BytesIO(b"%PDF-1.4 Enterprise Baseline Policy"), "application/pdf")},
        )

        # 2. Create supplier and upload policy
        code = f"M2EMPTY-{uuid.uuid4().hex[:4]}"
        r_sup = client.post(
            "/api/suppliers",
            json={
                "name": f"Clean Compliance Supplier {code}",
                "code": code,
                "category": "Logistics",
                "tier": "Tier 1",
                "country": "Germany",
                "contact_email": f"clean_{code}@test.com",
            },
            headers=admin_h,
        )
        assert r_sup.status_code == 201
        sup_id = r_sup.json()["id"]

        r_doc = client.post(
            f"/api/suppliers/{sup_id}/documents",
            headers=admin_h,
            data={"title": "Supplier ESG Policy", "document_type": "Environmental Policy"},
            files={"file": ("esg_policy.pdf", io.BytesIO(b"%PDF-1.4 Perfect Alignment"), "application/pdf")},
        )
        assert r_doc.status_code == 201

        # 3. Mock Member 2 returning clean report (zero risks identified)
        orig_send = httpx.Client.send

        def mock_send_empty_risks(self, request, *args, **kwargs):
            if "api/risk-report" in str(request.url):
                return httpx.Response(
                    200,
                    json={
                        "esg_scores": {
                            "environmental": 92.0,
                            "social": 88.0,
                            "governance": 94.0,
                            "overall": 91.33,
                            "method": "weighted_average",
                        },
                        "risks": [],
                        "risk_count": 0,
                        "high_or_critical_count": 0,
                    },
                    request=request,
                )
            return orig_send(self, request, *args, **kwargs)

        monkeypatch.setattr(httpx.Client, "send", mock_send_empty_risks)

        # 4. Evaluate supplier
        r_eval = client.post(
            f"/api/suppliers/{sup_id}/evaluate?policy_comparison=true",
            headers=admin_h,
        )
        assert r_eval.status_code == 200
        res = r_eval.json()

        # Must be NOT_ASSESSED, NOT fabricated 0.0 or LOW
        assert res["risk_score"] is None
        assert res["risk_level"] == "NOT_ASSESSED"
        assert res["overall_score"] == 91.33
        assert res["evaluation_mode"] == "MEMBER2_REMOTE_API"

        # Verify DB supplier state
        r_detail = client.get(f"/api/suppliers/{sup_id}", headers=admin_h)
        assert r_detail.status_code == 200
        d = r_detail.json()
        assert d["risk_score"] is None
        assert d["risk_level"] == "NOT_ASSESSED"
        assert d["overall_score"] == 91.33
        assert d["last_assessment_date"] is not None

    def test_evaluate_local_zero_findings_yields_not_assessed(self, client, seeded_tokens):
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}

        code = f"LOCZERO-{uuid.uuid4().hex[:4]}"
        r_sup = client.post(
            "/api/suppliers",
            json={
                "name": f"Zero Findings Supplier {code}",
                "code": code,
                "category": "Manufacturing",
                "tier": "Tier 1",
                "country": "Germany",
                "contact_email": f"zero_{code}@test.com",
            },
            headers=admin_h,
        )
        sup_id = r_sup.json()["id"]

        # Run local evaluation (policy_comparison=false)
        r_eval = client.post(
            f"/api/suppliers/{sup_id}/evaluate?policy_comparison=false",
            headers=admin_h,
        )
        assert r_eval.status_code == 200
        res = r_eval.json()

        assert res["risk_score"] is None
        assert res["risk_level"] == "NOT_ASSESSED"
        assert res["evaluation_mode"] == "LOCAL_ISO31000_ADAPTER"


# ─── 10. Hardened ZIP & OpenXML Security Tests ───────────────────────────────

class TestSupplierDocumentSecurityHardening:
    """Verifies that archive upload inspection blocks encryption, zip bombs,
    symlinks, and directory traversal without extracting untrusted files to disk.
    """

    def test_upload_encrypted_zip_rejected(self, client, seeded_tokens):
        import zipfile
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("word/document.xml", b"<w:document/>")
            z.writestr("[Content_Types].xml", b"<Types/>")

        # In ZIP headers, set bit 0 (flag_bits & 0x1) to indicate encryption
        raw_zip = bytearray(buf.getvalue())
        pos = 0
        while True:
            idx = raw_zip.find(b"PK\x01\x02", pos)
            if idx == -1:
                break
            raw_zip[idx + 8] |= 0x1
            pos = idx + 4
        pos = 0
        while True:
            idx = raw_zip.find(b"PK\x03\x04", pos)
            if idx == -1:
                break
            raw_zip[idx + 6] |= 0x1
            pos = idx + 4

        zip_bytes = bytes(raw_zip)

        r_doc = client.post(
            "/api/suppliers/1/documents",
            headers=admin_h,
            data={"title": "Encrypted Docx", "document_type": "Audit Report"},
            files={"file": ("encrypted.docx", io.BytesIO(zip_bytes), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert r_doc.status_code == 400
        assert "Encrypted or password-protected archives are not permitted" in r_doc.text

    def test_upload_zip_path_traversal_entry_rejected(self, client, seeded_tokens):
        import zipfile
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("../../etc/passwd", b"evil")
            z.writestr("word/document.xml", b"<w:document/>")
            z.writestr("[Content_Types].xml", b"<Types/>")
        zip_bytes = buf.getvalue()

        r_doc = client.post(
            "/api/suppliers/1/documents",
            headers=admin_h,
            data={"title": "Traversal Docx", "document_type": "Audit Report"},
            files={"file": ("traversal.docx", io.BytesIO(zip_bytes), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert r_doc.status_code == 400
        assert "Archive contains unsafe path traversal entry" in r_doc.text

    def test_upload_zip_excessive_entries_rejected(self, client, seeded_tokens):
        import zipfile
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for i in range(1005):
                z.writestr(f"file_{i}.xml", b"x")
        zip_bytes = buf.getvalue()

        r_doc = client.post(
            "/api/suppliers/1/documents",
            headers=admin_h,
            data={"title": "Too Many Entries", "document_type": "Audit Report"},
            files={"file": ("toomany.docx", io.BytesIO(zip_bytes), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert r_doc.status_code == 400
        assert "Archive contains too many entries" in r_doc.text

    def test_upload_zip_symlink_entry_rejected(self, client, seeded_tokens):
        import zipfile
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            zinfo = zipfile.ZipInfo("symlink_entry")
            # Set Unix symbolic link mode: 0o120000
            zinfo.external_attr = 0o120000 << 16
            z.writestr(zinfo, b"/etc/shadow")
            z.writestr("word/document.xml", b"<w:document/>")
            z.writestr("[Content_Types].xml", b"<Types/>")
        zip_bytes = buf.getvalue()

        r_doc = client.post(
            "/api/suppliers/1/documents",
            headers=admin_h,
            data={"title": "Symlink Docx", "document_type": "Audit Report"},
            files={"file": ("symlink.docx", io.BytesIO(zip_bytes), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert r_doc.status_code == 400
        assert "Archive contains prohibited symbolic link" in r_doc.text

    def test_upload_valid_docx_and_xlsx_accepted(self, client, seeded_tokens):
        import zipfile
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}

        # Valid DOCX
        docx_buf = io.BytesIO()
        with zipfile.ZipFile(docx_buf, "w") as z:
            z.writestr("word/document.xml", b"<w:document><w:body><w:p><w:r><w:t>ESG Valid</w:t></w:r></w:p></w:body></w:document>")
            z.writestr("[Content_Types].xml", b"<?xml version='1.0'?><Types></Types>")
        docx_bytes = docx_buf.getvalue()

        r_docx = client.post(
            "/api/suppliers/1/documents",
            headers=admin_h,
            data={"title": "Legitimate Word Document", "document_type": "Environmental Policy"},
            files={"file": ("valid.docx", io.BytesIO(docx_bytes), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert r_docx.status_code == 201
        assert r_docx.json()["title"] == "Legitimate Word Document"

        # Valid XLSX
        xlsx_buf = io.BytesIO()
        with zipfile.ZipFile(xlsx_buf, "w") as z:
            z.writestr("xl/workbook.xml", b"<workbook><sheets></sheets></workbook>")
            z.writestr("[Content_Types].xml", b"<?xml version='1.0'?><Types></Types>")
        xlsx_bytes = xlsx_buf.getvalue()

        r_xlsx = client.post(
            "/api/suppliers/1/documents",
            headers=admin_h,
            data={"title": "Legitimate Excel Spreadsheet", "document_type": "Audit Report"},
            files={"file": ("valid.xlsx", io.BytesIO(xlsx_bytes), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert r_xlsx.status_code == 201
        assert r_xlsx.json()["title"] == "Legitimate Excel Spreadsheet"


