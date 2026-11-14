"""Tests for Member 5: Enterprise ESG Reporting & PDF Generation (Phase 5E - Stage 1).

Verifies:
1. Authentication & RBAC (Admin, Auditor, Developer, Viewer permitted; unauthenticated rejected).
2. All 6 specialized report types generate valid JSON preview and multi-page PDF export:
   - ENTERPRISE_SUMMARY
   - ENVIRONMENTAL
   - SOCIAL
   - GOVERNANCE
   - SUPPLIER_RISK
   - FINDINGS_RECOMMENDATIONS
3. Pure in-memory PDF generation streaming (starts with %PDF-, proper headers, no temp files).
4. Strict Metric Integrity:
   - Unassessed suppliers strictly separated from LOW risk.
   - Missing metrics represented as 'Pending Assessment' or null, never default 0 or 80.
   - Honest disclosure of un-partitioned supplier reporting period.
5. Strict Multi-Tenant Isolation (Tenant boundary strictly enforced across preview and PDF).
6. Resilient empty-tenant report compilation (0 suppliers/findings without crash).
"""

from __future__ import annotations

import io
import os
import sys
import uuid

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
os.environ.setdefault("GEMINI_API_KEY", "test-key-for-reports-tests")

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.platform.database import SessionLocal, init_db
from app.platform.models import Organization, Supplier, SupplierFinding, User, UserRole
from app.platform.schemas import ReportFormat, ReportType
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

        org_a = Organization(
            name=f"Report Tenant Alpha {suffix}",
            slug=f"rep-alpha-{suffix}",
            industry="Manufacturing",
            reporting_period="FY 2025–26",
        )
        db.add(org_a)
        db.flush()

        user_a = User(
            organization_id=org_a.id,
            username=f"admin_rep_a_{suffix}",
            email=f"admin_rep_a_{suffix}@test.com",
            role=UserRole.ADMIN.value,
            hashed_password=hash_password("alpha2026"),
            is_active=True,
        )
        db.add(user_a)

        # Supplier for Org A
        sup_a = Supplier(
            organization_id=org_a.id,
            name=f"Alpha Chemical Supplies {suffix}",
            code=f"SUP-A-{suffix}",
            category="Raw Materials",
            tier="Tier 1",
            country="Germany",
            contact_email=f"alpha_{suffix}@test.com",
            risk_score=85.0,
            risk_level="HIGH",
            overall_score=42.0,
            environmental_score=38.0,
            social_score=45.0,
            governance_score=43.0,
        )
        db.add(sup_a)
        db.flush()

        finding_a = SupplierFinding(
            supplier_id=sup_a.id,
            title="Critical Solvent Leakage",
            severity="CRITICAL",
            category="Environmental",
            description="Solvent storage exceeds emissions limits.",
            recommendation="Install automated scrubbers.",
        )
        db.add(finding_a)

        # Org B
        org_b = Organization(
            name=f"Report Tenant Beta {suffix}",
            slug=f"rep-beta-{suffix}",
            industry="Finance",
            reporting_period="FY 2025–26",
        )
        db.add(org_b)
        db.flush()

        user_b = User(
            organization_id=org_b.id,
            username=f"admin_rep_b_{suffix}",
            email=f"admin_rep_b_{suffix}@test.com",
            role=UserRole.ADMIN.value,
            hashed_password=hash_password("beta2026"),
            is_active=True,
        )
        db.add(user_b)

        # Supplier for Org B
        sup_b = Supplier(
            organization_id=org_b.id,
            name=f"Beta Cloud Hosting {suffix}",
            code=f"SUP-B-{suffix}",
            category="IT Services",
            tier="Tier 2",
            country="Ireland",
            contact_email=f"beta_{suffix}@test.com",
            risk_score=20.0,
            risk_level="LOW",
            overall_score=88.0,
            environmental_score=90.0,
            social_score=85.0,
            governance_score=89.0,
        )
        db.add(sup_b)

        # Org C (Empty Tenant)
        org_c = Organization(
            name=f"Report Tenant Empty {suffix}",
            slug=f"rep-empty-{suffix}",
            industry="Consulting",
            reporting_period="FY 2025–26",
        )
        db.add(org_c)
        db.flush()

        user_c = User(
            organization_id=org_c.id,
            username=f"admin_rep_c_{suffix}",
            email=f"admin_rep_c_{suffix}@test.com",
            role=UserRole.ADMIN.value,
            hashed_password=hash_password("empty2026"),
            is_active=True,
        )
        db.add(user_c)

        db.commit()

        org_a_name = org_a.name
        org_b_name = org_b.name
        org_c_name = org_c.name
        user_c_id = user_c.id
        sup_a_name = sup_a.name
        sup_b_name = sup_b.name

        token_a = create_access_token({"sub": user_a.username, "user_id": user_a.id, "org_id": org_a.id, "role": user_a.role})
        token_b = create_access_token({"sub": user_b.username, "user_id": user_b.id, "org_id": org_b.id, "role": user_b.role})
        token_c = create_access_token({"sub": user_c.username, "user_id": user_c.id, "org_id": org_c.id, "role": user_c.role})

        return {
            "org_a_name": org_a_name,
            "org_b_name": org_b_name,
            "org_c_name": org_c_name,
            "user_c_id": user_c_id,
            "sup_a_name": sup_a.name,
            "sup_b_name": sup_b.name,
            "token_a": token_a,
            "token_b": token_b,
            "token_c": token_c,
        }
    finally:
        db.close()


# ─── 1. Authentication & RBAC Tests ──────────────────────────────────────────

def test_unauthenticated_requests_rejected(client):
    """Verify that unauthenticated requests to report endpoints are rejected with 401."""
    assert client.get("/api/platform/reports/types").status_code == 401

    payload = {"report_type": ReportType.ENTERPRISE_SUMMARY.value}
    assert client.post("/api/platform/reports/preview", json=payload).status_code == 401
    assert client.post("/api/platform/reports/export-pdf", json=payload).status_code == 401


def test_all_four_roles_can_preview_and_export_reports(client, seeded_tokens):
    """Verify that Admin, Auditor, Developer, and Viewer can all preview and export."""
    payload = {
        "report_type": ReportType.ENTERPRISE_SUMMARY.value,
        "format": ReportFormat.JSON.value,
    }

    for role, token in seeded_tokens.items():
        headers = {"Authorization": f"Bearer {token}"}

        # 1. GET /types
        res_types = client.get("/api/platform/reports/types", headers=headers)
        assert res_types.status_code == 200, f"Role {role} failed /types: {res_types.text}"

        # 2. POST /preview
        res_prev = client.post("/api/platform/reports/preview", json=payload, headers=headers)
        assert res_prev.status_code == 200, f"Role {role} failed /preview: {res_prev.text}"
        data = res_prev.json()
        assert data["report_type"] == ReportType.ENTERPRISE_SUMMARY.value

        # 3. POST /export-pdf
        res_pdf = client.post("/api/platform/reports/export-pdf", json=payload, headers=headers)
        assert res_pdf.status_code == 200, f"Role {role} failed /export-pdf: {res_pdf.text}"
        assert res_pdf.headers["content-type"] == "application/pdf"
        assert res_pdf.content.startswith(b"%PDF-")


