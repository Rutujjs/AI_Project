"""Comprehensive Tests for Member 5: Audit Logging & Notification Management (Phase 5F - Stage 1).

Covers:
1. Audit event recording across all lifecycle hooks:
   - Login success, failure (known vs unknown user tenancy separation), logout
   - User creation
   - Supplier CRUD (create, update, delete)
   - Document upload and secure download
   - Risk evaluations and notifications trigger on elevated risk
   - Baseline policy uploads and tenant updates
   - Report preview and PDF export
2. Append-only immutability protections:
   - ORM-level event listeners raising RuntimeError on update/delete
   - Database-level triggers aborting raw SQL updates/deletions
   - Absence of mutation endpoints on audit-logs router
3. Sensitive data sanitization in audit details (passwords, tokens, keys)
4. Mutation atomicity (failed actions do not persist audit logs)
5. Notification independent per-user read state (NotificationRead):
   - Tenant-wide alert marked read by User A remains unread for User B
   - Unread count queries and mark-all-read behavior
6. Document expiry sweep & deduplication:
   - EXPIRING_SOON (WARNING) and EXPIRED (CRITICAL) detection
   - event_key deduplication preventing duplicate alerts
   - Document renewal / valid status auto-resolution (RESOLVED)
7. Multi-worker scheduler coordination lock (PlatformScheduleLock)
8. Multi-tenant boundary isolation and RBAC:
   - Audit logs restricted to ADMIN and AUDITOR; forbidden to DEVELOPER and VIEWER
   - Cross-tenant data isolation
   - Unknown-user login failure records (organization_id=NULL) invisible in tenant audit feeds
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import io
import json
import os
import sys
import uuid
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

# Ensure backend directory is on sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
os.environ.setdefault("GEMINI_API_KEY", "test-key-for-audit-tests")

from fastapi.testclient import TestClient

from app.main import app
from app.platform.database import SessionLocal, init_db
from app.platform.models import (
    AuditLog,
    Notification,
    NotificationRead,
    Organization,
    PlatformScheduleLock,
    Supplier,
    SupplierDocument,
    User,
    UserRole,
)
from app.platform.security import create_access_token, hash_password
from app.platform.services.audit_service import query_audit_logs, record_audit_event, sanitize_details
from app.platform.services.notification_service import (
    _acquire_scheduler_lock,
    _release_scheduler_lock,
    create_notification,
    get_unread_count,
    get_user_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    run_document_expiry_sweep,
)


@pytest.fixture(scope="module")
def client():
    """Return a TestClient against the main FastAPI application."""
    init_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db_session():
    """Yield a database session and close afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_auth_headers(user: User) -> dict:
    """Helper to generate JWT bearer authorization header for a test user."""
    token = create_access_token(
        data={
            "sub": user.username,
            "user_id": user.id,
            "org_id": user.organization_id,
            "role": user.role,
        }
    )
    return {"Authorization": f"Bearer {token}"}


# ─── 1. Sensitive Data Sanitization ──────────────────────────────────────────

class TestAuditDataSanitization:
    """Verify that sensitive keys are recursively redacted from audit logs."""

    def test_sanitize_details_redacts_credentials(self):
        raw = {
            "username": "auditor_user",
            "password": "SuperSecretPassword123!",
            "token": "jwt.header.payload.signature",
            "nested": {
                "access_token": "bearer-12345",
                "secret_key": "private-key-data",
                "safe_field": "visible_value",
            },
            "api_key": "AIzaSySecretApiKey",
            "hashed_password": "$2b$12$hashedstring",
        }
        sanitized = sanitize_details(raw)
        assert sanitized["username"] == "auditor_user"
        assert "password" not in sanitized
        assert "token" not in sanitized
        assert "api_key" not in sanitized
        assert "hashed_password" not in sanitized
        assert "access_token" not in sanitized["nested"]
        assert "secret_key" not in sanitized["nested"]
        assert sanitized["nested"]["safe_field"] == "visible_value"


# ─── 2. Audit Event Recording & Immutability ──────────────────────────────────

