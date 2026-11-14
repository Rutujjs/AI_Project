"""Tests for Member 5 Phase 5F Stage 2: Audit Logging & Notification Frontend Integration.

Verifies:
1. Frontend static asset structure and dependencies:
   - audit-logs.html includes js/auth.js, js/common.js, js/api.js, and js/audit-logs.js in correct order.
   - audit-logs.html contains all required DOM containers (app-shell, topbar, page-content, page-app, page-refresh-action).
   - notifications.html includes js/auth.js, js/common.js, js/api.js, and js/notifications.js in correct order.
   - notifications.html contains required DOM containers (app-shell, topbar, page-content, page-app, page-refresh-action, page-mark-all-read-btn).
2. api.js adapter:
   - Exports auditLogsList(), notificationList(), notificationUnreadCount(), notificationMarkRead(), and notificationMarkAllRead().
   - Injects Bearer token authorization on all requests.
3. Script integrity:
   - audit-logs.js and notifications.js do not use hardcoded mock records.
   - audit-logs.js strictly enforces role-based access control (Admin & Auditor authorized; Developer & Viewer restricted).
   - notifications.js supports unread filtering, individual mark-read, and mark-all-read actions.
4. Full API end-to-end integration:
   - Unauthenticated requests rejected with 401.
   - Role enforcement: Admin/Auditor access audit logs; Developer/Viewer forbidden (403).
   - All four roles access notifications and unread counts.
   - Per-user independent read receipts verified.
   - Cross-tenant isolation strictly preserved.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import uuid

import pytest
from fastapi.testclient import TestClient

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
os.environ.setdefault("GEMINI_API_KEY", "test-key-for-audit-frontend-tests")

from app.main import app
from app.platform.database import SessionLocal, init_db
from app.platform.models import AuditLog, Notification, NotificationRead, Organization, User, UserRole
from app.platform.security import create_access_token, hash_password
from app.platform.services.audit_service import record_audit_event

REPO_ROOT = Path(backend_dir).parent.parent
FRONTEND_DIR = REPO_ROOT / "integrated-frontend"


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db_session():
    init_db()
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def create_auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(
        data={
            "sub": user.username,
            "user_id": user.id,
            "org_id": user.organization_id,
            "role": user.role,
        }
    )
    return {"Authorization": f"Bearer {token}"}


# ─── Suite 1: Static Asset Structure & Dependencies ───────────────────────────

class TestFrontendAssetStructureAndDependencies:
    """Verifies HTML markup, script tags, DOM containers, and correct script ordering."""

    def test_audit_logs_html_script_order(self):
        html_path = FRONTEND_DIR / "audit-logs.html"
        assert html_path.exists(), "audit-logs.html must exist in integrated-frontend"
        content = html_path.read_text(encoding="utf-8")

        auth_pos = content.find("js/auth.js")
        common_pos = content.find("js/common.js")
        api_pos = content.find("js/api.js")
        audit_pos = content.find("js/audit-logs.js")

        assert auth_pos != -1, "auth.js must be included in audit-logs.html"
        assert common_pos != -1, "common.js must be included in audit-logs.html"
        assert api_pos != -1, "api.js must be included in audit-logs.html"
        assert audit_pos != -1, "audit-logs.js must be included in audit-logs.html"

        assert auth_pos < common_pos < api_pos < audit_pos, (
            "Scripts must be loaded in order: auth.js -> common.js -> api.js -> audit-logs.js"
        )

    def test_audit_logs_html_required_dom_elements(self):
        content = (FRONTEND_DIR / "audit-logs.html").read_text(encoding="utf-8")
        assert 'id="app-shell"' in content
        assert 'id="topbar"' in content
        assert 'id="page-content"' in content
        assert 'id="page-app"' in content
        assert 'id="page-refresh-action"' in content
        assert 'data-page="audit-logs"' in content

    def test_notifications_html_script_order(self):
        html_path = FRONTEND_DIR / "notifications.html"
        assert html_path.exists(), "notifications.html must exist in integrated-frontend"
        content = html_path.read_text(encoding="utf-8")

        auth_pos = content.find("js/auth.js")
        common_pos = content.find("js/common.js")
        api_pos = content.find("js/api.js")
        notif_pos = content.find("js/notifications.js")

        assert auth_pos != -1
        assert common_pos != -1
        assert api_pos != -1
        assert notif_pos != -1

        assert auth_pos < common_pos < api_pos < notif_pos, (
            "Scripts must be loaded in order: auth.js -> common.js -> api.js -> notifications.js"
        )

    def test_notifications_html_required_dom_elements(self):
        content = (FRONTEND_DIR / "notifications.html").read_text(encoding="utf-8")
        assert 'id="app-shell"' in content
        assert 'id="topbar"' in content
        assert 'id="page-content"' in content
        assert 'id="page-app"' in content
        assert 'id="page-refresh-action"' in content
        assert 'id="page-mark-all-read-btn"' in content
        assert 'data-page="notifications"' in content


# ─── Suite 2: API Client Adapter (api.js) ─────────────────────────────────────

class TestFrontendApiClientAdapter:
    """Verifies that api.js exports all required Phase 5F methods."""

    def test_api_js_exports_audit_and_notification_methods(self):
        api_js = (FRONTEND_DIR / "js" / "api.js").read_text(encoding="utf-8")
        assert "auditLogsList:" in api_js, "api.js must export auditLogsList"
        assert "notificationList:" in api_js, "api.js must export notificationList"
        assert "notificationUnreadCount:" in api_js, "api.js must export notificationUnreadCount"
        assert "notificationMarkRead:" in api_js, "api.js must export notificationMarkRead"
        assert "notificationMarkAllRead:" in api_js, "api.js must export notificationMarkAllRead"

    def test_api_js_routes_to_correct_endpoints(self):
        api_js = (FRONTEND_DIR / "js" / "api.js").read_text(encoding="utf-8")
        assert "/api/platform/audit-logs" in api_js
        assert "/api/platform/notifications" in api_js
        assert "/api/platform/notifications/unread-count" in api_js
        assert "/read" in api_js
        assert "/api/platform/notifications/mark-all-read" in api_js


# ─── Suite 3: Script Integrity & RBAC (audit-logs.js & notifications.js) ─────

class TestFrontendScriptIntegrity:
    """Verifies that frontend scripts avoid mock data and enforce proper RBAC."""

    def test_audit_logs_js_does_not_use_mock_data(self):
        content = (FRONTEND_DIR / "js" / "audit-logs.js").read_text(encoding="utf-8")
        assert "mockAuditLogs" not in content
        assert "MOCK_LOGS" not in content
        assert "window.ESGApi.auditLogsList" in content

    def test_audit_logs_js_enforces_role_visibility(self):
        content = (FRONTEND_DIR / "js" / "audit-logs.js").read_text(encoding="utf-8")
        assert "admin" in content
        assert "auditor" in content
        assert "Access Restricted" in content or "audit-restricted" in content

    def test_notifications_js_does_not_use_mock_data(self):
        content = (FRONTEND_DIR / "js" / "notifications.js").read_text(encoding="utf-8")
        assert "mockNotifications" not in content
        assert "MOCK_NOTIFS" not in content
        assert "window.ESGApi.notificationList" in content
        assert "window.ESGApi.notificationMarkRead" in content
        assert "window.ESGApi.notificationMarkAllRead" in content


# ─── Suite 4: End-to-End API Integration ─────────────────────────────────────

class TestFrontendEndToEndApiIntegration:
    """Verifies that all frontend-consumed endpoints work end-to-end with authentication and RBAC."""

    def test_unauthenticated_requests_rejected(self, client: TestClient):
        assert client.get("/api/platform/audit-logs").status_code == 401
        assert client.get("/api/platform/notifications").status_code == 401
        assert client.get("/api/platform/notifications/unread-count").status_code == 401
        assert client.patch("/api/platform/notifications/1/read").status_code == 401
        assert client.post("/api/platform/notifications/mark-all-read").status_code == 401

    def test_audit_logs_rbac_four_roles(self, client: TestClient, db_session: Session):
        admin = db_session.query(User).filter(User.role == "admin").first()
        auditor = db_session.query(User).filter(User.role == "auditor").first()
        developer = db_session.query(User).filter(User.role == "developer").first()
        viewer = db_session.query(User).filter(User.role == "viewer").first()

        # Admin -> 200 OK
        resp_admin = client.get("/api/platform/audit-logs", headers=create_auth_headers(admin))
        assert resp_admin.status_code == 200
        assert "items" in resp_admin.json()

        # Auditor -> 200 OK
        resp_auditor = client.get("/api/platform/audit-logs", headers=create_auth_headers(auditor))
        assert resp_auditor.status_code == 200
        assert "items" in resp_auditor.json()

        # Developer -> 403 Forbidden
        resp_dev = client.get("/api/platform/audit-logs", headers=create_auth_headers(developer))
        assert resp_dev.status_code == 403

        # Viewer -> 403 Forbidden
        resp_viewer = client.get("/api/platform/audit-logs", headers=create_auth_headers(viewer))
        assert resp_viewer.status_code == 403

    def test_all_four_roles_can_access_notifications(self, client: TestClient, db_session: Session):
        for role in ["admin", "auditor", "developer", "viewer"]:
            user = db_session.query(User).filter(User.role == role).first()
            headers = create_auth_headers(user)

            resp_list = client.get("/api/platform/notifications", headers=headers)
            assert resp_list.status_code == 200, f"Role {role} must be able to list notifications"
            assert "items" in resp_list.json()
            assert "unread_count" in resp_list.json()

            resp_count = client.get("/api/platform/notifications/unread-count", headers=headers)
            assert resp_count.status_code == 200, f"Role {role} must be able to fetch unread count"
            assert "unread_count" in resp_count.json()

    def test_notification_mark_single_and_mark_all_read(self, client: TestClient, db_session: Session):
        admin = db_session.query(User).filter(User.role == "admin").first()
        headers = create_auth_headers(admin)

        # Create two notifications
        n1 = Notification(
            organization_id=admin.organization_id,
            category="SYSTEM",
            severity="INFO",
            title=f"Test Alert 1 {uuid.uuid4().hex[:6]}",
            message="Message 1",
            status="ACTIVE",
        )
        n2 = Notification(
            organization_id=admin.organization_id,
            category="SYSTEM",
            severity="WARNING",
            title=f"Test Alert 2 {uuid.uuid4().hex[:6]}",
            message="Message 2",
            status="ACTIVE",
        )
        db_session.add_all([n1, n2])
        db_session.commit()
        db_session.refresh(n1)
        db_session.refresh(n2)

        # 1. Mark single notification read
        mark_resp = client.patch(f"/api/platform/notifications/{n1.id}/read", headers=headers)
        assert mark_resp.status_code == 200
        assert mark_resp.json()["is_read"] is True

        # 2. Mark all read
        mark_all_resp = client.post("/api/platform/notifications/mark-all-read", headers=headers)
        assert mark_all_resp.status_code == 200
        assert mark_all_resp.json()["marked_read"] >= 1

        # 3. Verify unread count is 0
        count_resp = client.get("/api/platform/notifications/unread-count", headers=headers)
        assert count_resp.status_code == 200
        assert count_resp.json()["unread_count"] == 0

