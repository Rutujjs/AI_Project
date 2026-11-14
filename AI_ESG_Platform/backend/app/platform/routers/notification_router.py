"""FastAPI Router for Member 5: Platform Notification Management (Phase 5F).

Prefix: /api/platform/notifications
Tags:   Platform Notifications

Enforces:
- Independent per-user read receipts via NotificationRead association.
- Multi-tenant boundary derived strictly from authenticated user.
- All four roles (Admin, Auditor, Developer, Viewer) authorized for notification feed.
- Multi-worker safe document expiry sweeps.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.platform.database import get_db
from app.platform.dependencies import require_roles
from app.platform.models import User, UserRole
from app.platform.schemas import (
    ExpiryCheckResponse,
    MarkAllReadResponse,
    NotificationListResponse,
    NotificationResponse,
    UnreadCountResponse,
)
from app.platform.services.notification_service import (
    get_unread_count,
    get_user_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    run_document_expiry_sweep,
)

router = APIRouter(prefix="/api/platform/notifications", tags=["Platform Notifications"])


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    unread_only: bool = Query(False, description="Filter for unread alerts only"),
    category: Optional[str] = Query(None, description="Filter by category (e.g. DOCUMENT_EXPIRY, SUPPLIER_RISK)"),
    limit: int = Query(20, ge=1, le=100, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.ADMIN, UserRole.AUDITOR, UserRole.DEVELOPER, UserRole.VIEWER)
    ),
):
    """Retrieve notifications visible to the authenticated user with independent read state."""
    items, total, unread_count = get_user_notifications(
        db=db,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        unread_only=unread_only,
        category=category,
        limit=limit,
        offset=offset,
    )
    return NotificationListResponse(
        items=items,
        total=total,
        unread_count=unread_count,
        limit=limit,
        offset=offset,
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
def get_user_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.ADMIN, UserRole.AUDITOR, UserRole.DEVELOPER, UserRole.VIEWER)
    ),
):
    """Fast query for unread notifications count for header badge."""
    count = get_unread_count(
        db=db,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
    )
    return UnreadCountResponse(unread_count=count)


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
def mark_single_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.ADMIN, UserRole.AUDITOR, UserRole.DEVELOPER, UserRole.VIEWER)
    ),
):
    """Mark a notification as read for the current user."""
    notif = mark_notification_read(
        db=db,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        notification_id=notification_id,
    )
    if not notif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found or access denied.",
        )
    return notif


@router.post("/mark-all-read", response_model=MarkAllReadResponse)
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.ADMIN, UserRole.AUDITOR, UserRole.DEVELOPER, UserRole.VIEWER)
    ),
):
    """Mark all unread visible notifications as read for the current user."""
    count = mark_all_notifications_read(
        db=db,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
    )
    return MarkAllReadResponse(marked_read=count)


@router.post("/check-expiries", response_model=ExpiryCheckResponse)
def trigger_expiry_sweep(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.ADMIN, UserRole.AUDITOR)
    ),
):
    """Manually trigger document expiry sweep for the current tenant."""
    results = run_document_expiry_sweep(
        db=db,
        target_org_id=current_user.organization_id,
        force=True,
    )
    return ExpiryCheckResponse(**results)

