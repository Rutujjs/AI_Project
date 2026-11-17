"""FastAPI router for Member 5: Enterprise ESG Reporting & PDF Export.

Prefix: /api/platform/reports
Tags:   Enterprise ESG Reporting

Enforces:
- Strict Role-Based Access Control (RBAC: Admin, Auditor, Developer, Viewer).
- Multi-tenant isolation (Tenant derived strictly from authenticated user).
- Aggregation across all Member 1–5 subsystems with failure resilience.
- Pure in-memory PDF generation streaming with professional Platypus formatting.
"""

from __future__ import annotations

import io
import re
from typing import List

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.platform.database import get_db
from app.platform.dependencies import require_roles
from app.platform.models import User, UserRole
from app.platform.schemas import (
    ReportDataResponse,
    ReportGenerateRequest,
    ReportTypeDefinition,
)
from app.platform.services.report_service import (
    build_report_pdf,
    compile_report_data,
    get_available_report_types,
)
from app.platform.services.audit_service import record_audit_event

router = APIRouter(prefix="/api/platform/reports", tags=["Enterprise ESG Reporting"])


@router.get("/types", response_model=List[ReportTypeDefinition])
async def list_report_types(
    current_user: User = Depends(
        require_roles(UserRole.ADMIN, UserRole.AUDITOR, UserRole.DEVELOPER, UserRole.VIEWER)
    ),
):
    """List available report templates, metadata, default sections, and supported filters."""
    return get_available_report_types()


@router.post("/preview", response_model=ReportDataResponse)
async def preview_report(
    req: ReportGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.ADMIN, UserRole.AUDITOR, UserRole.DEVELOPER, UserRole.VIEWER)
    ),
):
    """Generate structured JSON report data for UI preview and data validation."""
    data = await compile_report_data(
        db=db,
        org_id=current_user.organization_id,
        user=current_user,
        req=req,
    )
    raw_type = req.report_type.value if hasattr(req.report_type, "value") else str(req.report_type)
    record_audit_event(
        db,
        action="REPORT_PREVIEWED",
        resource_type="REPORT",
        resource_id=None,
        user=current_user,
        status="SUCCESS",
        details={"report_type": raw_type, "reporting_period": req.reporting_period},
        commit=True,
    )
    return data


@router.post("/export-pdf")
async def export_report_pdf(
    req: ReportGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.ADMIN, UserRole.AUDITOR, UserRole.DEVELOPER, UserRole.VIEWER)
    ),
):
    """Compile and stream executive multi-page PDF document generated in-memory."""
    if req.report_data:
        try:
            report_data = ReportDataResponse(**req.report_data)
        except Exception:
            report_data = await compile_report_data(
                db=db,
                org_id=current_user.organization_id,
                user=current_user,
                req=req,
            )
    else:
        report_data = await compile_report_data(
            db=db,
            org_id=current_user.organization_id,
            user=current_user,
            req=req,
        )

    pdf_bytes = build_report_pdf(report_data)

    # Sanitize filename components
    raw_type = report_data.report_type.value if hasattr(report_data.report_type, "value") else str(report_data.report_type)
    clean_type = raw_type.lower().replace("_", "-")
    clean_org = re.sub(r"[^a-zA-Z0-9_\-]", "_", report_data.organization_name).strip("_") or "tenant"
    clean_date = report_data.generated_at.strftime("%Y%m%d_%H%M%S")
    filename = f"{clean_type}_{clean_org}_{clean_date}.pdf"

    record_audit_event(
        db,
        action="REPORT_EXPORTED_PDF",
        resource_type="REPORT",
        resource_id=None,
        user=current_user,
        status="SUCCESS",
        details={"report_type": raw_type, "filename": filename, "file_size": len(pdf_bytes)},
        commit=True,
    )

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )
