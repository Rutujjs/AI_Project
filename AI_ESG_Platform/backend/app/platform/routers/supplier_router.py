"""FastAPI Router for Member 5: Supplier Management & Intelligence.

Endpoints:
- GET    /api/suppliers             - List suppliers with filtering & pagination
- GET    /api/suppliers/stats       - KPI summary statistics
- POST   /api/suppliers             - Create new supplier (Admin, Auditor)
- GET    /api/suppliers/{id}        - Supplier profile with documents & findings
- PUT    /api/suppliers/{id}        - Update supplier details (Admin, Auditor)
- DELETE /api/suppliers/{id}        - Delete supplier with safeguard (Admin only)
- POST   /api/suppliers/{id}/documents - Upload compliance certificate / document
- GET    /api/suppliers/{id}/documents - List supplier documents
- GET    /api/suppliers/{id}/documents/{doc_id}/download - Download document file
- GET    /api/suppliers/{id}/findings  - List supplier findings
- POST   /api/suppliers/{id}/findings  - Create compliance finding (Admin, Auditor)
- POST   /api/suppliers/{id}/evaluate  - Recalculate ISO 31000 risk / policy comparison (Admin, Auditor)
"""

from __future__ import annotations

from datetime import datetime
import math
from pathlib import Path
from typing import List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.platform.database import get_db
from app.platform.dependencies import get_current_user, require_roles
from app.platform.models import Organization, User, UserRole
from app.platform.schemas import (
    EvaluateRiskResponse,
    SupplierCreateRequest,
    SupplierDetailResponse,
    SupplierDocumentResponse,
    SupplierFindingCreate,
    SupplierFindingResponse,
    SupplierListResponse,
    SupplierResponse,
    SupplierStatsResponse,
    SupplierUpdateRequest,
)
from app.platform.services import supplier_service
from app.platform.services.audit_service import record_audit_event

router = APIRouter(prefix="/api/suppliers", tags=["Supplier Management"])


# ─── Statistics & Metrics ──────────────────────────────────────────────────────

@router.get(
    "/stats",
    response_model=SupplierStatsResponse,
    summary="Get aggregated supplier KPI statistics",
)
def get_supplier_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return live dashboard statistics: total count, high risk count, expiring docs, avg ESG score."""
    return supplier_service.get_supplier_stats(db, current_user.organization_id)


# ─── Listing & Querying ────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=SupplierListResponse,
    summary="List suppliers with pagination and filtering",
)
def list_suppliers(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search across name, code, country"),
    category: Optional[str] = Query(None, description="Filter by category"),
    tier: Optional[str] = Query(None, description="Filter by tier (Tier 1, Tier 2, Tier 3)"),
    risk_level: Optional[str] = Query(None, description="Filter by risk level (LOW, MODERATE, HIGH, CRITICAL)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve suppliers belonging strictly to the caller's organization."""
    total, items = supplier_service.list_suppliers(
        db=db,
        org_id=current_user.organization_id,
        page=page,
        page_size=page_size,
        search=search,
        category=category,
        tier=tier,
        risk_level_filter=risk_level,
    )
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    return SupplierListResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=items,
    )


# ─── Single Supplier Profile ──────────────────────────────────────────────────