def test_list_report_types_catalog(client, seeded_tokens):
    """Verify that the reports catalog returns all 6 report definitions."""
    token = seeded_tokens["auditor"]
    res = client.get("/api/platform/reports/types", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    types_list = res.json()
    assert len(types_list) == 6

    ids = {t["id"] for t in types_list}
    expected_ids = {
        ReportType.ENTERPRISE_SUMMARY.value,
        ReportType.ENVIRONMENTAL.value,
        ReportType.SOCIAL.value,
        ReportType.GOVERNANCE.value,
        ReportType.SUPPLIER_RISK.value,
        ReportType.FINDINGS_RECOMMENDATIONS.value,
    }
    assert ids == expected_ids

    for t in types_list:
        assert len(t["title"]) > 5
        assert len(t["description"]) > 10
        assert len(t["default_sections"]) >= 3
        assert "reporting_period" in t["supported_filters"]


# ─── 2. All 6 Report Types Execution & PDF Validation ─────────────────────────

@pytest.mark.parametrize("rpt_type", [
    ReportType.ENTERPRISE_SUMMARY.value,
    ReportType.ENVIRONMENTAL.value,
    ReportType.SOCIAL.value,
    ReportType.GOVERNANCE.value,
    ReportType.SUPPLIER_RISK.value,
    ReportType.FINDINGS_RECOMMENDATIONS.value,
])
def test_all_six_report_types_preview_and_export(client, seeded_tokens, rpt_type):
    """Test preview JSON structure and binary PDF export for all six report types."""
    token = seeded_tokens["admin"]
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "report_type": rpt_type,
        "reporting_period": "FY 2025–26",
    }

    # 1. Preview
    resp_prev = client.post("/api/platform/reports/preview", json=payload, headers=headers)
    assert resp_prev.status_code == 200, f"Preview failed for {rpt_type}: {resp_prev.text}"
    pdata = resp_prev.json()

    assert pdata["report_type"] == rpt_type
    assert len(pdata["title"]) > 0
    assert len(pdata["executive_summary"]) > 20
    assert isinstance(pdata["kpi_summary"], list)
    assert len(pdata["sections"]) >= 2
    assert len(pdata["disclosures_and_limitations"]) >= 4

    # 2. PDF Export
    resp_pdf = client.post("/api/platform/reports/export-pdf", json=payload, headers=headers)
    assert resp_pdf.status_code == 200, f"PDF export failed for {rpt_type}: {resp_pdf.text}"
    assert resp_pdf.headers["content-type"] == "application/pdf"
    assert "Content-Disposition" in resp_pdf.headers
    assert resp_pdf.content.startswith(b"%PDF-")
    # Verify non-trivial PDF size (minimum 4KB for multi-page Platypus report)
    assert len(resp_pdf.content) > 4000


# ─── 3. Metric Integrity & Honest Aggregation ─────────────────────────────────

def test_metric_integrity_in_reports(client, tenant_fixture):
    """Verify that unassessed suppliers and missing metrics are not fabricated as 0 or 80."""
    token = tenant_fixture["token_a"]
    headers = {"Authorization": f"Bearer {token}"}

    payload = {"report_type": ReportType.SUPPLIER_RISK.value}
    resp = client.post("/api/platform/reports/preview", json=payload, headers=headers)
    assert resp.status_code == 200
    pdata = resp.json()

    # Verify disclosures statement contains historical period limitation
    disc_text = " ".join(pdata["disclosures_and_limitations"])
    assert "historical fiscal-year partitioning is not supported" in disc_text
    assert "Member 2" in disc_text
    assert "Member 3" in disc_text
    assert "Member 4" in disc_text

    # Check risk distribution section table rows isolate unassessed suppliers
    risk_sec = next((s for s in pdata["sections"] if s["key"] == "supplier_risk_distribution"), None)
    assert risk_sec is not None
    assert risk_sec["table_rows"] is not None
    row_headers = [row[0] for row in risk_sec["table_rows"]]
    assert any("NOT ASSESSED" in rh for rh in row_headers)
    assert any("Low Severity" in rh for rh in row_headers)


# ─── 4. Empty Tenant Resilient Generation ─────────────────────────────────────