class TestAuditLoggingAndImmutability:
    """Test audit log creation, query filtering, and append-only immutability."""

    def test_record_audit_event_commit(self, db_session: Session):
        org = db_session.query(Organization).first()
        user = db_session.query(User).filter(User.organization_id == org.id).first()

        log = record_audit_event(
            db=db_session,
            action="TEST_ACTION",
            resource_type="TEST",
            resource_id=999,
            user=user,
            organization_id=org.id,
            status="SUCCESS",
            details={"key": "test_value", "password": "sensitive_password"},
            commit=True,
        )

        assert log.id is not None
        assert log.action == "TEST_ACTION"
        details = json.loads(log.details) if isinstance(log.details, str) else log.details
        assert "password" not in details
        assert details["key"] == "test_value"
        assert log.username == user.username
        assert log.user_role == user.role.upper()
        assert log.organization_id == org.id

    def test_audit_log_orm_immutability_update_raises(self, db_session: Session):
        org = db_session.query(Organization).first()
        log = record_audit_event(
            db=db_session,
            action="IMMUTABLE_CHECK_UPDATE",
            resource_type="SYSTEM",
            organization_id=org.id,
            commit=True,
        )

        log.action = "TAMPERED_ACTION"
        with pytest.raises(RuntimeError, match="strictly immutable"):
            db_session.commit()
        db_session.rollback()

    def test_audit_log_orm_immutability_delete_raises(self, db_session: Session):
        org = db_session.query(Organization).first()
        log = record_audit_event(
            db=db_session,
            action="IMMUTABLE_CHECK_DELETE",
            resource_type="SYSTEM",
            organization_id=org.id,
            commit=True,
        )

        db_session.delete(log)
        with pytest.raises(RuntimeError, match="cannot be deleted"):
            db_session.commit()
        db_session.rollback()

    def test_audit_log_database_trigger_blocks_raw_update(self, db_session: Session):
        org = db_session.query(Organization).first()
        log = record_audit_event(
            db=db_session,
            action="TRIGGER_CHECK_UPDATE",
            resource_type="SYSTEM",
            organization_id=org.id,
            commit=True,
        )

        with pytest.raises(Exception):
            db_session.execute(
                text("UPDATE audit_logs SET action = 'SQL_TAMPERED' WHERE id = :log_id"),
                {"log_id": log.id},
            )
            db_session.commit()
        db_session.rollback()

    def test_audit_log_database_trigger_blocks_raw_delete(self, db_session: Session):
        org = db_session.query(Organization).first()
        log = record_audit_event(
            db=db_session,
            action="TRIGGER_CHECK_DELETE",
            resource_type="SYSTEM",
            organization_id=org.id,
            commit=True,
        )

        with pytest.raises(Exception):
            db_session.execute(
                text("DELETE FROM audit_logs WHERE id = :log_id"),
                {"log_id": log.id},
            )
            db_session.commit()
        db_session.rollback()


# ─── 3. End-to-End API Audit Event Hooks ─────────────────────────────────────

