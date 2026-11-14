"""Tests for Member 5: Unified Enterprise ESG Dashboard Aggregation (Phase 5D).

Verifies:
1. Authentication & RBAC (All 4 roles permitted, unauthenticated rejected).
2. Strict Multi-Tenant Isolation (Tenant boundary strictly enforced).
3. Metric Integrity & Honest Aggregation:
   - Unassessed suppliers strictly separated from LOW risk.
   - Missing metrics represented as null/PENDING, never fabricated as zero.
4. Module Resilience & Graceful Degraded States (Member 2 offline resilience).
5. Category & Reporting Period Filter Transparency.
"""

from __future__ import annotations

from datetime import datetime, timezone
import io
import os
import sys
import uuid

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
os.environ.setdefault("GEMINI_API_KEY", "test-key-for-dashboard-tests")

import pytest
from fastapi.testclient import TestClient
import httpx

from app.main import app
from app.platform.database import SessionLocal, init_db
from app.platform.models import Organization, Supplier, SupplierFinding, User, UserRole
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
            name=f"Dashboard Tenant Alpha {suffix}",
            slug=f"dash-alpha-{suffix}",
            industry="Technology",
            reporting_period="FY 2025–26",
        )
        db.add(org_a)
        db.flush()

        user_a = User(
            organization_id=org_a.id,
            username=f"admin_dash_a_{suffix}",
            email=f"admin_dash_a_{suffix}@test.com",
            role=UserRole.ADMIN.value,
            hashed_password=hash_password("alpha2026"),
            is_active=True,
        )
        db.add(user_a)

        org_b = Organization(
            name=f"Dashboard Tenant Beta {suffix}",
            slug=f"dash-beta-{suffix}",
            industry="Healthcare",
            reporting_period="FY 2024–25",
        )
        db.add(org_b)
        db.flush()

        user_b = User(
            organization_id=org_b.id,
            username=f"admin_dash_b_{suffix}",
            email=f"admin_dash_b_{suffix}@test.com",
            role=UserRole.ADMIN.value,
            hashed_password=hash_password("beta2026"),
            is_active=True,
        )
        db.add(user_b)
        db.commit()

        token_a = create_access_token({"sub": user_a.username, "user_id": user_a.id, "org_id": org_a.id, "role": user_a.role})
        token_b = create_access_token({"sub": user_b.username, "user_id": user_b.id, "org_id": org_b.id, "role": user_b.role})

        return {
            "org_a": {"id": org_a.id, "name": org_a.name, "token": token_a},
            "org_b": {"id": org_b.id, "name": org_b.name, "token": token_b},
        }
    finally:
        db.close()


# ─── 1. Authentication & RBAC Tests ──────────────────────────────────────────

class TestDashboardAuthenticationAndRBAC:
    def test_unauthenticated_request_rejected(self, client):
        resp = client.get("/api/platform/dashboard")
        assert resp.status_code == 401

    def test_all_four_roles_can_access_dashboard(self, client, seeded_tokens):
        roles = ["admin", "auditor", "developer", "viewer"]
        for role in roles:
            token = seeded_tokens[role]
            headers = {"Authorization": f"Bearer {token}"}
            resp = client.get("/api/platform/dashboard", headers=headers)
            assert resp.status_code == 200, f"Role {role} failed to access dashboard: {resp.text}"
            data = resp.json()
            assert "organization_id" in data
            assert "kpi_scores" in data
            assert "suppliers" in data
            assert "module_health" in data


# ─── 2. Multi-Tenant Isolation Tests ─────────────────────────────────────────

class TestDashboardTenantIsolation:
    def test_cross_tenant_dashboard_isolation(self, client, tenant_fixture):
        t_a = tenant_fixture["org_a"]
        t_b = tenant_fixture["org_b"]

        h_a = {"Authorization": f"Bearer {t_a['token']}"}
        h_b = {"Authorization": f"Bearer {t_b['token']}"}

        # Onboard a supplier exclusively into Tenant A
        code_a = f"TENA-{uuid.uuid4().hex[:4]}"
        r_create = client.post(
            "/api/suppliers",
            json={
                "name": f"Tenant A Dashboard Exclusive {code_a}",
                "code": code_a,
                "category": "Electronics",
                "tier": "Tier 1",
                "country": "Germany",
                "contact_email": f"tena_{code_a}@test.com",
            },
            headers=h_a,
        )
        assert r_create.status_code == 201
        sup_a_id = r_create.json()["id"]

        # Fetch dashboard for Tenant A
        r_dash_a = client.get("/api/platform/dashboard", headers=h_a)
        assert r_dash_a.status_code == 200
        dash_a = r_dash_a.json()
        assert dash_a["organization_id"] == t_a["id"]
        assert dash_a["organization_name"] == t_a["name"]
        assert dash_a["suppliers"]["total_suppliers"] >= 1

        # Fetch dashboard for Tenant B
        r_dash_b = client.get("/api/platform/dashboard", headers=h_b)
        assert r_dash_b.status_code == 200
        dash_b = r_dash_b.json()
        assert dash_b["organization_id"] == t_b["id"]
        assert dash_b["organization_name"] == t_b["name"]
        assert dash_b["suppliers"]["total_suppliers"] == 0  # Tenant B has 0 suppliers


# ─── 3. Metric Integrity & Honest Representation ─────────────────────────────

class TestDashboardMetricIntegrity:
    def test_supplier_metrics_strictly_separate_not_assessed_from_low(self, client, seeded_tokens):
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}

        # Onboard a new unassessed supplier
        code = f"UNASS-{uuid.uuid4().hex[:4]}"
        r_sup = client.post(
            "/api/suppliers",
            json={
                "name": f"Unassessed Dashboard Supplier {code}",
                "code": code,
                "category": "Manufacturing",
                "tier": "Tier 2",
                "country": "Germany",
                "contact_email": f"unass_{code}@test.com",
            },
            headers=admin_h,
        )
        assert r_sup.status_code == 201

        # Query dashboard
        r_dash = client.get("/api/platform/dashboard", headers=admin_h)
        assert r_dash.status_code == 200
        d = r_dash.json()

        # Unassessed count must be tracked strictly separately from low risk
        assert d["suppliers"]["not_assessed_count"] >= 1
        assert d["risk_overview"]["NOT_ASSESSED"] >= 1
        # Assessed count must be distinct
        assert d["suppliers"]["assessed_count"] >= 5

    def test_missing_metrics_represented_as_null_not_zero(self, client, seeded_tokens):
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}
        r_dash = client.get("/api/platform/dashboard", headers=admin_h)
        assert r_dash.status_code == 200
        d = r_dash.json()

        # Cloud carbon without active upload must have null emissions, not fabricated 0.0
        cc = d["cloud_carbon"]
        if not cc["has_active_session"]:
            assert cc["total_estimated_kg_co2e"] is None
            assert cc["data_status"] in ("NO_ACTIVE_SESSION", "UNAVAILABLE")

        # Policy checker without evaluated policy must have null scores
        pc = d["policy_checker"]
        if pc["service_status"] != "ONLINE" or pc["latest_overall_esg_score"] is None:
            assert pc["latest_overall_esg_score"] is None

    def test_cloud_carbon_online_without_session_reports_no_active_session(self, client, seeded_tokens, monkeypatch):
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}

        async def mock_online_health(self, request, *args, **kwargs):
            if "cloud-carbon/health" in str(request.url):
                return httpx.Response(200, json={"status": "healthy"})
            return httpx.Response(503, json={"status": "unavailable"})

        monkeypatch.setattr(httpx.AsyncClient, "send", mock_online_health)

        r_dash = client.get("/api/platform/dashboard", headers=admin_h)
        assert r_dash.status_code == 200
        d = r_dash.json()

        cc = d["cloud_carbon"]
        assert cc["service_status"] == "ONLINE"
        assert cc["has_active_session"] is False
        assert cc["total_estimated_kg_co2e"] is None
        assert cc["data_status"] == "NO_ACTIVE_SESSION"


# ─── 4. Module Resilience & Degradation Tests ─────────────────────────────────

class TestDashboardModuleResilience:
    def test_member2_offline_does_not_break_dashboard(self, client, seeded_tokens, monkeypatch):
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}

        orig_send = httpx.AsyncClient.send

        async def mock_member2_down(self, request, *args, **kwargs):
            if "8002" in str(request.url) or "risk-report" in str(request.url):
                raise httpx.ConnectError("Member 2 service is down")
            return await orig_send(self, request, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "send", mock_member2_down)

        # Dashboard must return 200 OK despite Member 2 offline
        r_dash = client.get("/api/platform/dashboard", headers=admin_h)
        assert r_dash.status_code == 200
        d = r_dash.json()

        # Member 2 status must be OFFLINE, but other modules remain available
        assert d["module_health"]["member_2_policy"]["service_status"] == "OFFLINE"
        assert d["module_health"]["member_5_platform"]["service_status"] == "ONLINE"
        assert d["suppliers"]["total_suppliers"] >= 5


# ─── 5. Policy Evaluation Integrity & Resilience Tests ────────────────────────

