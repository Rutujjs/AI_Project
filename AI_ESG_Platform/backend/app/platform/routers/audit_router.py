"""FastAPI Router for Member 5: Platform Audit Logging (Phase 5F).

Prefix: /api/platform/audit-logs
Tags:   Platform Governance & Audit

Enforces:
- Strict Role-Based Access Control (RBAC: Admin and Auditor only; Viewer & Developer forbidden).
- Strict multi-tenant isolation (Tenant derived strictly from authenticated user).
- Append-only immutability (No create, update, or delete endpoints).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.platform.database import get_db
from app.platform.dependencies import require_roles
from app.platform.models import User, UserRole
from app.platform.schemas import AuditLogListResponse
from app.platform.services.audit_service import query_audit_logs

router = APIRouter(prefix="/api/platform/audit-logs", tags=["Platform Governance & Audit"])


@router.get("", response_model=AuditLogListResponse)
def list_audit_logs(
    action: Optional[str] = Query(None, description="Filter by event action (e.g. SUPPLIER_CREATED, LOGIN_SUCCESS)"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type (e.g. supplier, document, auth)"),
    user_id: Optional[int] = Query(None, description="Filter by actor user ID"),
    start_date: Optional[datetime] = Query(None, description="Filter logs starting from UTC timestamp"),
    end_date: Optional[datetime] = Query(None, description="Filter logs up to UTC timestamp"),
    limit: int = Query(50, ge=1, le=200, description="Page limit (max 200)"),
    offset: int = Query(0, ge=0, description="Page offset"),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.ADMIN, UserRole.AUDITOR)
    ),
):
    """Retrieve immutable audit log history strictly scoped to the tenant organization."""
    items, total = query_audit_logs(
        db=db,
        organization_id=current_user.organization_id,
        action=action,
        resource_type=resource_type,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
    return AuditLogListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )

