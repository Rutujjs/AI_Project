"""Tests for Member 5: Authentication, RBAC, and Organization Management (Phase 5A).

Comprehensive verification of:
1. JWT secret loading & production security guard
2. Token expiration enforcement
3. Server-side logout token revocation
4. Cryptographic password hashing & verification
5. RBAC role enforcement (Admin, Auditor, Developer, Viewer)
6. Cross-organization multi-tenant isolation
7. Inactive user rejection (login & token usage)
8. Case-insensitive duplicate username and email rejection
9. Member 1-4 existing endpoint accessibility
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
import sys
import uuid

# Ensure backend directory is on sys.path and dummy GEMINI_API_KEY exists for import
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
os.environ.setdefault("GEMINI_API_KEY", "test-key-for-auth-tests")

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.platform.config import get_secret_key
from app.platform.database import SessionLocal, init_db
from app.platform.models import Organization, User, UserRole
from app.platform.security import create_access_token, decode_access_token, hash_password, verify_password


@pytest.fixture(scope="module")
def client():
    """Return a TestClient against the main FastAPI application."""
    init_db()
    with TestClient(app) as c:
        yield c


class TestSecurityConfiguration:
    """Pre-Phase 5C Checks 8, 9, 10: Production JWT secret configuration validation."""

    def test_production_rejects_missing_jwt_secret(self, monkeypatch):
        """Case 8: Production mode fails safely if SECRET_KEY and JWT_SECRET are missing."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("SECRET_KEY", raising=False)
        monkeypatch.delenv("JWT_SECRET", raising=False)
        with pytest.raises(RuntimeError, match="CRITICAL SECURITY CONFIGURATION ERROR"):
            get_secret_key()

    def test_production_rejects_weak_jwt_secret(self, monkeypatch):
        """Case 9: Production mode rejects secrets shorter than 32 characters or default insecure secret."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("SECRET_KEY", "short-secret")
        with pytest.raises(RuntimeError, match="CRITICAL SECURITY CONFIGURATION ERROR"):
            get_secret_key()

        # Insecure default secret rejected in production
        monkeypatch.setenv("SECRET_KEY", "esg-platform-enterprise-secret-key-2026-secure")
        with pytest.raises(RuntimeError, match="CRITICAL SECURITY CONFIGURATION ERROR"):
            get_secret_key()

    def test_valid_production_configuration_accepted(self, monkeypatch):
        """Case 10: Production mode accepts high-entropy secret >= 32 characters."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        secure_key = "x" * 64
        monkeypatch.setenv("SECRET_KEY", secure_key)
        assert get_secret_key() == secure_key

    def test_password_hashing_and_verification(self):
        """Verify cryptographic password hashing and constant-time verification."""
        pwd = "EnterpriseSecurePassword!2026"
        hashed = hash_password(pwd)
        assert hashed.startswith("pbkdf2:sha256:100000$")
        assert verify_password(pwd, hashed) is True
        assert verify_password("WrongPassword", hashed) is False
        assert verify_password("", hashed) is False
        assert verify_password(pwd, "") is False


