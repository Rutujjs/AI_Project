"""Notification Management & Document Expiry Sweep Service for Member 5 (Phase 5F).

Provides:
- Independent per-user read tracking via NotificationRead association model.
- Concurrency-safe event deduplication via deterministic event_key.
- Multi-worker safe document expiry sweep with database-backed lock coordination.
- Lifecycle state transitions (ACTIVE -> RESOLVED / SUPERSEDED) for document renewals.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, desc, or_
from sqlalchemy.orm import Session

from app.platform.models import (
    Notification,
    NotificationRead,
    Organization,
    PlatformScheduleLock,
    Supplier,
    SupplierDocument,
    User,
)
from app.platform.schemas import NotificationResponse

logger = logging.getLogger(__name__)


def create_notification(
    db: Session,
    organization_id: int,
    category: str,
    severity: str,
    title: str,
    message: str,
    user_id: Optional[int] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    event_key: Optional[str] = None,
    link_url: Optional[str] = None,
    commit: bool = True,
) -> Notification:
    """Create a new platform notification with deterministic deduplication."""
    now = datetime.now(timezone.utc)

    # Concurrency-safe deduplication: skip if active alert with same event_key exists
    if event_key:
        existing = (
            db.query(Notification)
            .filter(
                Notification.organization_id == organization_id,
                Notification.event_key == event_key,
                Notification.status == "ACTIVE",
            )
            .first()
        )
        if existing:
            return existing

    notif = Notification(
        organization_id=organization_id,
        user_id=user_id,
        category=category.upper(),
        severity=severity.upper(),
        title=title,
        message=message,
        resource_type=resource_type.lower() if resource_type else None,
        resource_id=str(resource_id) if resource_id is not None else None,
        event_key=event_key,
        link_url=link_url,
        status="ACTIVE",
        created_at=now,
    )
    db.add(notif)

    if commit:
        try:
            db.commit()
            db.refresh(notif)
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create notification: {e}", exc_info=True)
            raise

    return notif


def get_user_notifications(
    db: Session,
    organization_id: int,
    user_id: int,
    unread_only: bool = False,
    category: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> Tuple[List[NotificationResponse], int, int]:
    """Retrieve notifications visible to the user with individual read receipts."""
    # Base query: visible to this organization AND (broadcast OR directed to this user)
    base_cond = and_(
        Notification.organization_id == organization_id,
        Notification.status == "ACTIVE",
        or_(Notification.user_id.is_(None), Notification.user_id == user_id),
    )

    if category:
        base_cond = and_(base_cond, Notification.category == category.upper())

    # Left join with NotificationRead to evaluate per-user read receipt
    query = (
        db.query(Notification, NotificationRead)
        .outerjoin(
            NotificationRead,
            and_(
                NotificationRead.notification_id == Notification.id,
                NotificationRead.user_id == user_id,
            ),
        )
        .filter(base_cond)
    )

    if unread_only:
        query = query.filter(NotificationRead.id.is_(None))

    total = query.count()

    # Calculate overall unread count for this user
    unread_count = (
        db.query(Notification)
        .outerjoin(
            NotificationRead,
            and_(
                NotificationRead.notification_id == Notification.id,
                NotificationRead.user_id == user_id,
            ),
        )
        .filter(
            Notification.organization_id == organization_id,
            Notification.status == "ACTIVE",
            or_(Notification.user_id.is_(None), Notification.user_id == user_id),
            NotificationRead.id.is_(None),
        )
        .count()
    )

    records = query.order_by(desc(Notification.created_at)).offset(offset).limit(limit).all()

    items = []
    for notif, read_receipt in records:
        is_read = read_receipt is not None
        read_at = read_receipt.read_at if read_receipt else None
        items.append(
            NotificationResponse(
                id=notif.id,
                organization_id=notif.organization_id,
                user_id=notif.user_id,
                category=notif.category,
                severity=notif.severity,
                title=notif.title,
                message=notif.message,
                resource_type=notif.resource_type,
                resource_id=notif.resource_id,
                link_url=notif.link_url,
                status=notif.status,
                is_read=is_read,
                read_at=read_at,
                created_at=notif.created_at,
            )
        )

    return items, total, unread_count


def get_unread_count(db: Session, organization_id: int, user_id: int) -> int:
    """Fast query for unread notifications count for header badge."""
    return (
        db.query(Notification)
        .outerjoin(
            NotificationRead,
            and_(
                NotificationRead.notification_id == Notification.id,
                NotificationRead.user_id == user_id,
            ),
        )
        .filter(
            Notification.organization_id == organization_id,
            Notification.status == "ACTIVE",
            or_(Notification.user_id.is_(None), Notification.user_id == user_id),
            NotificationRead.id.is_(None),
        )
        .count()
    )


def mark_notification_read(
    db: Session,
    organization_id: int,
    user_id: int,
    notification_id: int,
) -> Optional[NotificationResponse]:
    """Mark a visible notification as read for the requesting user."""
    notif = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.organization_id == organization_id,
            or_(Notification.user_id.is_(None), Notification.user_id == user_id),
        )
        .first()
    )
    if not notif:
        return None

    now = datetime.now(timezone.utc)
    read_receipt = (
        db.query(NotificationRead)
        .filter(
            NotificationRead.notification_id == notification_id,
            NotificationRead.user_id == user_id,
        )
        .first()
    )
    if not read_receipt:
        read_receipt = NotificationRead(
            notification_id=notification_id,
            user_id=user_id,
            read_at=now,
        )
        db.add(read_receipt)
        db.commit()

    return NotificationResponse(
        id=notif.id,
        organization_id=notif.organization_id,
        user_id=notif.user_id,
        category=notif.category,
        severity=notif.severity,
        title=notif.title,
        message=notif.message,
        resource_type=notif.resource_type,
        resource_id=notif.resource_id,
        link_url=notif.link_url,
        status=notif.status,
        is_read=True,
        read_at=read_receipt.read_at if read_receipt else now,
        created_at=notif.created_at,
    )


def mark_all_notifications_read(
    db: Session,
    organization_id: int,
    user_id: int,
) -> int:
    """Mark all visible unread notifications as read for the requesting user."""
    now = datetime.now(timezone.utc)

    # Find unread visible notifications
    unread_notifs = (
        db.query(Notification)
        .outerjoin(
            NotificationRead,
            and_(
                NotificationRead.notification_id == Notification.id,
                NotificationRead.user_id == user_id,
            ),
        )
        .filter(
            Notification.organization_id == organization_id,
            Notification.status == "ACTIVE",
            or_(Notification.user_id.is_(None), Notification.user_id == user_id),
            NotificationRead.id.is_(None),
        )
        .all()
    )

    count = 0
    for n in unread_notifs:
        receipt = NotificationRead(
            notification_id=n.id,
            user_id=user_id,
            read_at=now,
        )
        db.add(receipt)
        count += 1

    if count > 0:
        db.commit()

    return count


# ─── Scheduled Expiry Sweep with Multi-Worker Lock Coordination ───────────────

def _acquire_scheduler_lock(db: Session, task_name: str, org_id: int) -> bool:
    """Acquire a coordination lock to prevent duplicate sweeps in multi-worker environments."""
    now = datetime.now(timezone.utc)
    lease_until = now + timedelta(minutes=15)

    lock = (
        db.query(PlatformScheduleLock)
        .filter(
            PlatformScheduleLock.task_name == task_name,
            PlatformScheduleLock.organization_id == org_id,
        )
        .first()
    )

    if not lock:
        try:
            lock = PlatformScheduleLock(
                task_name=task_name,
                organization_id=org_id,
                locked_until=lease_until,
                last_run_at=now,
                last_status="RUNNING",
            )
            db.add(lock)
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False

    # Check if existing lock is active
    if lock.locked_until:
        locked_until = (
            lock.locked_until.replace(tzinfo=timezone.utc)
            if lock.locked_until.tzinfo is None
            else lock.locked_until
        )
        if locked_until > now:
            return False  # Locked by another active worker

    # Acquire expired or free lock
    lock.locked_until = lease_until
    lock.last_status = "RUNNING"
    db.commit()
    return True


def _release_scheduler_lock(db: Session, task_name: str, org_id: int, status: str = "SUCCESS") -> None:
    """Release coordination lock after task completion."""
    now = datetime.now(timezone.utc)
    lock = (
        db.query(PlatformScheduleLock)
        .filter(
            PlatformScheduleLock.task_name == task_name,
            PlatformScheduleLock.organization_id == org_id,
        )
        .first()
    )
    if lock:
        lock.locked_until = None
        lock.last_run_at = now
        lock.last_status = status
        db.commit()


def run_document_expiry_sweep(
    db: Session,
    target_org_id: Optional[int] = None,
    force: bool = False,
) -> Dict[str, int]:
    """Execute document expiry sweep across organizations with lifecycle state management."""
    now = datetime.now(timezone.utc)
    scanned = 0
    created = 0
    superseded = 0

    orgs = db.query(Organization).all() if target_org_id is None else db.query(Organization).filter(Organization.id == target_org_id).all()

    for org in orgs:
        if not force and not _acquire_scheduler_lock(db, "document_expiry_sweep", org.id):
            continue

        try:
            # Query all supplier documents for this organization
            suppliers = db.query(Supplier).filter(Supplier.organization_id == org.id).all()
            supplier_ids = [s.id for s in suppliers]
            if not supplier_ids:
                _release_scheduler_lock(db, "document_expiry_sweep", org.id, status="SUCCESS")
                continue

            supplier_map = {s.id: s for s in suppliers}
            docs = (
                db.query(SupplierDocument)
                .filter(SupplierDocument.supplier_id.in_(supplier_ids))
                .all()
            )

            for doc in docs:
                scanned += 1
                if not doc.expiry_date:
                    continue

                exp = doc.expiry_date.replace(tzinfo=timezone.utc) if doc.expiry_date.tzinfo is None else doc.expiry_date
                days = (exp - now).days
                sup = supplier_map.get(doc.supplier_id)
                sup_name = sup.name if sup else f"Supplier #{doc.supplier_id}"

                if days < 0:
                    # 1. Document is Expired
                    expired_key = f"doc:{doc.id}:EXPIRED"
                    # Supersede any prior EXPIRING_SOON warning
                    prior_warn = (
                        db.query(Notification)
                        .filter(
                            Notification.organization_id == org.id,
                            Notification.resource_type == "supplier_document",
                            Notification.resource_id == str(doc.id),
                            Notification.event_key == f"doc:{doc.id}:EXPIRING_SOON",
                            Notification.status == "ACTIVE",
                        )
                        .first()
                    )
                    if prior_warn:
                        prior_warn.status = "SUPERSEDED"
                        prior_warn.resolved_at = now
                        superseded += 1

                    # Check if EXPIRED alert already created
                    existing_exp = (
                        db.query(Notification)
                        .filter(
                            Notification.organization_id == org.id,
                            Notification.event_key == expired_key,
                            Notification.status == "ACTIVE",
                        )
                        .first()
                    )
                    if not existing_exp:
                        notif = Notification(
                            organization_id=org.id,
                            category="DOCUMENT_EXPIRY",
                            severity="CRITICAL",
                            title=f"Expired Compliance Evidence: {doc.title}",
                            message=f"Document '{doc.title}' ({doc.document_type}) for supplier '{sup_name}' expired on {exp.strftime('%Y-%m-%d')} ({-days} days overdue).",
                            resource_type="supplier_document",
                            resource_id=str(doc.id),
                            event_key=expired_key,
                            link_url="suppliers.html",
                            status="ACTIVE",
                            created_at=now,
                        )
                        db.add(notif)
                        created += 1

                elif 0 <= days <= 30:
                    # 2. Document is Expiring Soon (Warning)
                    warn_key = f"doc:{doc.id}:EXPIRING_SOON"
                    existing_warn = (
                        db.query(Notification)
                        .filter(
                            Notification.organization_id == org.id,
                            Notification.event_key == warn_key,
                            Notification.status == "ACTIVE",
                        )
                        .first()
                    )
                    if not existing_warn:
                        notif = Notification(
                            organization_id=org.id,
                            category="DOCUMENT_EXPIRY",
                            severity="WARNING",
                            title=f"Expiring Evidence: {doc.title}",
                            message=f"Document '{doc.title}' ({doc.document_type}) for supplier '{sup_name}' will expire in {days} days on {exp.strftime('%Y-%m-%d')}.",
                            resource_type="supplier_document",
                            resource_id=str(doc.id),
                            event_key=warn_key,
                            link_url="suppliers.html",
                            status="ACTIVE",
                            created_at=now,
                        )
                        db.add(notif)
                        created += 1

                else:
                    # 3. Document is Valid (> 30 days) - Auto-resolve any prior expiry alerts
                    active_alerts = (
                        db.query(Notification)
                        .filter(
                            Notification.organization_id == org.id,
                            Notification.resource_type == "supplier_document",
                            Notification.resource_id == str(doc.id),
                            Notification.status == "ACTIVE",
                        )
                        .all()
                    )
                    for alert in active_alerts:
                        alert.status = "RESOLVED"
                        alert.resolved_at = now
                        superseded += 1

            db.commit()
            _release_scheduler_lock(db, "document_expiry_sweep", org.id, status="SUCCESS")

        except Exception as e:
            db.rollback()
            _release_scheduler_lock(db, "document_expiry_sweep", org.id, status="FAILED")
            logger.error(f"Error during document expiry sweep for org {org.id}: {e}", exc_info=True)

    return {
        "scanned_documents": scanned,
        "created_notifications": created,
        "superseded_notifications": superseded,
    }


def resolve_notifications_for_supplier_doctype(
    db: Session,
    organization_id: int,
    supplier_id: int,
    document_type: str,
) -> int:
    """Auto-resolve active notifications for prior documents of the same type for a supplier upon renewal."""
    from app.platform.models import SupplierDocument

    doc_ids = [
        str(d.id)
        for d in db.query(SupplierDocument.id)
        .filter(SupplierDocument.supplier_id == supplier_id, SupplierDocument.document_type == document_type)
        .all()
    ]
    if not doc_ids:
        return 0

    now = datetime.now(timezone.utc)
    active_notifs = (
        db.query(Notification)
        .filter(
            Notification.organization_id == organization_id,
            Notification.category == "DOCUMENT_EXPIRY",
            Notification.resource_type == "supplier_document",
            Notification.resource_id.in_(doc_ids),
            Notification.status == "ACTIVE",
        )
        .all()
    )
    resolved = 0
    for n in active_notifs:
        n.status = "RESOLVED"
        n.resolved_at = now
        resolved += 1

    return resolved

