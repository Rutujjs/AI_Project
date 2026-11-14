"""SQLAlchemy models for Member 5: Platform Engineering & Multi-Tenancy.

Defines schemas for:
- Organization (Tenant)
- User (RBAC: Admin, Auditor, Developer, Viewer)
"""

from __future__ import annotations

from datetime import datetime, timezone
import enum
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    AUDITOR = "auditor"
    DEVELOPER = "developer"
    VIEWER = "viewer"


class Organization(Base):
    """Tenant organization entity."""

    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False, index=True)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    industry = Column(String(150), nullable=True, default="Logistics & Transportation")
    reporting_period = Column(String(50), nullable=True, default="FY 2025–26")
    is_active = Column(Boolean, default=True, nullable=False)
    baseline_policy_path = Column(String(500), nullable=True)
    baseline_policy_name = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    suppliers = relationship("Supplier", back_populates="organization", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Organization(id={self.id}, name='{self.name}', slug='{self.slug}')>"


class User(Base):
    """User account entity with Role-Based Access Control (RBAC)."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    role = Column(
        String(50),
        default=UserRole.VIEWER.value,
        nullable=False,
        index=True,
    )
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    organization = relationship("Organization", back_populates="users")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"


class RevokedToken(Base):
    """Stores invalidated tokens for server-side logout enforcement."""

    __tablename__ = "revoked_tokens"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self) -> str:
        return f"<RevokedToken(id={self.id}, user_id={self.user_id}, expires_at={self.expires_at})>"


# ─── Member 5B: Supplier Management Models ────────────────────────────────────


class Supplier(Base):
    """Supplier profile entity under multi-tenant isolation."""

    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(255), nullable=False, index=True)
    code = Column(String(50), nullable=False, index=True)
    category = Column(String(100), nullable=False, default="Manufacturing")
    tier = Column(String(20), nullable=False, default="Tier 1")
    country = Column(String(100), nullable=False, default="Germany")
    contact_person = Column(String(255), nullable=True)
    contact_email = Column(String(255), nullable=False)
    contact_phone = Column(String(50), nullable=True)
    status = Column(String(50), nullable=False, default="Active")

    # ESG & ISO 31000 Risk Scores
    risk_score = Column(Float, nullable=True, default=None)
    risk_level = Column(String(50), nullable=False, default="NOT_ASSESSED")
    environmental_score = Column(Float, nullable=False, default=80.0)
    social_score = Column(Float, nullable=False, default=80.0)
    governance_score = Column(Float, nullable=False, default=80.0)
    overall_score = Column(Float, nullable=False, default=80.0)
    last_assessment_date = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    organization = relationship("Organization", back_populates="suppliers")
    documents = relationship("SupplierDocument", back_populates="supplier", cascade="all, delete-orphan")
    findings = relationship("SupplierFinding", back_populates="supplier", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Supplier(id={self.id}, name='{self.name}', code='{self.code}', risk='{self.risk_level}')>"


class SupplierDocument(Base):
    """Supplier compliance documents, certifications, and audits."""

    __tablename__ = "supplier_documents"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    supplier_id = Column(
        Integer,
        ForeignKey("suppliers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_type = Column(String(100), nullable=False)
    document_category = Column(String(50), nullable=False, default="CERTIFICATE")
    title = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=False, default=0)
    mime_type = Column(String(100), nullable=False, default="application/pdf")
    issue_date = Column(DateTime, nullable=True)
    expiry_date = Column(DateTime, nullable=True, index=True)
    verification_status = Column(String(50), nullable=False, default="Verified")
    notes = Column(Text, nullable=True)
    uploaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    supplier = relationship("Supplier", back_populates="documents")

    def __repr__(self) -> str:
        return f"<SupplierDocument(id={self.id}, supplier_id={self.supplier_id}, title='{self.title}')>"


class SupplierFinding(Base):
    """Supplier compliance findings, risk observations, and recommendations."""

    __tablename__ = "supplier_findings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    supplier_id = Column(
        Integer,
        ForeignKey("suppliers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(255), nullable=False)
    category = Column(String(50), nullable=False, default="Governance")
    severity = Column(String(50), nullable=False, default="Medium")
    likelihood = Column(Integer, nullable=False, default=3)
    impact = Column(Integer, nullable=False, default=3)
    risk_score = Column(Float, nullable=False, default=36.0)
    description = Column(Text, nullable=False)
    recommendation = Column(Text, nullable=False)
    status = Column(String(50), nullable=False, default="Open")
    identified_date = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    resolved_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    supplier = relationship("Supplier", back_populates="findings")

    def __repr__(self) -> str:
        return f"<SupplierFinding(id={self.id}, supplier_id={self.supplier_id}, title='{self.title}')>"


# ─── Phase 5F: Audit Logging & Notification Models ───────────────────────────

class AuditLog(Base):
    """Immutable audit trail for security, governance, and compliance events."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=True,  # Nullable for unauthenticated/unknown user failed logins
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    username = Column(String(100), nullable=False)
    user_role = Column(String(50), nullable=True)
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(50), nullable=False, index=True)
    resource_id = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, default="SUCCESS")
    details = Column(Text, nullable=True)  # JSON-encoded metadata
    ip_address = Column(String(50), nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    __table_args__ = (
        Index("ix_audit_logs_org_created", "organization_id", "created_at"),
        Index("ix_audit_logs_org_action", "organization_id", "action"),
        Index("ix_audit_logs_org_resource", "organization_id", "resource_type", "resource_id"),
    )

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action='{self.action}', user='{self.username}', status='{self.status}')>"