class TestJWTSecurityAndRevocation:
    """Pre-Phase 5C Checks 1-7: JWT jti uniqueness, expiration, and individual token revocation."""

    def test_newly_generated_jwt_contains_unique_jti(self, client: TestClient):
        """Case 1: Newly generated JWT contains a unique jti claim and preserves existing claims."""
        resp = client.post("/api/auth/login", json={"username": "admin", "password": "esg2026"})
        assert resp.status_code == 200
        token = resp.json()["access_token"]
        payload = decode_access_token(token)

        assert "jti" in payload
        assert isinstance(payload["jti"], str)
        assert len(payload["jti"]) >= 16

        # Verify existing standard claims are preserved
        assert payload["sub"] == "admin"
        assert payload["user_id"] == 1
        assert "org_id" in payload
        assert payload["role"] == "admin"
        assert "iat" in payload
        assert "exp" in payload

    def test_consecutive_tokens_for_same_user_have_different_jti(self, client: TestClient):
        """Case 2: Consecutive logins for the same user produce different jti values and distinct token strings."""
        resp1 = client.post("/api/auth/login", json={"username": "viewer", "password": "esg2026"})
        resp2 = client.post("/api/auth/login", json={"username": "viewer", "password": "esg2026"})
        assert resp1.status_code == 200 and resp2.status_code == 200

        t1, t2 = resp1.json()["access_token"], resp2.json()["access_token"]
        p1, p2 = decode_access_token(t1), decode_access_token(t2)

        assert t1 != t2, "Consecutive tokens must be distinct strings"
        assert p1["jti"] != p2["jti"], "Consecutive tokens must have distinct jti values"

    def test_tokens_generated_within_same_second_remain_unique(self):
        """Case 3: Two tokens generated in the exact same second are cryptographically unique."""
        data = {"sub": "developer", "user_id": 3, "role": "developer", "org_id": 1}
        t1 = create_access_token(data)
        t2 = create_access_token(data)
        assert t1 != t2, "Tokens issued in rapid succession must be unique"
        p1 = decode_access_token(t1)
        p2 = decode_access_token(t2)
        assert p1["jti"] != p2["jti"], "Each token must receive a unique jti"

    def test_individual_token_revocation_lifecycle(self, client: TestClient):
        """Cases 4, 5 & 6: Logging out revokes only Token A; fresh Token B works; Token A remains invalid."""
        # Step 1: Login and obtain Token A
        resp_a = client.post("/api/auth/login", json={"username": "developer", "password": "esg2026"})
        assert resp_a.status_code == 200
        token_a = resp_a.json()["access_token"]

        # Step 2: Verify Token A can access authenticated endpoint
        check_a = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_a}"})
        assert check_a.status_code == 200
        assert check_a.json()["username"] == "developer"

        # Step 3: Log out using Token A
        logout_resp = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token_a}"})
        assert logout_resp.status_code == 200

        # Step 4: Verify Token A is rejected with HTTP 401
        check_a_revoked = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_a}"})
        assert check_a_revoked.status_code == 401
        assert "revoked" in check_a_revoked.json()["detail"].lower()

        # Step 5: Log in again as the same user and obtain Token B
        resp_b = client.post("/api/auth/login", json={"username": "developer", "password": "esg2026"})
        assert resp_b.status_code == 200
        token_b = resp_b.json()["access_token"]

        # Step 6: Verify Token B is different from Token A
        assert token_b != token_a
        payload_a = decode_access_token(token_a)
        payload_b = decode_access_token(token_b)
        assert payload_a["jti"] != payload_b["jti"]

        # Step 7: Verify Token B can access authenticated endpoints successfully
        check_b = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_b}"})
        assert check_b.status_code == 200
        assert check_b.json()["username"] == "developer"

        # Step 8: Confirm that revoking Token A did not revoke Token B, and Token A remains invalid
        check_a_still_revoked = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_a}"})
        assert check_a_still_revoked.status_code == 401
        assert "revoked" in check_a_still_revoked.json()["detail"].lower()

    def test_token_expiration_enforcement(self, client: TestClient):
        """Case 7: Expired token rejected with 401 Unauthorized."""
        expired_token = create_access_token(
            data={"sub": "admin", "user_id": 1, "role": "admin"},
            expires_delta=timedelta(seconds=-10),
        )
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
        assert resp.status_code == 401
        assert "expired" in resp.json()["detail"].lower()


class TestAuthenticationAndTokens:
    """Checks 3 & 4: Expiration & server-side logout revocation."""

    def test_login_success_admin(self, client: TestClient):
        resp = client.post("/api/auth/login", json={"username": "admin", "password": "esg2026"})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["username"] == "admin"
        assert data["user"]["role"] == "admin"

    def test_login_all_four_roles(self, client: TestClient):
        roles = ["admin", "auditor", "developer", "viewer"]
        for role in roles:
            resp = client.post("/api/auth/login", json={"username": role, "password": "esg2026"})
            assert resp.status_code == 200
            assert resp.json()["user"]["role"] == role

    def test_login_invalid_password(self, client: TestClient):
        resp = client.post("/api/auth/login", json={"username": "admin", "password": "wrongpassword"})
        assert resp.status_code == 401
        assert "Incorrect username or password" in resp.json()["detail"]

    def test_login_nonexistent_user(self, client: TestClient):
        resp = client.post("/api/auth/login", json={"username": "nonexistent_user", "password": "password"})
        assert resp.status_code == 401


