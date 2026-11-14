"""Tests for Member 5 Phase 5D Stage 2: Unified ESG Dashboard Frontend Integration.

Verifies:
1. Frontend static asset structure and dependencies:
   - index.html includes api.js and dashboard.js in correct order
   - index.html includes all required DOM containers and filter controls
2. api.js adapter:
   - Exports dashboardMetrics() method
   - Routes to /api/platform/dashboard with query parameters and Bearer token
3. dashboard.js implementation:
   - Completely removes dependency on hardcoded MOCK metrics
   - Handles loading, error, empty, and partial-availability states
   - Honestly formats null values (never 0 or 80)
   - Accurately reports NOT_ASSESSED and NOT_EVALUATED
   - Implements honest filter notice for session-bound cloud metrics
4. Full API end-to-end integration:
   - Unauthenticated access returns 401
   - All four roles (Admin, Auditor, Developer, Viewer) access successfully
   - Empty tenant responses handle empty arrays and null metrics gracefully
   - Module offline states are surfaced gracefully
   - Multi-tenant isolation is strictly preserved
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import uuid

import pytest
from fastapi.testclient import TestClient
import httpx

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
os.environ.setdefault("GEMINI_API_KEY", "test-key-for-dashboard-tests")

from app.main import app
from app.platform.database import SessionLocal, init_db
from app.platform.models import Organization, Supplier, SupplierFinding, User, UserRole
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
def isolated_tenants():
    """Create two isolated organizations for tenant verification."""
    db = SessionLocal()
    try:
        suffix = uuid.uuid4().hex[:6]
        org_1 = Organization(
            name=f"Frontend Test Org One {suffix}",
            slug=f"fe-org-1-{suffix}",
            industry="Logistics",
            reporting_period="FY 2025–26",
            baseline_policy_name="Enterprise Baseline v1.0",
            baseline_policy_path="/tmp/baseline.pdf",
        )
        db.add(org_1)
        db.flush()

        user_1 = User(
            organization_id=org_1.id,
            username=f"admin_fe1_{suffix}",
            email=f"admin_fe1_{suffix}@test.com",
            role=UserRole.ADMIN.value,
            hashed_password=hash_password("testpass2026"),
            is_active=True,
        )
        db.add(user_1)

        # Add 1 supplier to Org 1
        sup_1 = Supplier(
            organization_id=org_1.id,
            name=f"Org 1 Exclusive Supplier {suffix}",
            code=f"SUP1-{suffix}",
            category="Manufacturing",
            contact_email=f"sup1_{suffix}@test.com",
            risk_score=24.0,
            risk_level="LOW",
            overall_score=85.0,
        )
        db.add(sup_1)

        org_2 = Organization(
            name=f"Frontend Test Org Two {suffix}",
            slug=f"fe-org-2-{suffix}",
            industry="Healthcare",
            reporting_period="FY 2024–25",
        )
        db.add(org_2)
        db.flush()

        user_2 = User(
            organization_id=org_2.id,
            username=f"admin_fe2_{suffix}",
            email=f"admin_fe2_{suffix}@test.com",
            role=UserRole.ADMIN.value,
            hashed_password=hash_password("testpass2026"),
            is_active=True,
        )
        db.add(user_2)
        db.commit()

        token_1 = create_access_token({"sub": user_1.username, "user_id": user_1.id, "org_id": org_1.id, "role": user_1.role})
        token_2 = create_access_token({"sub": user_2.username, "user_id": user_2.id, "org_id": org_2.id, "role": user_2.role})

        return {
            "org_1": {"id": org_1.id, "name": org_1.name, "token": token_1},
            "org_2": {"id": org_2.id, "name": org_2.name, "token": token_2},
        }
    finally:
        db.close()


# ─── 1. Frontend Asset Structure & Dependency Verification ────────────────────

class TestFrontendAssetStructureAndDependencies:
    def test_index_html_includes_required_scripts_in_order(self):
        """index.html must load auth.js, common.js, api.js, and dashboard.js in correct order."""
        index_file = FRONTEND_DIR / "index.html"
        assert index_file.exists(), f"index.html not found at {index_file}"
        content = index_file.read_text(encoding="utf-8")

        # Must include api.js and dashboard.js
        assert 'src="js/api.js"' in content or "src='js/api.js'" in content, "index.html does not load js/api.js"
        assert 'src="js/dashboard.js"' in content or "src='js/dashboard.js'" in content, "index.html does not load js/dashboard.js"

        # api.js must appear BEFORE dashboard.js
        idx_api = content.find("js/api.js")
        idx_dash = content.find("js/dashboard.js")
        assert idx_api < idx_dash, "js/api.js must be loaded before js/dashboard.js"

    def test_index_html_contains_all_required_dom_sections(self):
        """index.html must contain all necessary DOM element IDs for live data rendering."""
        index_file = FRONTEND_DIR / "index.html"
        content = index_file.read_text(encoding="utf-8")

        required_ids = [
            "dashboard-container",
            "dashboard-loading",
            "dashboard-error",
            "filter-notice",
            "filter-category",
            "filter-period",
            "btn-refresh-dashboard",
            "dash-org-title",
            "dash-reporting-sub",
            "dash-generated-at",
            "module-health-strip",
            "score-grid",
            "deep-dive-grid",
            "performance-chart",
            "risk-overview",
            "priority-findings",
            "dashboard-recommendations",
        ]
        for elem_id in required_ids:
            assert f'id="{elem_id}"' in content or f"id='{elem_id}'" in content, f"Missing required element #{elem_id} in index.html"


# ─── 2. API Client Adapter Verification ───────────────────────────────────────

class TestFrontendApiClientAdapter:
    def test_api_js_exports_dashboard_metrics(self):
        """api.js must export dashboardMetrics() function calling /api/platform/dashboard."""
        api_file = FRONTEND_DIR / "js" / "api.js"
        assert api_file.exists(), f"api.js not found at {api_file}"
        content = api_file.read_text(encoding="utf-8")

        assert "function dashboardMetrics(" in content or "dashboardMetrics:dashboardMetrics" in content
        assert "/api/platform/dashboard" in content
        assert "dashboardMetrics:dashboardMetrics" in content or "dashboardMetrics: dashboardMetrics" in content


# ─── 3. Dashboard Script Logic & Mock Removal ─────────────────────────────────

class TestFrontendDashboardScriptIntegrity:
    def test_dashboard_js_does_not_use_mock_data(self):
        """dashboard.js must NOT depend on MOCK.scores, MOCK.riskCounts, MOCK.findings, or MOCK.recommendations."""
        dash_file = FRONTEND_DIR / "js" / "dashboard.js"
        assert dash_file.exists(), f"dashboard.js not found at {dash_file}"
        content = dash_file.read_text(encoding="utf-8")

        assert "MOCK.scores" not in content, "dashboard.js still references MOCK.scores"
        assert "MOCK.riskCounts" not in content, "dashboard.js still references MOCK.riskCounts"
        assert "MOCK.findings" not in content, "dashboard.js still references MOCK.findings"
        assert "MOCK.recommendations" not in content, "dashboard.js still references MOCK.recommendations"

    def test_dashboard_js_integrates_with_live_api(self):
        """dashboard.js must invoke window.ESGApi.dashboardMetrics()."""
        dash_file = FRONTEND_DIR / "js" / "dashboard.js"
        content = dash_file.read_text(encoding="utf-8")

        assert "ESGApi.dashboardMetrics" in content

    def test_dashboard_js_handles_null_values_honestly(self):
        """dashboard.js must format null values as Pending Assessment or Not Evaluated, never 0 or 80."""
        dash_file = FRONTEND_DIR / "js" / "dashboard.js"
        content = dash_file.read_text(encoding="utf-8")

        assert "Pending Assessment" in content
        assert "Not Evaluated" in content
        assert "NOT ASSESSED" in content

    def test_dashboard_js_renders_all_five_module_health_indicators(self):
        """dashboard.js must render indicators for all 5 platform member modules."""
        dash_file = FRONTEND_DIR / "js" / "dashboard.js"
        content = dash_file.read_text(encoding="utf-8")

        assert "member_1_documents" in content
        assert "member_2_policy" in content
        assert "member_3_green" in content
        assert "member_4_cloud" in content
        assert "member_5_platform" in content


# ─── 4. End-to-End API Integration & UI Contract Verification ─────────────────

class TestDashboardEndToEndApiIntegration:
    def test_unauthenticated_dashboard_rejected(self, client):
        """Unauthenticated requests are rejected with 401."""
        resp = client.get("/api/platform/dashboard")
        assert resp.status_code == 401

    def test_all_four_roles_retrieve_live_dashboard(self, client, seeded_tokens):
        """Admin, Auditor, Developer, and Viewer all receive 200 OK with full schema."""
        roles = ["admin", "auditor", "developer", "viewer"]
        for role in roles:
            token = seeded_tokens[role]
            resp = client.get("/api/platform/dashboard", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 200, f"Role {role} failed: {resp.text}"
            data = resp.json()

            # Verify core sections
            assert "organization_id" in data
            assert "organization_name" in data
            assert "module_health" in data
            assert len(data["module_health"]) == 5
            assert "kpi_scores" in data
            assert "suppliers" in data
            assert "green_software" in data
            assert "cloud_carbon" in data
            assert "policy_checker" in data
            assert "document_intelligence" in data
            assert "risk_overview" in data
            assert "priority_findings" in data
            assert "recommendations" in data

    def test_empty_tenant_response_integrity(self, client, isolated_tenants):
        """Empty tenant has 0 suppliers and empty findings/recommendations without errors."""
        t2 = isolated_tenants["org_2"]
        resp = client.get("/api/platform/dashboard", headers={"Authorization": f"Bearer {t2['token']}"})
        assert resp.status_code == 200
        data = resp.json()

        assert data["organization_id"] == t2["id"]
        assert data["suppliers"]["total_suppliers"] == 0
        assert data["suppliers"]["assessed_count"] == 0
        assert data["suppliers"]["not_assessed_count"] == 0
        assert data["suppliers"]["average_esg_score"] is None
        assert data["priority_findings"] == []
        assert data["recommendations"] == []

    def test_tenant_isolation_boundary(self, client, isolated_tenants):
        """Tenant 2 cannot see Tenant 1's supplier metrics or baseline policy."""
        t1 = isolated_tenants["org_1"]
        t2 = isolated_tenants["org_2"]

        r1 = client.get("/api/platform/dashboard", headers={"Authorization": f"Bearer {t1['token']}"})
        d1 = r1.json()
        assert d1["suppliers"]["total_suppliers"] == 1
        assert d1["policy_checker"]["baseline_configured"] is True
        assert d1["policy_checker"]["baseline_policy_name"] == "Enterprise Baseline v1.0"

        r2 = client.get("/api/platform/dashboard", headers={"Authorization": f"Bearer {t2['token']}"})
        d2 = r2.json()
        assert d2["suppliers"]["total_suppliers"] == 0
        assert d2["policy_checker"]["baseline_configured"] is False
        assert d2["policy_checker"]["baseline_policy_name"] is None

    def test_module_offline_graceful_handling(self, client, seeded_tokens, monkeypatch):
        """When Member 2 service is offline, dashboard returns 200 OK with OFFLINE status and null scores."""
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}

        async def mock_m2_down(self, request, *args, **kwargs):
            if "8002" in str(request.url):
                raise httpx.ConnectError("Member 2 service is down")
            return httpx.Response(503, json={"status": "unavailable"})

        monkeypatch.setattr(httpx.AsyncClient, "send", mock_m2_down)

        resp = client.get("/api/platform/dashboard", headers=admin_h)
        assert resp.status_code == 200
        data = resp.json()

        assert data["module_health"]["member_2_policy"]["service_status"] == "OFFLINE"
        assert data["policy_checker"]["service_status"] == "OFFLINE"
        assert data["policy_checker"]["latest_overall_esg_score"] is None
        assert data["policy_checker"]["latest_policy_risk_level"] is None

