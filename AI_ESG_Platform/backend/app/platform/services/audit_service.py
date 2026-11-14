"""Centralized Audit Logging Service for Member 5 (Phase 5F).

Provides:
- Append-only audit record creation with atomic or isolated commits.
- Strict data sanitization (strips credentials, tokens, secrets, binary payloads).
- Multi-tenant isolated audit log querying for authorized auditors and admins.
- Full evidentiary snapshot of actor identity (retained even after user deactivation).
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.platform.models import AuditLog, User
from app.platform.schemas import AuditLogResponse

logger = logging.getLogger(__name__)

# Keys strictly stripped from audit details to prevent credential/data leakage
SENSITIVE_KEYS = {
    "password",
    "hashed_password",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "secret_key",
    "api_key",
    "authorization",
    "cookie",
    "file_content",
    "content",
    "raw_bytes",
}


def sanitize_details(data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Recursively sanitize metadata dict, removing secrets and non-serializable objects."""
    if not data:
        return None
    cleaned = {}
    for k, v in data.items():
        lk = k.lower()
        if (
            lk in SENSITIVE_KEYS
            or "password" in lk
            or "secret" in lk
            or "token" in lk
            or "api_key" in lk
        ):
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            cleaned[k] = v
        elif isinstance(v, datetime):
            cleaned[k] = v.isoformat()
        elif isinstance(v, dict):
            cleaned[k] = sanitize_details(v)
        elif isinstance(v, (list, tuple, set)):
            cleaned[k] = [
                x if isinstance(x, (str, int, float, bool)) or x is None
                else (x.isoformat() if isinstance(x, datetime) else str(x))
                for x in v
            ]
        else:
            cleaned[k] = str(v)
    return cleaned


def record_audit_event(
    db: Session,
    action: str,
    resource_type: str,
    organization_id: Optional[int] = None,
    user: Optional[User] = None,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    user_role: Optional[str] = None,
    resource_id: Optional[str] = None,
    status: str = "SUCCESS",
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    commit: bool = True,
) -> AuditLog:
    """Record an immutable audit event in the platform database.
    
    If commit=False, adds AuditLog to the active session without committing,
    allowing caller to commit business entity mutations and audit log atomically.
    """
    # 1. Resolve Actor Information
    if user:
        resolved_user_id = user.id
        resolved_username = user.username or user.email
        resolved_role = user.role.upper() if user.role else "UNKNOWN"
        resolved_org_id = user.organization_id if organization_id is None else organization_id
    else:
        resolved_user_id = user_id
        resolved_username = (username or "anonymous").strip()[:100]
        resolved_role = user_role.upper() if user_role else None
        resolved_org_id = organization_id

    # 2. Sanitize and Serialize Metadata
    cleaned_details = sanitize_details(details)
    details_json = json.dumps(cleaned_details) if cleaned_details else None

    # 3. Create AuditLog Record
    entry = AuditLog(
        organization_id=resolved_org_id,
        user_id=resolved_user_id,
        username=resolved_username,
        user_role=resolved_role,
        action=action.upper(),
        resource_type=resource_type.lower(),
        resource_id=str(resource_id) if resource_id is not None else None,
        status=status.upper(),
        details=details_json,
        ip_address=ip_address,
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)

    if commit:
        try:
            db.commit()
            db.refresh(entry)
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to write audit log entry: {e}", exc_info=True)
            raise

    return entry


def query_audit_logs(
    db: Session,
    organization_id: int,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    user_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[AuditLogResponse], int]:
    """Query audit logs strictly scoped to the tenant organization boundary."""
    query = db.query(AuditLog).filter(AuditLog.organization_id == organization_id)

    if action:
        query = query.filter(AuditLog.action == action.upper())
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type.lower())
    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    if start_date:
        query = query.filter(AuditLog.created_at >= start_date)
    if end_date:
        query = query.filter(AuditLog.created_at <= end_date)

    total = query.count()
    records = query.order_by(desc(AuditLog.created_at)).offset(offset).limit(limit).all()

    items = []
    for r in records:
        parsed_details = None
        if r.details:
            try:
                parsed_details = json.loads(r.details)
            except Exception:
                parsed_details = {"raw": r.details}

        items.append(
            AuditLogResponse(
                id=r.id,
                organization_id=r.organization_id,
                user_id=r.user_id,
                username=r.username,
                user_role=r.user_role,
                action=r.action,
                resource_type=r.resource_type,
                resource_id=r.resource_id,
                status=r.status,
                details=parsed_details,
                ip_address=r.ip_address,
                created_at=r.created_at,
            )
        )

    return items, total