class TestRBACAndDeactivation:
    """Checks 6 & 8: Role enforcement & deactivated accounts."""

    def test_admin_can_list_organization_users(self, client: TestClient):
        login_resp = client.post("/api/auth/login", json={"username": "admin", "password": "esg2026"})
        token = login_resp.json()["access_token"]

        resp = client.get("/api/auth/users", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        users = resp.json()
        assert len(users) >= 4

    def test_non_admin_roles_forbidden_from_listing_users(self, client: TestClient):
        for role in ["auditor", "developer", "viewer"]:
            login_resp = client.post("/api/auth/login", json={"username": role, "password": "esg2026"})
            token = login_resp.json()["access_token"]
            resp = client.get("/api/auth/users", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 403
            assert "Access forbidden" in resp.json()["detail"]

    def test_inactive_user_cannot_authenticate_or_access(self, client: TestClient):
        """Check 8: Inactive users cannot authenticate or access endpoints."""
        db = SessionLocal()
        try:
            temp_user = User(
                organization_id=1,
                username=f"inactive_{uuid.uuid4().hex[:6]}",
                email=f"inactive_{uuid.uuid4().hex[:6]}@test.com",
                full_name="Deactivated User",
                role="viewer",
                hashed_password=hash_password("password123"),
                is_active=False,
            )
            db.add(temp_user)
            db.commit()
            db.refresh(temp_user)
            inactive_name = temp_user.username
            inactive_id = temp_user.id
        finally:
            db.close()

        # 1. Login attempt must fail
        login_resp = client.post("/api/auth/login", json={"username": inactive_name, "password": "password123"})
        assert login_resp.status_code == 403
        assert "inactive" in login_resp.json()["detail"].lower()

        # 2. Existing token for deactivated user must fail
        token = create_access_token(data={"sub": inactive_name, "user_id": inactive_id, "role": "viewer"})
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403
        assert "deactivated" in resp.json()["detail"].lower()


class TestMultiTenancyAndDuplicates:
    """Checks 7 & 9: Cross-organization isolation & duplicate handling."""

    def test_cross_organization_data_isolation(self, client: TestClient):
        """Check 7: Users cannot see or modify other organizations' data."""
        db = SessionLocal()
        try:
            # Create a second tenant organization
            org2 = Organization(
                name="Beta Renewable Industries",
                slug=f"beta-renewables-{uuid.uuid4().hex[:6]}",
                industry="Clean Energy",
                reporting_period="FY 2025–26",
            )
            db.add(org2)
            db.commit()
            db.refresh(org2)

            user_org2 = User(
                organization_id=org2.id,
                username=f"admin_beta_{uuid.uuid4().hex[:6]}",
                email=f"admin_beta_{uuid.uuid4().hex[:6]}@beta.com",
                full_name="Beta Admin",
                role="admin",
                hashed_password=hash_password("esg2026"),
                is_active=True,
            )
            db.add(user_org2)
            db.commit()
            db.refresh(user_org2)
            beta_username = user_org2.username
            beta_org_id = org2.id
        finally:
            db.close()

        # Login as Beta Admin
        login_beta = client.post("/api/auth/login", json={"username": beta_username, "password": "esg2026"})
        token_beta = login_beta.json()["access_token"]

        # 1. Beta Admin listing users must ONLY see users from Org 2
        users_resp = client.get("/api/auth/users", headers={"Authorization": f"Bearer {token_beta}"})
        assert users_resp.status_code == 200
        org2_users = users_resp.json()
        for u in org2_users:
            assert u["organization_id"] == beta_org_id
            assert u["username"] != "admin"  # Cannot see Acme Corp admin

        # 2. Beta Admin gets current organization -> returns Beta Renewables, not Acme
        org_resp = client.get("/api/platform/organizations/current", headers={"Authorization": f"Bearer {token_beta}"})
        assert org_resp.status_code == 200
        assert org_resp.json()["id"] == beta_org_id
        assert org_resp.json()["name"] == "Beta Renewable Industries"

    def test_case_insensitive_duplicate_handling(self, client: TestClient):
        """Check 9: Duplicate usernames and emails rejected case-insensitively."""
        login_resp = client.post("/api/auth/login", json={"username": "admin", "password": "esg2026"})
        token = login_resp.json()["access_token"]

        # Attempt to create duplicate with different casing: "ADMIN" or "Admin@Esg-Intelligence.Local"
        resp1 = client.post(
            "/api/auth/users",
            json={
                "username": "ADMIN",
                "email": "unique_email_123@acme.com",
                "password": "password123",
                "role": "viewer",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp1.status_code == 400
        assert "already taken" in resp1.json()["detail"].lower()

        resp2 = client.post(
            "/api/auth/users",
            json={
                "username": f"unique_user_{uuid.uuid4().hex[:6]}",
                "email": "ADMIN@ESG-INTELLIGENCE.LOCAL",
                "password": "password123",
                "role": "viewer",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp2.status_code == 400
        assert "already registered" in resp2.json()["detail"].lower()


class TestMember1To4IntegrationIntegrity:
    """Check 10: Existing Member 1-4 APIs remain mounted and functional."""

    def test_member_1_document_health(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_member_3_green_software_health(self, client: TestClient):
        resp = client.get("/green/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"
        assert resp.json()["module"] == "green_software"

    def test_member_4_cloud_carbon_health(self, client: TestClient):
        resp = client.get("/api/cloud-carbon/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"
        assert resp.json()["module"] == "cloud_carbon"

    def test_member_5_platform_health(self, client: TestClient):
        resp = client.get("/api/platform/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"
        assert resp.json()["module"] == "platform_engineering"
