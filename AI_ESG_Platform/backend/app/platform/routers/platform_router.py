"""Organization & Tenant Management Router for Member 5."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.platform.database import get_db
from app.platform.dependencies import get_current_organization, get_current_user, require_roles
from app.platform.models import Organization, User, UserRole
from app.platform.schemas import (
    BaselinePolicyResponse,
    OrganizationResponse,
    OrganizationUpdateRequest,
)
from app.platform.services import supplier_service
from app.platform.services.audit_service import record_audit_event

router = APIRouter(prefix="/api/platform", tags=["Platform & Multi-Tenancy"])


@router.get("/health")
def platform_health():
    """Health check endpoint for Member 5 Platform Services."""
    return {
        "status": "healthy",
        "module": "platform_engineering",
        "phase": "5C (Supplier Risk Evaluation & Member 2 Integration)",
        "version": "1.0.0",
    }


@router.get("/organizations/current", response_model=OrganizationResponse)
def get_current_tenant_organization(
    org: Organization = Depends(get_current_organization),
):
    """Retrieve metadata and settings for the authenticated user's organization."""
    return OrganizationResponse.model_validate(org)


@router.put("/organizations/current", response_model=OrganizationResponse)
def update_current_tenant_organization(
    payload: OrganizationUpdateRequest,
    current_user: User = Depends(require_roles(UserRole.ADMIN.value)),
    org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
):
    """Update settings for the current tenant organization (Admin only)."""
    if payload.name is not None and payload.name.strip():
        org.name = payload.name.strip()
    if payload.industry is not None:
        org.industry = payload.industry.strip()
    if payload.reporting_period is not None:
        org.reporting_period = payload.reporting_period.strip()

    record_audit_event(
        db,
        action="ORGANIZATION_UPDATED",
        resource_type="ORGANIZATION",
        resource_id=org.id,
        user=current_user,
        organization_id=org.id,
        status="SUCCESS",
        details={
            "name": org.name,
            "industry": org.industry,
            "reporting_period": org.reporting_period,
        },
        commit=False,
    )

    db.commit()
    db.refresh(org)
    return OrganizationResponse.model_validate(org)


# ─── Enterprise Baseline Policy Endpoints ─────────────────────────────────────

@router.get(
    "/organizations/current/baseline-policy",
    response_model=BaselinePolicyResponse,
    summary="Get enterprise baseline policy status for current tenant",
)
def get_baseline_policy(
    org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
):
    """Check if the enterprise baseline policy is configured and retrieve its metadata."""
    meta = supplier_service.get_organization_baseline_policy(db, org.id)
    return BaselinePolicyResponse(**meta)


@router.post(
    "/organizations/current/baseline-policy",
    response_model=BaselinePolicyResponse,
    summary="Upload enterprise baseline policy for current tenant",
    dependencies=[Depends(require_roles(UserRole.ADMIN.value, UserRole.AUDITOR.value))],
)
async def upload_baseline_policy(
    file: UploadFile = File(..., description="Enterprise baseline policy document (PDF, DOCX)"),
    current_user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: Session = Depends(get_db),
):
    """Upload enterprise baseline policy PDF or document to benchmark all supplier policies."""
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded policy file is empty.",
        )

    updated_org = supplier_service.set_organization_baseline_policy(
        db=db,
        org_id=org.id,
        file_bytes=content,
        filename=file.filename or "enterprise_baseline_policy.pdf",
        user=current_user,
    )

    meta = supplier_service.get_organization_baseline_policy(db, updated_org.id)
    return BaselinePolicyResponse(**meta)
