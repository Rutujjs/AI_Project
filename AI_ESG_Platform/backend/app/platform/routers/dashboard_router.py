"""FastAPI router for Member 5: Unified Enterprise ESG Dashboard Aggregation.

Prefix: /api/platform/dashboard
Tags:   Enterprise Dashboard

Enforces:
- Strict Role-Based Access Control (RBAC: Admin, Auditor, Developer, Viewer).
- Multi-tenant isolation (Tenant derived strictly from authenticated user).
- Aggregation across all Member 1–5 subsystems with failure resilience.
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.platform.database import get_db
from app.platform.dependencies import require_roles
from app.platform.models import User, UserRole
from app.platform.schemas import UnifiedDashboardResponse
from app.platform.services.dashboard_service import aggregate_dashboard_metrics

router = APIRouter(prefix="/api/platform/dashboard", tags=["Enterprise Dashboard"])


@router.get("", response_model=UnifiedDashboardResponse)
async def get_enterprise_dashboard(
    category: Optional[str] = Query(None, description="Filter by ESG category (Environmental, Social, Governance)"),
    reporting_period: Optional[str] = Query(None, description="Filter reporting period (e.g., FY 2025–26)"),
    cloud_upload_id: Optional[str] = Query(None, description="Optional active Cloud & Carbon upload session ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.ADMIN, UserRole.AUDITOR, UserRole.DEVELOPER, UserRole.VIEWER)
    ),
):
    """Retrieve unified enterprise ESG dashboard aggregating metrics across Members 1–5."""
    return await aggregate_dashboard_metrics(
        db=db,
        org_id=current_user.organization_id,
        category=category,
        reporting_period=reporting_period,
        cloud_upload_id=cloud_upload_id,
    )