class TestDashboardPolicyEvaluationIntegrity:
    def test_no_policy_evaluation_exists_reports_not_evaluated_and_null(self, client, seeded_tokens, monkeypatch):
        """When no policy evaluation exists, dashboard reports NOT_EVALUATED with null scores."""
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}

        async def mock_m2_online(self, request, *args, **kwargs):
            if "8002/health" in str(request.url):
                return httpx.Response(200, json={"status": "healthy"})
            return httpx.Response(503, json={"status": "unavailable"})

        monkeypatch.setattr(httpx.AsyncClient, "send", mock_m2_online)

        r_dash = client.get("/api/platform/dashboard", headers=admin_h)
        assert r_dash.status_code == 200
        d = r_dash.json()

        pc = d["policy_checker"]
        assert pc["service_status"] == "ONLINE"
        assert pc["data_status"] == "NOT_EVALUATED"
        assert pc["latest_overall_esg_score"] is None
        assert pc["latest_policy_risk_level"] is None

        # Verify KPI metric is PENDING with null score
        policy_kpi = next(k for k in d["kpi_scores"] if k["label"] == "Policy Baseline Alignment")
        assert policy_kpi["score"] is None
        assert policy_kpi["status"] == "PENDING"

    def test_member2_online_but_no_evaluation_exists(self, client, seeded_tokens, monkeypatch):
        """Health check returns ONLINE, but this must NOT be treated as proof of evaluated data."""
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}

        async def mock_m2_online(self, request, *args, **kwargs):
            if "8002/health" in str(request.url):
                return httpx.Response(200, json={"status": "healthy"})
            return httpx.Response(503, json={"status": "unavailable"})

        monkeypatch.setattr(httpx.AsyncClient, "send", mock_m2_online)

        r_dash = client.get("/api/platform/dashboard", headers=admin_h)
        assert r_dash.status_code == 200
        d = r_dash.json()

        pc = d["policy_checker"]
        assert pc["service_status"] == "ONLINE"
        assert pc["data_status"] == "NOT_EVALUATED"
        assert pc["latest_overall_esg_score"] is None
        assert pc["latest_policy_risk_level"] is None

        # Health registry must reflect service online but data not evaluated
        m2_health = d["module_health"]["member_2_policy"]
        assert m2_health["service_status"] == "ONLINE"
        assert m2_health["data_status"] == "NOT_EVALUATED"

    def test_member2_offline_reports_unavailable_and_null(self, client, seeded_tokens, monkeypatch):
        """When Member 2 service is offline, dashboard reports UNAVAILABLE with null scores without failing."""
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}

        async def mock_m2_offline(self, request, *args, **kwargs):
            if "8002" in str(request.url):
                raise httpx.ConnectError("Member 2 service is down")
            return httpx.Response(503, json={"status": "unavailable"})

        monkeypatch.setattr(httpx.AsyncClient, "send", mock_m2_offline)

        r_dash = client.get("/api/platform/dashboard", headers=admin_h)
        assert r_dash.status_code == 200
        d = r_dash.json()

        pc = d["policy_checker"]
        assert pc["service_status"] == "OFFLINE"
        assert pc["data_status"] == "UNAVAILABLE"
        assert pc["latest_overall_esg_score"] is None
        assert pc["latest_policy_risk_level"] is None

    def test_genuine_member2_result_exists(self, client, seeded_tokens, monkeypatch):
        """When a genuine Member 2 evaluation result is persisted, dashboard surfaces it accurately."""
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}

        # Mock Member 2 service online
        async def mock_m2_online(self, request, *args, **kwargs):
            if "8002/health" in str(request.url):
                return httpx.Response(200, json={"status": "healthy"})
            return httpx.Response(503, json={"status": "unavailable"})

        monkeypatch.setattr(httpx.AsyncClient, "send", mock_m2_online)

        # Mock genuine persisted evaluation for tenant org_id = 1
        def mock_genuine_evaluation(db, org_id):
            if org_id == 1:
                return {
                    "risk_level": "LOW",
                    "overall_score": 88.5,
                    "organization_id": 1,
                }
            return None

        monkeypatch.setattr(
            "app.platform.services.dashboard_service.get_persisted_policy_evaluation",
            mock_genuine_evaluation,
        )

        r_dash = client.get("/api/platform/dashboard", headers=admin_h)
        assert r_dash.status_code == 200
        d = r_dash.json()

        pc = d["policy_checker"]
        assert pc["service_status"] == "ONLINE"
        assert pc["data_status"] == "ACTIVE"
        assert pc["latest_overall_esg_score"] == 88.5
        assert pc["latest_policy_risk_level"] == "LOW"

        # KPI metric is ASSESSED with the real score
        policy_kpi = next(k for k in d["kpi_scores"] if k["label"] == "Policy Baseline Alignment")
        assert policy_kpi["score"] == 88.5
        assert policy_kpi["status"] == "ASSESSED"

    def test_local_fallback_findings_exist_without_genuine_member2_result(self, client, seeded_tokens, monkeypatch):
        """Existence of findings titled 'Policy Discrepancy' must NOT cause fabricated scores."""
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}

        async def mock_m2_online(self, request, *args, **kwargs):
            if "8002/health" in str(request.url):
                return httpx.Response(200, json={"status": "healthy"})
            return httpx.Response(503, json={"status": "unavailable"})

        monkeypatch.setattr(httpx.AsyncClient, "send", mock_m2_online)

        # Add a local fallback finding titled 'Policy Discrepancy'
        db = SessionLocal()
        fb_finding_id = None
        try:
            sup = db.query(Supplier).filter(Supplier.organization_id == 1).first()
            assert sup is not None
            fb_finding = SupplierFinding(
                supplier_id=sup.id,
                title="Policy Discrepancy: Governance - Local Audit Gap",
                category="Governance",
                severity="Medium",
                likelihood=3,
                impact=3,
                risk_score=36.0,
                description="Local fallback finding created without remote Member 2 API evaluation.",
                recommendation="Review policy alignment when service becomes available.",
                status="Open",
            )
            db.add(fb_finding)
            db.commit()
            fb_finding_id = fb_finding.id
        finally:
            db.close()

        try:
            r_dash = client.get("/api/platform/dashboard", headers=admin_h)
            assert r_dash.status_code == 200
            d = r_dash.json()

            pc = d["policy_checker"]
            # Must NOT fabricate MODERATE risk or 80.0 overall score from the presence of Policy Discrepancy finding
            assert pc["latest_overall_esg_score"] is None
            assert pc["latest_policy_risk_level"] is None
            assert pc["data_status"] == "NOT_EVALUATED"
        finally:
            if fb_finding_id is not None:
                db_clean = SessionLocal()
                try:
                    db_clean.query(SupplierFinding).filter(SupplierFinding.id == fb_finding_id).delete()
                    db_clean.commit()
                finally:
                    db_clean.close()

    def test_organization_a_cannot_access_organization_b_evaluation_results(self, client, tenant_fixture, monkeypatch):
        """Organization B cannot access Organization A's baseline policy or evaluation results."""
        t_a = tenant_fixture["org_a"]
        t_b = tenant_fixture["org_b"]

        h_a = {"Authorization": f"Bearer {t_a['token']}"}
        h_b = {"Authorization": f"Bearer {t_b['token']}"}

        # Mock Member 2 online
        async def mock_m2_online(self, request, *args, **kwargs):
            if "8002/health" in str(request.url):
                return httpx.Response(200, json={"status": "healthy"})
            return httpx.Response(503, json={"status": "unavailable"})

        monkeypatch.setattr(httpx.AsyncClient, "send", mock_m2_online)

        # Mock persisted evaluation ONLY for Org A
        def mock_tenant_scoped_evaluation(db, org_id):
            if org_id == t_a["id"]:
                return {
                    "risk_level": "LOW",
                    "overall_score": 92.0,
                    "organization_id": t_a["id"],
                }
            return None

        monkeypatch.setattr(
            "app.platform.services.dashboard_service.get_persisted_policy_evaluation",
            mock_tenant_scoped_evaluation,
        )

        # Org A sees its genuine evaluation
        r_a = client.get("/api/platform/dashboard", headers=h_a)
        assert r_a.status_code == 200
        d_a = r_a.json()
        assert d_a["policy_checker"]["data_status"] == "ACTIVE"
        assert d_a["policy_checker"]["latest_overall_esg_score"] == 92.0

        # Org B MUST NOT see Org A's evaluation
        r_b = client.get("/api/platform/dashboard", headers=h_b)
        assert r_b.status_code == 200
        d_b = r_b.json()
        assert d_b["policy_checker"]["data_status"] == "NOT_EVALUATED"
        assert d_b["policy_checker"]["latest_overall_esg_score"] is None
        assert d_b["policy_checker"]["latest_policy_risk_level"] is None


# ─── 6. Filter Behavior & Transparency Tests ─────────────────────────────────

class TestDashboardFilterBehavior:
    def test_category_filter_social(self, client, seeded_tokens):
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}

        r_dash = client.get("/api/platform/dashboard?category=Social", headers=admin_h)
        assert r_dash.status_code == 200
        d = r_dash.json()

        assert d["filters_applied"]["category"] == "Social"
        for finding in d["priority_findings"]:
            assert finding["category"].capitalize() == "Social"

    def test_honest_period_filter_reporting(self, client, seeded_tokens):
        admin_h = {"Authorization": f"Bearer {seeded_tokens['admin']}"}

        r_dash = client.get("/api/platform/dashboard?reporting_period=FY%202025%E2%80%9326", headers=admin_h)
        assert r_dash.status_code == 200
        d = r_dash.json()

        assert d["filters_applied"]["reporting_period"] == "FY 2025–26"
        # Transparently reports that session-based cloud carbon does not support multi-year historical filtering
        assert d["filters_applied"]["period_filtering_supported"]["member_4_cloud"] is False
        assert d["filters_applied"]["period_filtering_supported"]["member_5_suppliers"] is True