@router.get(
    "/{supplier_id}",
    response_model=SupplierDetailResponse,
    summary="Get detailed supplier profile",
)
def get_supplier(
    supplier_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fetch complete supplier profile including verified documents and audit findings."""
    supplier = supplier_service.get_supplier_by_id(db, current_user.organization_id, supplier_id)
    doc_objs = supplier_service.list_supplier_documents(db, current_user.organization_id, supplier_id)
    finding_objs = supplier_service.list_supplier_findings(db, current_user.organization_id, supplier_id)

    enriched_docs = [supplier_service.enrich_document_response(d) for d in doc_objs]
    enriched_findings = [
        SupplierFindingResponse.model_validate(f) for f in finding_objs
    ]

    base_resp = supplier_service.enrich_supplier_response(supplier)
    return SupplierDetailResponse(
        **base_resp.model_dump(),
        documents=enriched_docs,
        findings=enriched_findings,
    )


# ─── Onboarding / Creation ────────────────────────────────────────────────────

@router.post(
    "",
    response_model=SupplierResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Onboard a new supplier",
    dependencies=[Depends(require_roles("admin", "auditor"))],
)
def create_supplier(
    payload: SupplierCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Register and onboard a new supplier profile for the organization (Auditor or Admin)."""
    supplier = supplier_service.create_supplier(db, current_user.organization_id, payload, user=current_user)
    return supplier_service.enrich_supplier_response(supplier)


# ─── Updating ──────────────────────────────────────────────────────────────────

@router.put(
    "/{supplier_id}",
    response_model=SupplierResponse,
    summary="Update an existing supplier",
    dependencies=[Depends(require_roles("admin", "auditor"))],
)
def update_supplier(
    supplier_id: int,
    payload: SupplierUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update supplier details, tier, category, or status (Auditor or Admin)."""
    supplier = supplier_service.update_supplier(
        db, current_user.organization_id, supplier_id, payload, user=current_user
    )
    return supplier_service.enrich_supplier_response(supplier)


# ─── Deletion ──────────────────────────────────────────────────────────────────

@router.delete(
    "/{supplier_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a supplier",
    dependencies=[Depends(require_roles("admin"))],
)
def delete_supplier(
    supplier_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Permanently delete a supplier record and all associated records (Admin only)."""
    supplier_service.delete_supplier(db, current_user.organization_id, supplier_id, user=current_user)
    return {"message": f"Supplier #{supplier_id} successfully deleted.", "supplier_id": supplier_id}


# ─── Document Uploads, Listing & Downloads ─────────────────────────────────────

@router.get(
    "/{supplier_id}/documents",
    response_model=List[SupplierDocumentResponse],
    summary="List compliance documents for a supplier",
)
def list_documents(
    supplier_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all uploaded certifications and compliance documents with real-time expiry status."""
    docs = supplier_service.list_supplier_documents(db, current_user.organization_id, supplier_id)
    return [supplier_service.enrich_document_response(d) for d in docs]


@router.post(
    "/{supplier_id}/documents",
    response_model=SupplierDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a compliance document / certificate",
    dependencies=[Depends(require_roles("admin", "auditor"))],
)
async def upload_document(
    supplier_id: int,
    file: UploadFile = File(..., description="Document file (PDF, DOCX, XLSX, etc.)"),
    document_type: str = Form(..., description="Type of document (e.g. ISO 14001, SA 8000, Environmental Policy)"),
    title: str = Form(..., description="Document title"),
    document_category: Optional[str] = Form(None, description="Category override: POLICY, CERTIFICATE, AUDIT_REPORT, GENERAL"),
    issue_date: Optional[str] = Form(None, description="Issue date in YYYY-MM-DD format"),
    expiry_date: Optional[str] = Form(None, description="Expiry date in YYYY-MM-DD format"),
    notes: Optional[str] = Form(None, description="Audit notes or verification details"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload an ESG certificate, audit report, or policy file with file security validation."""
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # Parse dates if supplied
    parsed_issue: Optional[datetime] = None
    parsed_expiry: Optional[datetime] = None

    if issue_date:
        try:
            parsed_issue = datetime.fromisoformat(issue_date.strip())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid issue_date format. Please use YYYY-MM-DD.",
            )

    if expiry_date:
        try:
            parsed_expiry = datetime.fromisoformat(expiry_date.strip())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid expiry_date format. Please use YYYY-MM-DD.",
            )

    doc = supplier_service.add_supplier_document(
        db=db,
        org_id=current_user.organization_id,
        supplier_id=supplier_id,
        file_bytes=content,
        filename=file.filename or "document.pdf",
        mime_type=file.content_type or "application/pdf",
        document_type=document_type,
        title=title,
        document_category=document_category,
        issue_date=parsed_issue,
        expiry_date=parsed_expiry,
        notes=notes,
        user=current_user,
    )

    return supplier_service.enrich_document_response(doc)


@router.get(
    "/{supplier_id}/documents/{doc_id}/download",
    summary="Download a supplier compliance document securely",
)
def download_document(
    supplier_id: int,
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download an uploaded compliance file with tenant containment validation."""
    file_path, title, mime_type = supplier_service.get_supplier_document_file(
        db, current_user.organization_id, supplier_id, doc_id
    )

    record_audit_event(
        db,
        action="DOCUMENT_DOWNLOADED",
        resource_type="DOCUMENT",
        resource_id=doc_id,
        user=current_user,
        status="SUCCESS",
        details={"supplier_id": supplier_id, "title": title},
        commit=True,
    )

    return FileResponse(
        path=str(file_path),
        media_type=mime_type or "application/octet-stream",
        filename=Path(file_path).name,
    )


# ─── Findings & Risk Evaluation ───────────────────────────────────────────────

@router.get(
    "/{supplier_id}/findings",
    response_model=List[SupplierFindingResponse],
    summary="List audit findings for a supplier",
)
def list_findings(
    supplier_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve compliance findings, observations, and recommendations."""
    findings = supplier_service.list_supplier_findings(db, current_user.organization_id, supplier_id)
    return [SupplierFindingResponse.model_validate(f) for f in findings]


@router.post(
    "/{supplier_id}/findings",
    response_model=SupplierFindingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a compliance finding",
    dependencies=[Depends(require_roles("admin", "auditor"))],
)
def create_finding(
    supplier_id: int,
    payload: SupplierFindingCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a compliance finding and automatically trigger risk recalculation."""
    finding = supplier_service.create_supplier_finding(
        db, current_user.organization_id, supplier_id, payload
    )
    return SupplierFindingResponse.model_validate(finding)


@router.post(
    "/{supplier_id}/evaluate",
    response_model=EvaluateRiskResponse,
    summary="Evaluate supplier risk using Member 2 risk engine or local ISO 31000 matrix",
    dependencies=[Depends(require_roles("admin", "auditor"))],
)
def evaluate_supplier(
    supplier_id: int,
    document_id: Optional[int] = Query(None, description="Supplier policy document ID to compare"),
    policy_comparison: bool = Query(True, description="Compare supplier policy against enterprise baseline"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Evaluate supplier risk score and ESG performance metrics."""
    result = supplier_service.evaluate_supplier_risk(
        db,
        current_user.organization_id,
        supplier_id,
        document_id=document_id,
        policy_comparison=policy_comparison,
        user=current_user,
    )
    return EvaluateRiskResponse(**result)