# Model-level append-only immutability enforcement
@event.listens_for(AuditLog, "before_update")
def _audit_log_prevent_update(mapper, connection, target):
    raise RuntimeError("AuditLog records are append-only and strictly immutable.")


@event.listens_for(AuditLog, "before_delete")
def _audit_log_prevent_delete(mapper, connection, target):
    raise RuntimeError("AuditLog records are append-only and cannot be deleted.")


class Notification(Base):
    """Platform alerts, compliance warnings, and event notifications."""

    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,  # NULL = organization-wide broadcast; int = user-specific
        index=True,
    )
    category = Column(String(50), nullable=False)  # DOCUMENT_EXPIRY, SUPPLIER_RISK, POLICY, SYSTEM
    severity = Column(String(20), nullable=False)  # CRITICAL, WARNING, INFO, SUCCESS
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(String(100), nullable=True)
    event_key = Column(String(150), nullable=True, index=True)  # Deduplication key
    link_url = Column(String(255), nullable=True)
    status = Column(String(50), nullable=False, default="ACTIVE")  # ACTIVE, RESOLVED, SUPERSEDED
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    resolved_at = Column(DateTime, nullable=True)

    reads = relationship("NotificationRead", back_populates="notification", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_notifications_org_created", "organization_id", "created_at"),
        Index("ix_notifications_dedup", "organization_id", "event_key"),
    )

    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, cat='{self.category}', sev='{self.severity}', title='{self.title}')>"


class NotificationRead(Base):
    """Per-user read receipt association for tenant and direct notifications."""

    __tablename__ = "notification_reads"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    notification_id = Column(
        Integer,
        ForeignKey("notifications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    read_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    notification = relationship("Notification", back_populates="reads")

    __table_args__ = (
        UniqueConstraint("notification_id", "user_id", name="uq_notification_user_read"),
        Index("ix_notification_reads_user", "user_id", "notification_id"),
    )

    def __repr__(self) -> str:
        return f"<NotificationRead(id={self.id}, notif_id={self.notification_id}, user_id={self.user_id})>"


class PlatformScheduleLock(Base):
    """Distributed coordination lock for background tasks across multiple workers."""

    __tablename__ = "platform_schedule_locks"

    task_name = Column(String(100), primary_key=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    locked_until = Column(DateTime, nullable=True)
    last_run_at = Column(DateTime, nullable=True)
    last_status = Column(String(50), nullable=True, default="SUCCESS")

    def __repr__(self) -> str:
        return f"<PlatformScheduleLock(task='{self.task_name}', org_id={self.organization_id})>"