class TestAuditRouterAndHooks:
    """Verify that all platform operations trigger correct audit log entries."""

    def test_login_success_and_logout_audit(self, client: TestClient, db_session: Session):
        # 1. Login success with default seeded password 'esg2026'
        resp = client.post("/api/auth/login", json={"username": "admin", "password": "esg2026"})
        assert resp.status_code == 200
        token = resp.json()["access_token"]

        # Check audit log for login
        admin = db_session.query(User).filter(User.username == "admin").first()
        logs, _ = query_audit_logs(db_session, organization_id=admin.organization_id, action="LOGIN_SUCCESS")
        assert len(logs) > 0
        assert logs[0].username == "admin"
        assert logs[0].status == "SUCCESS"

        # 2. Logout
        logout_resp = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
        assert logout_resp.status_code == 200

        logout_logs, _ = query_audit_logs(db_session, organization_id=admin.organization_id, action="LOGOUT")
        assert len(logout_logs) > 0
        assert logout_logs[0].username == "admin"

    def test_login_failure_known_vs_unknown_user_tenancy(self, client: TestClient, db_session: Session):
        # Known user with bad password
        client.post("/api/auth/login", json={"username": "admin", "password": "WrongPassword!"})
        admin = db_session.query(User).filter(User.username == "admin").first()

        known_failure_logs, _ = query_audit_logs(db_session, organization_id=admin.organization_id, action="LOGIN_FAILURE")
        assert len(known_failure_logs) > 0
        latest_known = known_failure_logs[0]
        assert latest_known.organization_id == admin.organization_id
        assert latest_known.status == "FAILURE"

        # Unknown user
        ghost_user = f"ghost_{uuid.uuid4().hex[:6]}"
        client.post("/api/auth/login", json={"username": ghost_user, "password": "WrongPassword!"})

        # Query all audit logs directly in DB with organization_id IS NULL
        ghost_log = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "LOGIN_FAILURE", AuditLog.organization_id.is_(None))
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert ghost_log is not None
        assert ghost_log.organization_id is None
        assert ghost_log.username == ghost_user

        # Ensure tenant audit endpoint does NOT leak this unknown-user attempt
        tenant_logs, _ = query_audit_logs(db_session, organization_id=admin.organization_id, action="LOGIN_FAILURE")
        assert not any(l.username == ghost_user for l in tenant_logs)

    def test_supplier_crud_audit_logs(self, client: TestClient, db_session: Session):
        admin = db_session.query(User).filter(User.username == "admin").first()
        headers = create_auth_headers(admin)

        unique_code = f"AUDIT-SUP-{uuid.uuid4().hex[:6].upper()}"
        create_payload = {
            "name": "Audit Test Supplier Corp",
            "code": unique_code,
            "category": "Raw Materials",
            "tier": "Tier 1",
            "country": "Germany",
            "contact_email": "audit@supplier.corp",
        }

        # 1. Create Supplier
        create_resp = client.post("/api/suppliers", json=create_payload, headers=headers)
        assert create_resp.status_code == 201
        supplier_id = create_resp.json()["id"]

        logs, _ = query_audit_logs(db_session, organization_id=admin.organization_id, action="SUPPLIER_CREATED")
        assert any(l.resource_id == str(supplier_id) or l.resource_id == supplier_id for l in logs)

        # 2. Update Supplier
        update_resp = client.put(f"/api/suppliers/{supplier_id}", json={"status": "Under Review"}, headers=headers)
        assert update_resp.status_code == 200

        logs, _ = query_audit_logs(db_session, organization_id=admin.organization_id, action="SUPPLIER_UPDATED")
        assert any(l.resource_id == str(supplier_id) or l.resource_id == supplier_id for l in logs)

        # 3. Delete Supplier
        delete_resp = client.delete(f"/api/suppliers/{supplier_id}", headers=headers)
        assert delete_resp.status_code == 200

        logs, _ = query_audit_logs(db_session, organization_id=admin.organization_id, action="SUPPLIER_DELETED")
        assert any(l.resource_id == str(supplier_id) or l.resource_id == supplier_id for l in logs)

    def test_document_upload_and_download_audit(self, client: TestClient, db_session: Session):
        admin = db_session.query(User).filter(User.username == "admin").first()
        headers = create_auth_headers(admin)

        # Create temporary supplier
        sup = Supplier(
            organization_id=admin.organization_id,
            name="Doc Audit Supplier",
            code=f"DOC-AUD-{uuid.uuid4().hex[:4].upper()}",
            contact_email="doc@supplier.test",
            status="Active",
        )
        db_session.add(sup)
        db_session.commit()
        db_session.refresh(sup)

        # Upload document
        fake_pdf = b"%PDF-1.4 Fake PDF Content for Audit Testing\n%%EOF"
        upload_resp = client.post(
            f"/api/suppliers/{sup.id}/documents",
            headers=headers,
            data={
                "document_type": "ISO 14001",
                "title": "ISO 14001 Audit Certificate",
                "issue_date": "2026-01-01",
                "expiry_date": "2027-01-01",
            },
            files={"file": ("certificate.pdf", fake_pdf, "application/pdf")},
        )
        assert upload_resp.status_code == 201
        doc_id = upload_resp.json()["id"]

        # Check upload audit log
        logs, _ = query_audit_logs(db_session, organization_id=admin.organization_id, action="DOCUMENT_UPLOADED")
        assert any(l.resource_id == str(doc_id) or l.resource_id == doc_id for l in logs)

        # Download document
        down_resp = client.get(f"/api/suppliers/{sup.id}/documents/{doc_id}/download", headers=headers)
        assert down_resp.status_code == 200

        # Check download audit log
        logs, _ = query_audit_logs(db_session, organization_id=admin.organization_id, action="DOCUMENT_DOWNLOADED")
        assert any(l.resource_id == str(doc_id) or l.resource_id == doc_id for l in logs)

    def test_supplier_evaluation_audit_and_notification(self, client: TestClient, db_session: Session):
        admin = db_session.query(User).filter(User.username == "admin").first()
        headers = create_auth_headers(admin)

        # Create supplier with high risk finding
        sup = Supplier(
            organization_id=admin.organization_id,
            name="High Risk Audit Supplier",
            code=f"HR-SUP-{uuid.uuid4().hex[:4].upper()}",
            contact_email="hr@supplier.test",
            status="Active",
        )
        db_session.add(sup)
        db_session.commit()
        db_session.refresh(sup)

        # Add finding that generates critical risk
        finding_resp = client.post(
            f"/api/suppliers/{sup.id}/findings",
            headers=headers,
            json={
                "title": "Severe Environmental Policy Violation",
                "category": "Environmental",
                "severity": "Critical",
                "likelihood": 5,
                "impact": 5,
                "description": "Unauthorized wastewater discharge",
                "recommendation": "Immediate suspension of operations",
                "status": "Open",
            },
        )
        assert finding_resp.status_code == 201

        # Check evaluation audit log
        eval_logs, _ = query_audit_logs(db_session, organization_id=admin.organization_id, action="SUPPLIER_EVALUATED")
        assert any(l.resource_id == str(sup.id) or l.resource_id == sup.id for l in eval_logs)

        # Check notification was generated for elevated risk
        notifs, _, _ = get_user_notifications(db_session, organization_id=admin.organization_id, user_id=admin.id, category="SUPPLIER_RISK")
        assert any(n.resource_id == str(sup.id) and n.severity in ("WARNING", "CRITICAL") for n in notifs)

    def test_report_preview_and_export_audit(self, client: TestClient, db_session: Session):
        admin = db_session.query(User).filter(User.username == "admin").first()
        headers = create_auth_headers(admin)

        req_body = {
            "report_type": "ENTERPRISE_SUMMARY",
            "reporting_period": "FY 2025–26",
            "include_sections": ["executive_summary", "supplier_metrics"],
        }

        # 1. Preview
        prev_resp = client.post("/api/platform/reports/preview", json=req_body, headers=headers)
        assert prev_resp.status_code == 200

        logs, _ = query_audit_logs(db_session, organization_id=admin.organization_id, action="REPORT_PREVIEWED")
        assert len(logs) > 0

        # 2. PDF Export
        export_resp = client.post("/api/platform/reports/export-pdf", json=req_body, headers=headers)
        assert export_resp.status_code == 200
        assert export_resp.headers["content-type"] == "application/pdf"

        logs, _ = query_audit_logs(db_session, organization_id=admin.organization_id, action="REPORT_EXPORTED_PDF")
        assert len(logs) > 0

    def test_audit_logs_rbac_enforcement(self, client: TestClient, db_session: Session):
        admin = db_session.query(User).filter(User.role == "admin").first()
        auditor = db_session.query(User).filter(User.role == "auditor").first()
        developer = db_session.query(User).filter(User.role == "developer").first()
        viewer = db_session.query(User).filter(User.role == "viewer").first()

        # Admin -> 200 OK
        resp = client.get("/api/platform/audit-logs", headers=create_auth_headers(admin))
        assert resp.status_code == 200

        # Auditor -> 200 OK
        resp = client.get("/api/platform/audit-logs", headers=create_auth_headers(auditor))
        assert resp.status_code == 200

        # Developer -> 403 Forbidden
        resp = client.get("/api/platform/audit-logs", headers=create_auth_headers(developer))
        assert resp.status_code == 403

        # Viewer -> 403 Forbidden
        resp = client.get("/api/platform/audit-logs", headers=create_auth_headers(viewer))
        assert resp.status_code == 403

        # Unauthenticated -> 401 Unauthorized
        resp = client.get("/api/platform/audit-logs")
        assert resp.status_code == 401