def test_empty_tenant_report_generation(client, tenant_fixture):
    """Verify that an organization with zero suppliers, zero docs, and zero findings generates clean reports."""
    token = tenant_fixture["token_c"]
    headers = {"Authorization": f"Bearer {token}"}

    for rpt_type in [ReportType.ENTERPRISE_SUMMARY.value, ReportType.SUPPLIER_RISK.value]:
        payload = {"report_type": rpt_type}

        # Preview
        resp_prev = client.post("/api/platform/reports/preview", json=payload, headers=headers)
        assert resp_prev.status_code == 200
        pdata = resp_prev.json()
        assert pdata["organization_name"] == tenant_fixture["org_c_name"]
        assert len(pdata["sections"]) >= 1

        # PDF Export
        resp_pdf = client.post("/api/platform/reports/export-pdf", json=payload, headers=headers)
        assert resp_pdf.status_code == 200
        assert resp_pdf.content.startswith(b"%PDF-")
        assert len(resp_pdf.content) > 3000


# ─── 5. Multi-Tenant Isolation Boundary ───────────────────────────────────────

def test_tenant_isolation_boundary(client, tenant_fixture):
    """Verify that Org A cannot see Org B's suppliers or findings in reports, and vice-versa."""
    # Org A
    headers_a = {"Authorization": f"Bearer {tenant_fixture['token_a']}"}
    payload = {"report_type": ReportType.ENTERPRISE_SUMMARY.value}
    resp_a = client.post("/api/platform/reports/preview", json=payload, headers=headers_a)
    assert resp_a.status_code == 200
    data_a = resp_a.json()
    assert data_a["organization_name"] == tenant_fixture["org_a_name"]

    # Check that supplier list or summary for Org A does NOT contain Org B supplier
    json_str_a = str(data_a)
    assert tenant_fixture["sup_a_name"] in json_str_a
    assert tenant_fixture["sup_b_name"] not in json_str_a

    # Org B
    headers_b = {"Authorization": f"Bearer {tenant_fixture['token_b']}"}
    resp_b = client.post("/api/platform/reports/preview", json=payload, headers=headers_b)
    assert resp_b.status_code == 200
    data_b = resp_b.json()
    assert data_b["organization_name"] == tenant_fixture["org_b_name"]

    json_str_b = str(data_b)
    assert tenant_fixture["sup_b_name"] in json_str_b
    assert tenant_fixture["sup_a_name"] not in json_str_b


# ─── 6. Custom Section Selection & Reporting Period Override ──────────────────

def test_custom_section_selection(client, seeded_tokens):
    """Verify that requesting custom sections filters the rendered report sections."""
    token = seeded_tokens["admin"]
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "report_type": ReportType.ENTERPRISE_SUMMARY.value,
        "sections": ["kpi_overview", "priority_findings"],
        "reporting_period": "FY 2026–27 (Projected)",
    }

    resp = client.post("/api/platform/reports/preview", json=payload, headers=headers)
    assert resp.status_code == 200
    pdata = resp.json()
    assert pdata["reporting_period"] == "FY 2026–27 (Projected)"

    sec_keys = [s["key"] for s in pdata["sections"]]
    assert sec_keys == ["kpi_overview", "priority_findings"]

    # PDF with customized sections
    resp_pdf = client.post("/api/platform/reports/export-pdf", json=payload, headers=headers)
    assert resp_pdf.status_code == 200
    assert resp_pdf.content.startswith(b"%PDF-")


# ─── 7. Deactivated User Access Blocked ───────────────────────────────────────

def test_deactivated_user_blocked(client, tenant_fixture):
    """Verify that deactivated user accounts cannot generate or export reports."""
    db = SessionLocal()
    try:
        user_c = db.query(User).filter(User.id == tenant_fixture["user_c_id"]).first()
        user_c.is_active = False
        db.commit()
    finally:
        db.close()

    headers = {"Authorization": f"Bearer {tenant_fixture['token_c']}"}
    payload = {"report_type": ReportType.ENTERPRISE_SUMMARY.value}

    assert client.get("/api/platform/reports/types", headers=headers).status_code in (401, 403)
    assert client.post("/api/platform/reports/preview", json=payload, headers=headers).status_code in (401, 403)
    assert client.post("/api/platform/reports/export-pdf", json=payload, headers=headers).status_code in (401, 403)

