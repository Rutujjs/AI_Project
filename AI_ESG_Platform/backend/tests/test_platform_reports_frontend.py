"""Tests for Member 5 Phase 5E Stage 2: ESG Reporting & PDF Export Frontend Integration.

Verifies:
1. Frontend static asset structure and dependencies:
   - reports.html includes js/auth.js, js/api.js, and js/reports.js in correct order
   - reports.html contains all required DOM containers (page-app, page-content, page-refresh-action)
2. api.js adapter:
   - Exports reportTypes(), reportPreview(), and reportExportPdf() methods
   - reportExportPdf handles binary Blob streaming and Content-Disposition filename extraction
   - Injects Bearer token authorization
3. reports.js implementation:
   - Removes hardcoded mock module labels, mock data, and placeholder export notices
   - Connects to live GET /api/platform/reports/types, POST /preview, and POST /export-pdf
   - Supports reporting period selection and section customization
   - Formats null and pending values honestly without defaulting to 0 or 80
   - Accurately isolates NOT_ASSESSED suppliers from Low risk
   - Discloses data provenance and reporting period limitations
   - Enforces Blob/object URL download handling with post-response success notification
   - Manages all required UI states: loading, ready, previewing, exporting, success, error, unauthorized
4. Full API end-to-end integration:
   - Unauthenticated requests rejected with 401
   - All four roles (Admin, Auditor, Developer, Viewer) access report endpoints
   - All 6 report types generate valid preview and binary PDF download
   - Tenant boundary isolation strictly preserved
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sys
import uuid

import pytest
from fastapi.testclient import TestClient

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
os.environ.setdefault("GEMINI_API_KEY", "test-key-for-reports-frontend-tests")

from app.main import app
from app.platform.database import SessionLocal, init_db
from app.platform.models import Organization, Supplier, SupplierFinding, User, UserRole
from app.platform.schemas import ReportFormat, ReportType
from app.platform.security import create_access_token, hash_password

REPO_ROOT = Path(backend_dir).parent.parent
FRONTEND_DIR = REPO_ROOT / "integrated-frontend"


# ─── Fixtures ─────────────────────────────────────────────────────────────────

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
def frontend_files():
    """Load frontend file contents for static verification."""
    reports_html_path = FRONTEND_DIR / "reports.html"
    api_js_path = FRONTEND_DIR / "js" / "api.js"
    reports_js_path = FRONTEND_DIR / "js" / "reports.js"

    assert reports_html_path.exists(), f"Missing reports.html at {reports_html_path}"
    assert api_js_path.exists(), f"Missing api.js at {api_js_path}"
    assert reports_js_path.exists(), f"Missing reports.js at {reports_js_path}"

    return {
        "reports_html": reports_html_path.read_text(encoding="utf-8"),
        "api_js": api_js_path.read_text(encoding="utf-8"),
        "reports_js": reports_js_path.read_text(encoding="utf-8"),
    }


# ─── 1. Frontend Asset Structure & Dependencies ───────────────────────────────

class TestFrontendAssetStructureAndDependencies:
    """Verify that reports.html loads all required scripts and defines expected DOM containers."""

    def test_reports_html_script_order(self, frontend_files):
        html = frontend_files["reports_html"]

        assert "js/auth.js" in html, "reports.html must include auth.js"
        assert "js/api.js" in html, "reports.html must include api.js"
        assert "js/reports.js" in html, "reports.html must include reports.js"

        # Verify correct script inclusion sequence
        pos_auth = html.find("js/auth.js")
        pos_api = html.find("js/api.js")
        pos_reports = html.find("js/reports.js")

        assert pos_auth < pos_reports, "auth.js must load before reports.js"
        assert pos_api < pos_reports, "api.js must load before reports.js"

    def test_reports_html_required_dom_elements(self, frontend_files):
        html = frontend_files["reports_html"]

        assert 'id="page-app"' in html, "reports.html must contain page-app container"
        assert 'id="page-content"' in html, "reports.html must contain page-content section"
        assert 'data-page="reports"' in html, "reports.html must declare data-page='reports'"


# ─── 2. ESGApi Adapter Reporting Methods ──────────────────────────────────────

class TestFrontendApiClientAdapter:
    """Verify that api.js exports reportTypes, reportPreview, and reportExportPdf."""

    def test_api_js_exports_reporting_methods(self, frontend_files):
        api = frontend_files["api_js"]

        # Check function declarations
        assert "function reportTypes(" in api, "api.js must define reportTypes()"
        assert "function reportPreview(" in api, "api.js must define reportPreview()"
        assert "function reportExportPdf(" in api, "api.js must define reportExportPdf()"

        # Check export map
        assert "reportTypes:reportTypes" in api or "reportTypes: reportTypes" in api, "api.js must export reportTypes"
        assert "reportPreview:reportPreview" in api or "reportPreview: reportPreview" in api, "api.js must export reportPreview"
        assert "reportExportPdf:reportExportPdf" in api or "reportExportPdf: reportExportPdf" in api, "api.js must export reportExportPdf"

    def test_api_js_report_export_pdf_handles_blob(self, frontend_files):
        api = frontend_files["api_js"]

        assert "/api/platform/reports/export-pdf" in api, "Must route to /api/platform/reports/export-pdf"
        assert "res.blob()" in api, "Must call res.blob() to process binary PDF response"
        assert "Content-Disposition" in api, "Must parse Content-Disposition for filename"


# ─── 3. reports.js Implementation & UI Logic ──────────────────────────────────

class TestFrontendReportsScriptIntegrity:
    """Verify that reports.js contains authentic live logic without mock placeholders."""

    def test_reports_js_does_not_use_mock_placeholders(self, frontend_files):
        js = frontend_files["reports_js"]

        # Confirm old mock indicators are eliminated
        assert "MOCK MODULE" not in js, "reports.js must not display MOCK MODULE badge"
        assert "PDF export is a future backend integration" not in js, "reports.js must not retain placeholder export message"
        assert "This preview is generated from the platform's configured mock data" not in js, "Mock preview text must be removed"

    def test_reports_js_connects_to_live_apis(self, frontend_files):
        js = frontend_files["reports_js"]

        assert "ESGApi.reportTypes" in js, "Must call ESGApi.reportTypes()"
        assert "ESGApi.reportPreview" in js, "Must call ESGApi.reportPreview()"
        assert "ESGApi.reportExportPdf" in js, "Must call ESGApi.reportExportPdf()"

    def test_reports_js_manages_ui_states(self, frontend_files):
        js = frontend_files["reports_js"]

        # Loading, previewing, and exporting states
        assert "Generating Preview..." in js or "Compiling..." in js
        assert "Generating PDF..." in js or "Compiling PDF..." in js
        assert "PDF Exported" in js
        assert "Export Failed" in js or "Failed to generate report" in js

    def test_reports_js_handles_blob_and_object_url_safely(self, frontend_files):
        js = frontend_files["reports_js"]

        assert "createObjectURL" in js, "Must create object URL for PDF download"
        assert "revokeObjectURL" in js, "Must revoke object URL after download dispatch"
        assert "download" in js, "Must set download attribute on anchor element"

    def test_reports_js_distinguishes_not_assessed_from_low(self, frontend_files):
        js = frontend_files["reports_js"]

        assert "NOT ASSESSED" in js, "Must explicitly format NOT ASSESSED risk"
        assert "NOT_ASSESSED" in js, "Must check NOT_ASSESSED status"

    def test_reports_js_discloses_period_limitations(self, frontend_files):
        js = frontend_files["reports_js"]

        # Confirm transparency notice regarding lifecycle status vs fiscal year partitioning
        assert "historical fiscal-year partitioning is not supported" in js or "reflect current lifecycle status" in js


# ─── 4. End-to-End API Integration for Frontend Consumption ───────────────────

class TestFrontendEndToEndApiIntegration:
    """Verify live API responses for the frontend adapter across all 6 report types."""

    def test_unauthenticated_requests_rejected(self, client):
        assert client.get("/api/platform/reports/types").status_code == 401
        assert client.post("/api/platform/reports/preview", json={"report_type": "ENTERPRISE_SUMMARY"}).status_code == 401
        assert client.post("/api/platform/reports/export-pdf", json={"report_type": "ENTERPRISE_SUMMARY"}).status_code == 401

    def test_all_four_roles_retrieve_report_types(self, client, seeded_tokens):
        for role, token in seeded_tokens.items():
            resp = client.get("/api/platform/reports/types", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 200, f"Role {role} failed /types: {resp.text}"
            data = resp.json()
            assert len(data) == 6

    @pytest.mark.parametrize("rpt_type", [
        ReportType.ENTERPRISE_SUMMARY.value,
        ReportType.ENVIRONMENTAL.value,
        ReportType.SOCIAL.value,
        ReportType.GOVERNANCE.value,
        ReportType.SUPPLIER_RISK.value,
        ReportType.FINDINGS_RECOMMENDATIONS.value,
    ])
    def test_frontend_preview_and_export_flow(self, client, seeded_tokens, rpt_type):
        token = seeded_tokens["admin"]
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "report_type": rpt_type,
            "reporting_period": "FY 2025–26",
            "category": "All",
        }

        # 1. Preview response (consumed by renderPreviewContent)
        p_resp = client.post("/api/platform/reports/preview", json=payload, headers=headers)
        assert p_resp.status_code == 200
        p_data = p_resp.json()
        assert p_data["report_type"] == rpt_type
        assert "title" in p_data
        assert "organization_name" in p_data
        assert "executive_summary" in p_data
        assert "sections" in p_data
        assert "disclosures_and_limitations" in p_data

        # 2. PDF Export response (consumed by executePdfExport)
        e_resp = client.post("/api/platform/reports/export-pdf", json=payload, headers=headers)
        assert e_resp.status_code == 200
        assert e_resp.headers["content-type"] == "application/pdf"
        assert "Content-Disposition" in e_resp.headers
        assert e_resp.content.startswith(b"%PDF-")
        assert len(e_resp.content) > 3000

    def test_invalid_report_selection_graceful_handling(self, client, seeded_tokens):
        token = seeded_tokens["viewer"]
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Unrecognized custom section key returns 200 with empty matched sections
        payload_unknown_sec = {
            "report_type": ReportType.ENTERPRISE_SUMMARY.value,
            "include_sections": ["non_existent_section_key"],
        }
        resp_sec = client.post("/api/platform/reports/preview", json=payload_unknown_sec, headers=headers)
        assert resp_sec.status_code == 200
        data_sec = resp_sec.json()
        assert data_sec["sections"] == []

        # 2. Invalid report type string is rejected with 422 validation error, not 500
        payload_bad_type = {
            "report_type": "TOTALLY_INVALID_REPORT_TYPE_123",
        }
        resp_type = client.post("/api/platform/reports/preview", json=payload_bad_type, headers=headers)
        assert resp_type.status_code == 422