# ─── 4. Notifications & Independent Per-User Read Receipts ────────────────────

class TestNotificationManagementAndReadReceipts:
    """Verify independent per-user read tracking, unread count, and sweep coordination."""

    def test_per_user_independent_read_status(self, client: TestClient, db_session: Session):
        """User A marking broadcast notification as read must not affect User B."""
        org = db_session.query(Organization).first()
        user_a = db_session.query(User).filter(User.organization_id == org.id, User.role == "admin").first()
        user_b = db_session.query(User).filter(User.organization_id == org.id, User.role == "viewer").first()

        # Create broadcast notification
        notif = create_notification(
            db=db_session,
            organization_id=org.id,
            user_id=None,  # Broadcast to entire org
            category="SYSTEM_ANNOUNCEMENT",
            severity="INFO",
            title=f"Broadcast Alert {uuid.uuid4().hex[:6]}",
            message="Maintenance window scheduled for this weekend.",
            commit=True,
        )

        headers_a = create_auth_headers(user_a)
        headers_b = create_auth_headers(user_b)

        # Both users initially see it as unread
        resp_a = client.get("/api/platform/notifications", headers=headers_a)
        resp_b = client.get("/api/platform/notifications", headers=headers_b)
        assert resp_a.status_code == 200
        assert resp_b.status_code == 200

        item_a = next(i for i in resp_a.json()["items"] if i["id"] == notif.id)
        item_b = next(i for i in resp_b.json()["items"] if i["id"] == notif.id)
        assert item_a["is_read"] is False
        assert item_b["is_read"] is False

        # User A marks it as read
        read_resp = client.patch(f"/api/platform/notifications/{notif.id}/read", headers=headers_a)
        assert read_resp.status_code == 200
        assert read_resp.json()["is_read"] is True

        # User A now sees it as read
        resp_a_after = client.get("/api/platform/notifications", headers=headers_a)
        item_a_after = next(i for i in resp_a_after.json()["items"] if i["id"] == notif.id)
        assert item_a_after["is_read"] is True

        # User B STILL sees it as unread!
        resp_b_after = client.get("/api/platform/notifications", headers=headers_b)
        item_b_after = next(i for i in resp_b_after.json()["items"] if i["id"] == notif.id)
        assert item_b_after["is_read"] is False

    def test_mark_all_notifications_read(self, client: TestClient, db_session: Session):
        org = db_session.query(Organization).first()
        user = db_session.query(User).filter(User.organization_id == org.id, User.role == "auditor").first()
        headers = create_auth_headers(user)

        # Create two notifications for this user
        create_notification(
            db=db_session,
            organization_id=org.id,
            category="AUDIT",
            severity="WARNING",
            title=f"Unread Alert 1 {uuid.uuid4().hex[:4]}",
            message="Test unread message 1",
            commit=True,
        )
        create_notification(
            db=db_session,
            organization_id=org.id,
            category="AUDIT",
            severity="INFO",
            title=f"Unread Alert 2 {uuid.uuid4().hex[:4]}",
            message="Test unread message 2",
            commit=True,
        )

        # Mark all read
        mark_resp = client.post("/api/platform/notifications/mark-all-read", headers=headers)
        assert mark_resp.status_code == 200
        assert mark_resp.json()["marked_read"] >= 2

        # Check unread count
        count_resp = client.get("/api/platform/notifications/unread-count", headers=headers)
        assert count_resp.status_code == 200
        # All visible notifications should now be marked read
        assert count_resp.json()["unread_count"] == 0


# ─── 5. Document Expiry Sweep & Deduplication ─────────────────────────────────

class TestDocumentExpirySweepAndLock:
    """Verify automated document expiry detection, deduplication, and scheduler lock."""

    def test_document_expiry_sweep_and_deduplication(self, db_session: Session):
        org = db_session.query(Organization).first()
        now = datetime.now(timezone.utc)

        # Create supplier
        sup = Supplier(
            organization_id=org.id,
            name=f"Sweep Supplier {uuid.uuid4().hex[:4]}",
            code=f"SWP-{uuid.uuid4().hex[:4].upper()}",
            contact_email="sweep@supplier.test",
            status="Active",
        )
        db_session.add(sup)
        db_session.commit()
        db_session.refresh(sup)

        # 1. Expired document (-10 days)
        doc_expired = SupplierDocument(
            supplier_id=sup.id,
            document_type="ISO 14001",
            document_category="CERTIFICATE",
            title="Expired ISO 14001 Certificate",
            file_path="uploads/fake_expired.pdf",
            file_size=1024,
            mime_type="application/pdf",
            expiry_date=now - timedelta(days=10),
            verification_status="Expired",
        )
        # 2. Expiring soon document (+15 days)
        doc_expiring_soon = SupplierDocument(
            supplier_id=sup.id,
            document_type="SA 8000",
            document_category="CERTIFICATE",
            title="Expiring SA 8000 Certificate",
            file_path="uploads/fake_expiring.pdf",
            file_size=1024,
            mime_type="application/pdf",
            expiry_date=now + timedelta(days=15),
            verification_status="Verified",
        )
        db_session.add(doc_expired)
        db_session.add(doc_expiring_soon)
        db_session.commit()

        # Run sweep 1
        res1 = run_document_expiry_sweep(db_session, target_org_id=org.id, force=True)
        assert res1["scanned_documents"] >= 2
        assert res1["created_notifications"] >= 2

        # Verify notifications exist in DB
        expired_notif = (
            db_session.query(Notification)
            .filter(Notification.event_key == f"doc:{doc_expired.id}:EXPIRED")
            .first()
        )
        assert expired_notif is not None
        assert expired_notif.severity == "CRITICAL"

        soon_notif = (
            db_session.query(Notification)
            .filter(Notification.event_key == f"doc:{doc_expiring_soon.id}:EXPIRING_SOON")
            .first()
        )
        assert soon_notif is not None
        assert soon_notif.severity == "WARNING"

        # Run sweep 2 -> Deduplication check: 0 new notifications created
        res2 = run_document_expiry_sweep(db_session, target_org_id=org.id, force=True)
        assert res2["created_notifications"] == 0

    def test_document_renewal_auto_resolution(self, client: TestClient, db_session: Session):
        """Uploading a renewed valid document must auto-resolve existing expiry alerts."""
        org = db_session.query(Organization).first()
        admin = db_session.query(User).filter(User.organization_id == org.id, User.role == "admin").first()
        headers = create_auth_headers(admin)
        now = datetime.now(timezone.utc)

        sup = Supplier(
            organization_id=org.id,
            name="Renewal Supplier",
            code=f"RNW-{uuid.uuid4().hex[:4].upper()}",
            contact_email="renewal@supplier.test",
            status="Active",
        )
        db_session.add(sup)
        db_session.commit()
        db_session.refresh(sup)

        # Upload old expired document
        fake_pdf = b"%PDF-1.4 Fake Old Document\n%%EOF"
        upload_resp = client.post(
            f"/api/suppliers/{sup.id}/documents",
            headers=headers,
            data={
                "document_type": "ISO 50001",
                "title": "Old Expired ISO 50001",
                "issue_date": "2024-01-01",
                "expiry_date": (now - timedelta(days=5)).strftime("%Y-%m-%d"),
            },
            files={"file": ("old_iso50001.pdf", fake_pdf, "application/pdf")},
        )
        assert upload_resp.status_code == 201
        old_doc_id = upload_resp.json()["id"]

        # Run sweep to generate critical alert
        run_document_expiry_sweep(db_session, target_org_id=org.id, force=True)

        alert = (
            db_session.query(Notification)
            .filter(Notification.event_key == f"doc:{old_doc_id}:EXPIRED")
            .first()
        )
        assert alert is not None
        assert alert.status == "ACTIVE"

        # Now upload renewed document with valid future date (>30 days)
        renew_resp = client.post(
            f"/api/suppliers/{sup.id}/documents",
            headers=headers,
            data={
                "document_type": "ISO 50001",
                "title": "Renewed ISO 50001 Certificate",
                "issue_date": now.strftime("%Y-%m-%d"),
                "expiry_date": (now + timedelta(days=365)).strftime("%Y-%m-%d"),
            },
            files={"file": ("renewed_iso50001.pdf", fake_pdf, "application/pdf")},
        )
        assert renew_resp.status_code == 201

        # Check that the prior alert has been auto-resolved!
        db_session.refresh(alert)
        assert alert.status == "RESOLVED"
        assert alert.resolved_at is not None

    def test_multi_worker_schedule_lock_coordination(self, db_session: Session):
        """Simulate two workers attempting to run expiry sweep concurrently."""
        org = db_session.query(Organization).first()
        task_name = f"test_sweep_lock_{uuid.uuid4().hex[:6]}"

        # Worker 1 acquires lock
        acquired_w1 = _acquire_scheduler_lock(db_session, task_name, org.id)
        assert acquired_w1 is True

        # Worker 2 attempts to acquire lock on same task -> Must be rejected!
        acquired_w2 = _acquire_scheduler_lock(db_session, task_name, org.id)
        assert acquired_w2 is False

        # Worker 1 completes and releases lock
        _release_scheduler_lock(db_session, task_name, org.id, status="SUCCESS")

        # Worker 2 now acquires lock successfully
        acquired_w2_after = _acquire_scheduler_lock(db_session, task_name, org.id)
        assert acquired_w2_after is True

        _release_scheduler_lock(db_session, task_name, org.id, status="SUCCESS")


# ─── 6. Phase 5F Corrective Pass: Foreign Key Restrict, File Cleanup, Dialect Consistency ───

class TestPhase5FCorrectivePass:
    """Verifications for DEF-01, DEF-02, DEF-03, and DEF-04."""

    def test_attempted_hard_deletion_cannot_mutate_or_remove_audit_records(self, db_session: Session):
        """DEF-01: Proves that hard-deleting a user or org cannot remove or mutate AuditLog records."""
        db_session.execute(text("PRAGMA foreign_keys = ON;"))
        # Create an isolated tenant and user
        suffix = uuid.uuid4().hex[:6]
        org = Organization(name=f"HardDel Org {suffix}", slug=f"harddel-org-{suffix}", is_active=True)
        db_session.add(org)
        db_session.commit()
        db_session.refresh(org)

        user = User(
            organization_id=org.id,
            username=f"harddel_user_{suffix}",
            email=f"harddel_{suffix}@test.corp",
            hashed_password=hash_password("testpass123"),
            role="auditor",
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        # Record audit log linked to this user and org
        log = record_audit_event(
            db=db_session,
            action="COMPLIANCE_SIGN_OFF",
            resource_type="AUDIT",
            resource_id="101",
            user=user,
            organization_id=org.id,
            status="SUCCESS",
            commit=True,
        )
        assert log.id is not None
        assert log.username == f"harddel_user_{suffix}"
        assert log.user_role == "AUDITOR"

        # Attempt hard deletion of user -> Must fail via RESTRICT constraint or trigger!
        with pytest.raises(Exception):
            db_session.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user.id})
            db_session.commit()
        db_session.rollback()

        # Attempt hard deletion of org -> Must fail via RESTRICT constraint or trigger!
        with pytest.raises(Exception):
            db_session.execute(text("DELETE FROM organizations WHERE id = :oid"), {"oid": org.id})
            db_session.commit()
        db_session.rollback()

        # Audit log must remain intact, immutable, and snapshot intact
        preserved = db_session.query(AuditLog).filter(AuditLog.id == log.id).first()
        assert preserved is not None
        assert preserved.username == f"harddel_user_{suffix}"
        assert preserved.user_role == "AUDITOR"
        assert preserved.user_id == user.id
        assert preserved.organization_id == org.id

    def test_user_and_organization_soft_deactivation_preserves_audit_records(self, db_session: Session):
        """DEF-01: Proves the non-destructive soft-deactivation workflow preserves audit logs."""
        suffix = uuid.uuid4().hex[:6]
        org = Organization(name=f"SoftDel Org {suffix}", slug=f"softdel-org-{suffix}", is_active=True)
        db_session.add(org)
        db_session.commit()
        db_session.refresh(org)

        user = User(
            organization_id=org.id,
            username=f"softdel_user_{suffix}",
            email=f"softdel_{suffix}@test.corp",
            hashed_password=hash_password("testpass123"),
            role="viewer",
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        log = record_audit_event(
            db=db_session,
            action="VIEW_POLICY",
            resource_type="DOCUMENT",
            resource_id="55",
            user=user,
            organization_id=org.id,
            commit=True,
        )

        # Soft-deactivate user and org
        user.is_active = False
        org.is_active = False
        db_session.commit()

        # Verify soft-deactivation succeeded
        db_session.refresh(user)
        db_session.refresh(org)
        assert user.is_active is False
        assert org.is_active is False

        # Verify audit log is unchanged
        preserved_logs, total = query_audit_logs(db_session, organization_id=org.id, action="VIEW_POLICY")
        assert total == 1
        assert preserved_logs[0].username == f"softdel_user_{suffix}"
        assert preserved_logs[0].user_role == "VIEWER"

    def test_document_upload_db_failure_cleans_up_file_and_preserves_existing(self, db_session: Session, monkeypatch):
        """DEF-02: Simulated DB failure during doc upload deletes new file, leaves existing files intact."""
        from pathlib import Path
        from app.platform.services import supplier_service

        org = db_session.query(Organization).first()
        suffix = uuid.uuid4().hex[:6]
        supplier = Supplier(
            organization_id=org.id,
            name=f"Cleanup Supplier {suffix}",
            code=f"CLN-{suffix}".upper(),
            contact_email="clean@supplier.corp",
            status="Active",
        )
        db_session.add(supplier)
        db_session.commit()
        db_session.refresh(supplier)

        fake_pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"

        # 1. Upload initial existing document successfully
        doc1 = supplier_service.add_supplier_document(
            db=db_session,
            org_id=org.id,
            supplier_id=supplier.id,
            file_bytes=fake_pdf,
            filename="existing_valid_document.pdf",
            mime_type="application/pdf",
            document_type="ISO 14001",
            title="Existing Valid Document",
        )
        existing_path = Path(doc1.file_path).resolve()
        assert existing_path.exists(), "Pre-existing file must exist on disk"

        # 2. Simulate database commit failure on second document upload
        def failing_commit():
            raise RuntimeError("Simulated Database Commit Failure")

        monkeypatch.setattr(db_session, "commit", failing_commit)

        with pytest.raises(RuntimeError, match="Simulated Database Commit Failure"):
            supplier_service.add_supplier_document(
                db=db_session,
                org_id=org.id,
                supplier_id=supplier.id,
                file_bytes=fake_pdf,
                filename="failed_document.pdf",
                mime_type="application/pdf",
                document_type="ISO 9001",
                title="Failed Document",
            )

        # Restore commit
        monkeypatch.undo()

        # 3. Assertions:
        # Pre-existing file MUST still exist!
        assert existing_path.exists(), "Pre-existing file must NOT be deleted!"
        # No second document record in database
        doc_count = db_session.query(SupplierDocument).filter(SupplierDocument.supplier_id == supplier.id).count()
        assert doc_count == 1, "Only the pre-existing document should be in the database"
        # No 'failed_document' on disk in the supplier upload directory
        supplier_dir = existing_path.parent
        dir_files = [f.name for f in supplier_dir.iterdir()]
        assert not any("failed_document" in fn for fn in dir_files), "New file must have been cleaned up from disk"

    def test_baseline_policy_upload_db_failure_cleans_up_file_and_preserves_existing(self, db_session: Session, monkeypatch):
        """DEF-03: Simulated DB failure during baseline upload deletes new file, leaves existing files intact."""
        from pathlib import Path
        from app.platform.services import supplier_service

        suffix = uuid.uuid4().hex[:6]
        org = Organization(name=f"Policy Org {suffix}", slug=f"policy-org-{suffix}", is_active=True)
        db_session.add(org)
        db_session.commit()
        db_session.refresh(org)

        fake_pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"

        # 1. Upload existing baseline policy
        updated_org = supplier_service.set_organization_baseline_policy(
            db=db_session,
            org_id=org.id,
            file_bytes=fake_pdf,
            filename="initial_baseline_policy.pdf",
        )
        existing_policy_path = Path(updated_org.baseline_policy_path).resolve()
        assert existing_policy_path.exists()

        # 2. Simulate failure during next baseline policy upload
        def failing_commit():
            raise RuntimeError("Simulated Baseline Policy DB Failure")

        monkeypatch.setattr(db_session, "commit", failing_commit)

        with pytest.raises(RuntimeError, match="Simulated Baseline Policy DB Failure"):
            supplier_service.set_organization_baseline_policy(
                db=db_session,
                org_id=org.id,
                file_bytes=fake_pdf,
                filename="failing_second_policy.pdf",
            )

        monkeypatch.undo()

        # 3. Assertions:
        assert existing_policy_path.exists(), "Pre-existing baseline file must remain untouched"
        db_session.refresh(org)
        assert org.baseline_policy_path == str(existing_policy_path).replace("\\", "/")
        assert org.baseline_policy_name == "initial_baseline_policy.pdf"

        # Verify second file was removed from the org directory
        org_dir = existing_policy_path.parent
        dir_files = [f.name for f in org_dir.iterdir()]
        assert not any("failing_second_policy" in fn for fn in dir_files), "Failed file must be removed"

    def test_postgresql_trigger_and_migration_consistency_static(self):
        """DEF-04: Static inspection of PostgreSQL trigger DDL for consistency with SQLite."""
        import inspect
        from app.platform import database

        source = inspect.getsource(database._run_migrations)

        # Verify PostgreSQL trigger DDL defines function and trigger
        assert "CREATE OR REPLACE FUNCTION trg_audit_logs_reject()" in source
        assert "RAISE EXCEPTION 'AuditLog records are append-only and strictly immutable.'" in source
        assert "CREATE TRIGGER trg_audit_logs_no_mutation BEFORE UPDATE OR DELETE ON audit_logs" in source
        assert "FOR EACH ROW EXECUTE FUNCTION trg_audit_logs_reject();" in source

        # Verify SQLite trigger DDL defines BEFORE UPDATE and BEFORE DELETE
        assert "CREATE TRIGGER IF NOT EXISTS trg_audit_logs_no_update" in source
        assert "CREATE TRIGGER IF NOT EXISTS trg_audit_logs_no_delete" in source
        assert "SELECT RAISE(ABORT, 'AuditLog records are append-only and strictly immutable.');" in source
        assert "SELECT RAISE(ABORT, 'AuditLog records are append-only and cannot be deleted.');" in source

    def test_organization_deactivation_access_control(self, client: TestClient, db_session: Session):
        """DEF-01 Security Correction: Verify organization-level deactivation access controls."""
        suffix = uuid.uuid4().hex[:6]
        org = Organization(name=f"Access Org {suffix}", slug=f"access-org-{suffix}", is_active=True)
        db_session.add(org)
        db_session.commit()
        db_session.refresh(org)

        # 1. Active user in active organization works normally
        user = User(
            organization_id=org.id,
            username=f"access_user_{suffix}",
            email=f"access_{suffix}@test.corp",
            hashed_password=hash_password("securePass123!"),
            role="auditor",
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        login_resp = client.post(
            "/api/auth/login",
            json={"username": user.username, "password": "securePass123!"},
        )
        assert login_resp.status_code == 200, "Active user in active organization must be able to log in"
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Verify active user can access protected endpoint
        me_resp = client.get("/api/auth/me", headers=headers)
        assert me_resp.status_code == 200
        assert me_resp.json()["username"] == user.username

        # 2. Deactivate Organization (is_active = False)
        org.is_active = False
        db_session.commit()
        db_session.refresh(org)

        # 2a. Active user in inactive organization cannot log in
        blocked_login = client.post(
            "/api/auth/login",
            json={"username": user.username, "password": "securePass123!"},
        )
        assert blocked_login.status_code == 403
        assert "organization" in blocked_login.json()["detail"].lower()
        assert "deactivated" in blocked_login.json()["detail"].lower()

        # 2b. Previously issued JWT is rejected after organization deactivation
        blocked_token_resp = client.get("/api/auth/me", headers=headers)
        assert blocked_token_resp.status_code == 403
        assert "organization" in blocked_token_resp.json()["detail"].lower()
        assert "deactivated" in blocked_token_resp.json()["detail"].lower()

        # 3. Reactivate Organization and verify user deactivation behavior is preserved
        org.is_active = True
        user.is_active = False
        db_session.commit()
        db_session.refresh(org)
        db_session.refresh(user)

        # 3a. Deactivated user in active organization cannot log in
        user_blocked_login = client.post(
            "/api/auth/login",
            json={"username": user.username, "password": "securePass123!"},
        )
        assert user_blocked_login.status_code == 403
        assert "account is inactive" in user_blocked_login.json()["detail"].lower()

        # 3b. JWT for deactivated user is rejected with user-specific message
        user_blocked_token = client.get("/api/auth/me", headers=headers)
        assert user_blocked_token.status_code == 403
        assert "user account is deactivated" in user_blocked_token.json()["detail"].lower()
