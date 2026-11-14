"""Supplier Service Layer for Member 5: Supplier Intelligence.

Handles:
- Supplier CRUD with strict organization tenant isolation
- Search and multi-criteria filtering (category, tier, risk) with pagination
- ESG Document / Certificate uploads with magic bytes & ZIP structure validation
- Path traversal prevention using os.path.commonpath
- Document expiry tracking and status calculation
- Findings & recommendations management
- Enterprise baseline policy storage & management
- ISO 31000 risk evaluation integrated with Member 2 /api/risk-report
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import io
import math
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
import uuid
import zipfile

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.platform.config import (
    ALLOWED_UPLOAD_EXTENSIONS,
    MAX_UPLOAD_SIZE_BYTES,
    POLICY_DOCUMENT_CATEGORIES,
)
from app.platform.models import Organization, Supplier, SupplierDocument, SupplierFinding, User
from app.platform.services.audit_service import record_audit_event
from app.platform.risk_adapter import (
    calculate_risk_score,
    evaluate_supplier_findings_risk,
    evaluate_via_member2_api,
    risk_level,
)
from app.platform.schemas import (
    SupplierCreateRequest,
    SupplierDocumentResponse,
    SupplierFindingCreate,
    SupplierFindingResponse,
    SupplierResponse,
    SupplierUpdateRequest,
)


# ─── File Validation & Security ───────────────────────────────────────────────

def sanitize_filename(filename: str) -> Tuple[str, str]:
    """Sanitize original filename into safe alphanumeric stem and lowercased extension."""
    p = Path(filename)
    ext = p.suffix.lower()
    raw_stem = p.stem
    safe_stem = re.sub(r"[^a-zA-Z0-9_\-]", "_", raw_stem)[:40] or "document"
    return safe_stem, ext


MAX_ZIP_ENTRIES = 1000
MAX_ZIP_ENTRY_SIZE_BYTES = 30 * 1024 * 1024  # 30 MB
MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES = 100 * 1024 * 1024  # 100 MB
MAX_ZIP_COMPRESSION_RATIO = 100.0


def _validate_openxml_zip(file_bytes: bytes, required_xml: str, doc_label: str) -> None:
    """Validate OpenXML ZIP archive for security, integrity, and internal structure.

    Security properties:
    - In-memory validation only: zero bytes written or extracted to the filesystem.
    - Encryption detection: rejects encrypted/password-protected entries via ZipInfo.flag_bits & 0x1.
    - Zip bomb defense: limits entry count (<=1000), single entry size (<=30MB),
      total uncompressed size (<=100MB), and compression ratio (<=100x).
    - Traversal & Symlink defense: rejects '..', absolute paths, stream colons, null bytes,
      and POSIX symbolic links.
    - OpenXML structure: validates presence of required parts without parsing untrusted external XML.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
            infolist = z.infolist()
            if len(infolist) > MAX_ZIP_ENTRIES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Archive contains too many entries ({len(infolist)} > {MAX_ZIP_ENTRIES}).",
                )

            total_uncompressed = 0
            namelist = []

            for info in infolist:
                # 1. Encryption check: Bit 0 of flag_bits indicates encryption
                if info.flag_bits & 0x1:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Encrypted or password-protected archives are not permitted.",
                    )

                # 2. Path traversal check on internal entry filename
                fn = info.filename
                if ".." in fn or fn.startswith(("/", "\\")) or ":" in fn or "\x00" in fn:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Archive contains unsafe path traversal entry: {fn}",
                    )

                # 3. Symlink check (Unix mode 0o120000 indicates symbolic link)
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Archive contains prohibited symbolic link: {fn}",
                    )

                # 4. Entry uncompressed size limit
                if info.file_size > MAX_ZIP_ENTRY_SIZE_BYTES:
                    max_mb = MAX_ZIP_ENTRY_SIZE_BYTES // (1024 * 1024)
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Archive entry '{fn}' exceeds uncompressed limit of {max_mb} MB.",
                    )

                # 5. Compression ratio check (zip bomb defense)
                if info.compress_size > 0 and info.file_size > 10240:
                    ratio = info.file_size / info.compress_size
                    if ratio > MAX_ZIP_COMPRESSION_RATIO:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Archive entry '{fn}' exhibits suspicious compression ratio ({ratio:.1f}x > {MAX_ZIP_COMPRESSION_RATIO}x).",
                        )

                total_uncompressed += info.file_size
                if total_uncompressed > MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES:
                    max_total_mb = MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES // (1024 * 1024)
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Archive total uncompressed size exceeds limit of {max_total_mb} MB.",
                    )

                namelist.append(fn)

            # 6. Verify required OpenXML structure components
            if required_xml not in namelist or "[Content_Types].xml" not in namelist:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid {doc_label} structure: Missing required OpenXML document components.",
                )

    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Corrupted {doc_label} archive.",
        )


def validate_file_content(file_bytes: bytes, filename: str) -> None:
    """Validate file size, extension, magic header bytes, and openXML structures."""
    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    if len(file_bytes) > MAX_UPLOAD_SIZE_BYTES:
        max_mb = MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds maximum allowed size of {max_mb} MB.",
        )

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_UPLOAD_EXTENSIONS))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File extension '{ext}' is not permitted. Allowed extensions: {allowed}",
        )

    if ext == ".pdf":
        if not file_bytes.startswith(b"%PDF"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid PDF file: Missing %PDF signature.",
            )
    elif ext == ".png":
        if not file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid PNG image: Missing PNG header signature.",
            )
    elif ext in (".jpg", ".jpeg"):
        if not file_bytes.startswith(b"\xff\xd8\xff"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JPEG image: Missing JPEG header signature.",
            )
    elif ext == ".docx":
        if not file_bytes.startswith(b"PK\x03\x04"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid DOCX document: Missing PK ZIP header signature.",
            )
        _validate_openxml_zip(file_bytes, "word/document.xml", "DOCX")
    elif ext == ".xlsx":
        if not file_bytes.startswith(b"PK\x03\x04"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid XLSX document: Missing PK ZIP header signature.",
            )
        _validate_openxml_zip(file_bytes, "xl/workbook.xml", "XLSX")
    elif ext in (".csv", ".txt"):
        if b"\x00" in file_bytes[:1024]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid text or CSV file: Binary null bytes detected.",
            )


def classify_document(document_type: str, category_override: Optional[str] = None) -> str:
    """Classify document into POLICY, CERTIFICATE, AUDIT_REPORT, or GENERAL."""
    if category_override and category_override.upper() in ("POLICY", "CERTIFICATE", "AUDIT_REPORT", "GENERAL"):
        return category_override.upper()
    if document_type in POLICY_DOCUMENT_CATEGORIES:
        return "POLICY"
    if document_type in {"ISO 14001", "ISO 45001", "ISO 9001", "ISO 27001", "ISO 50001", "SA 8000", "REACH / RoHS"}:
        return "CERTIFICATE"
    if document_type in {"ESG Audit", "Social Audit", "Environmental Audit"}:
        return "AUDIT_REPORT"
    return "GENERAL"


# ─── Baseline Policy Operations ───────────────────────────────────────────────

def set_organization_baseline_policy(
    db: Session,
    org_id: int,
    file_bytes: bytes,
    filename: str,
    user: Optional[User] = None,
) -> Organization:
    """Store the enterprise baseline policy for an organization under tenant isolation."""
    validate_file_content(file_bytes, filename)
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")

    safe_stem, ext = sanitize_filename(filename)
    unique_name = f"baseline_{uuid.uuid4().hex[:12]}_{safe_stem}{ext}"
    base_dir = (Path("uploads/organizations") / f"org_{org_id}").resolve()
    base_dir.mkdir(parents=True, exist_ok=True)
    target_path = (base_dir / unique_name).resolve()

    if os.path.commonpath([str(base_dir), str(target_path)]) != str(base_dir):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path traversal attempt detected.")

    with open(target_path, "wb") as f:
        f.write(file_bytes)

    try:
        org.baseline_policy_path = str(target_path).replace("\\", "/")
        org.baseline_policy_name = filename
        org.updated_at = datetime.now(timezone.utc)

        record_audit_event(
            db,
            action="BASELINE_POLICY_UPLOADED",
            resource_type="ORGANIZATION",
            resource_id=org_id,
            user=user,
            organization_id=org_id,
            status="SUCCESS",
            details={"filename": filename, "policy_name": org.baseline_policy_name},
            commit=False,
        )

        db.commit()
        db.refresh(org)
        return org
    except Exception:
        db.rollback()
        try:
            if target_path.exists():
                target_path.unlink()
        except Exception as cleanup_err:
            logger.warning(f"Failed to cleanup orphaned baseline file {target_path}: {cleanup_err}")
        raise


def get_organization_baseline_policy(
    db: Session,
    org_id: int,
) -> Dict[str, Any]:
    """Retrieve metadata about the organization's enterprise baseline policy."""
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")

    is_cfg = bool(org.baseline_policy_path and Path(org.baseline_policy_path).exists())
    return {
        "organization_id": org.id,
        "organization_name": org.name,
        "baseline_policy_name": org.baseline_policy_name,
        "baseline_policy_path": org.baseline_policy_path if is_cfg else None,
        "is_configured": is_cfg,
        "updated_at": org.updated_at,
    }


# ─── Enriched Models ──────────────────────────────────────────────────────────

def _calculate_doc_expiry(expiry_date: Optional[datetime]) -> Tuple[str, Optional[int]]:
    """Determine document expiry status and remaining days."""
    if not expiry_date:
        return "NO_EXPIRY", None

    now = datetime.now(timezone.utc)
    if expiry_date.tzinfo is None:
        exp = expiry_date.replace(tzinfo=timezone.utc)
    else:
        exp = expiry_date

    diff = exp - now
    days = diff.days

    if days < 0:
        return "EXPIRED", days
    elif days <= 30:
        return "EXPIRING_SOON", days
    else:
        return "VALID", days


def enrich_document_response(doc: SupplierDocument) -> SupplierDocumentResponse:
    """Transform SupplierDocument ORM into SupplierDocumentResponse with computed expiry status."""
    expiry_status, days = _calculate_doc_expiry(doc.expiry_date)
    return SupplierDocumentResponse(
        id=doc.id,
        supplier_id=doc.supplier_id,
        document_type=doc.document_type,
        document_category=doc.document_category or "CERTIFICATE",
        title=doc.title,
        file_path=doc.file_path,
        file_size=doc.file_size,
        mime_type=doc.mime_type,
        issue_date=doc.issue_date,
        expiry_date=doc.expiry_date,
        verification_status=doc.verification_status,
        expiry_status=expiry_status,
        days_until_expiry=days,
        notes=doc.notes,
        uploaded_at=doc.uploaded_at,
    )


def enrich_supplier_response(supplier: Supplier) -> SupplierResponse:
    """Transform Supplier ORM into SupplierResponse with computed counts."""
    doc_count = len(supplier.documents) if supplier.documents else 0
    finding_count = len(supplier.findings) if supplier.findings else 0
    return SupplierResponse(
        id=supplier.id,
        organization_id=supplier.organization_id,
        name=supplier.name,
        code=supplier.code,
        category=supplier.category,
        tier=supplier.tier,
        country=supplier.country,
        contact_person=supplier.contact_person,
        contact_email=supplier.contact_email,
        contact_phone=supplier.contact_phone,
        status=supplier.status,
        risk_score=supplier.risk_score,
        risk_level=supplier.risk_level,
        environmental_score=supplier.environmental_score,
        social_score=supplier.social_score,
        governance_score=supplier.governance_score,
        overall_score=supplier.overall_score,
        last_assessment_date=supplier.last_assessment_date,
        document_count=doc_count,
        finding_count=finding_count,
        created_at=supplier.created_at,
        updated_at=supplier.updated_at,
    )


# ─── Query Operations ──────────────────────────────────────────────────────────

def list_suppliers(
    db: Session,
    org_id: int,
    page: int = 1,
    page_size: int = 10,
    search: Optional[str] = None,
    category: Optional[str] = None,
    tier: Optional[str] = None,
    risk_level_filter: Optional[str] = None,
) -> Tuple[int, List[SupplierResponse]]:
    """List suppliers under tenant isolation with filtering and pagination."""
    query = db.query(Supplier).filter(Supplier.organization_id == org_id)

    if search:
        s = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Supplier.name.ilike(s),
                Supplier.code.ilike(s),
                Supplier.country.ilike(s),
                Supplier.contact_person.ilike(s),
            )
        )

    if category and category.lower() != "all":
        query = query.filter(Supplier.category.ilike(f"%{category.strip()}%"))

    if tier and tier.lower() != "all":
        query = query.filter(Supplier.tier.ilike(f"%{tier.strip()}%"))

    if risk_level_filter and risk_level_filter.lower() != "all":
        query = query.filter(Supplier.risk_level.ilike(risk_level_filter.strip()))

    total = query.count()
    offset = max(0, (page - 1) * page_size)
    suppliers = query.order_by(Supplier.name.asc()).offset(offset).limit(page_size).all()

    items = [enrich_supplier_response(s) for s in suppliers]
    return total, items


def get_supplier_stats(db: Session, org_id: int) -> Dict[str, Any]:
    """Calculate aggregate KPI stats for the supplier dashboard."""
    suppliers = db.query(Supplier).filter(Supplier.organization_id == org_id).all()
    total = len(suppliers)

    if total == 0:
        return {
            "total_suppliers": 0,
            "high_risk_count": 0,
            "expiring_documents_count": 0,
            "average_esg_score": 0.0,
        }

    high_risk_count = sum(1 for s in suppliers if (s.risk_level or "").upper() in ("HIGH", "CRITICAL"))
    avg_score = round(sum(s.overall_score for s in suppliers) / total, 1)

    supplier_ids = [s.id for s in suppliers]
    docs = db.query(SupplierDocument).filter(SupplierDocument.supplier_id.in_(supplier_ids)).all()
    expiring_count = 0
    now = datetime.now(timezone.utc)
    for d in docs:
        if d.expiry_date:
            exp = d.expiry_date.replace(tzinfo=timezone.utc) if d.expiry_date.tzinfo is None else d.expiry_date
            if (exp - now).days <= 30:
                expiring_count += 1

    return {
        "total_suppliers": total,
        "high_risk_count": high_risk_count,
        "expiring_documents_count": expiring_count,
        "average_esg_score": avg_score,
    }


def get_supplier_by_id(db: Session, org_id: int, supplier_id: int) -> Supplier:
    """Retrieve single supplier with tenant isolation enforcement."""
    supplier = (
        db.query(Supplier)
        .filter(Supplier.id == supplier_id, Supplier.organization_id == org_id)
        .first()
    )
    if not supplier:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Supplier #{supplier_id} not found in this organization.",
        )
    return supplier


# ─── Mutating Operations ──────────────────────────────────────────────────────

def create_supplier(
    db: Session,
    org_id: int,
    data: SupplierCreateRequest,
    user: Optional[User] = None,
) -> Supplier:
    """Onboard a new supplier under tenant isolation."""
    existing = (
        db.query(Supplier)
        .filter(
            Supplier.organization_id == org_id,
            func.lower(Supplier.code) == data.code.strip().lower(),
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A supplier with code '{data.code}' already exists in your organization.",
        )

    supplier = Supplier(
        organization_id=org_id,
        name=data.name.strip(),
        code=data.code.strip().upper(),
        category=data.category,
        tier=data.tier,
        country=data.country,
        contact_person=data.contact_person,
        contact_email=data.contact_email,
        contact_phone=data.contact_phone,
        status=data.status,
        risk_score=None,
        risk_level="NOT_ASSESSED",
        environmental_score=85.0,
        social_score=85.0,
        governance_score=85.0,
        overall_score=85.0,
    )
    db.add(supplier)
    db.flush()

    record_audit_event(
        db,
        action="SUPPLIER_CREATED",
        resource_type="SUPPLIER",
        resource_id=supplier.id,
        user=user,
        organization_id=org_id,
        status="SUCCESS",
        details={"name": supplier.name, "code": supplier.code, "tier": supplier.tier, "category": supplier.category},
        commit=False,
    )

    db.commit()
    db.refresh(supplier)
    return supplier


def update_supplier(
    db: Session,
    org_id: int,
    supplier_id: int,
    data: SupplierUpdateRequest,
    user: Optional[User] = None,
) -> Supplier:
    """Update supplier details."""
    supplier = get_supplier_by_id(db, org_id, supplier_id)

    if data.code is not None and data.code.strip().upper() != supplier.code:
        code_check = (
            db.query(Supplier)
            .filter(
                Supplier.organization_id == org_id,
                Supplier.id != supplier.id,
                func.lower(Supplier.code) == data.code.strip().lower(),
            )
            .first()
        )
        if code_check:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"A supplier with code '{data.code}' already exists.",
            )
        supplier.code = data.code.strip().upper()

    if data.name is not None:
        supplier.name = data.name.strip()
    if data.category is not None:
        supplier.category = data.category
    if data.tier is not None:
        supplier.tier = data.tier
    if data.country is not None:
        supplier.country = data.country
    if data.contact_person is not None:
        supplier.contact_person = data.contact_person
    if data.contact_email is not None:
        supplier.contact_email = data.contact_email
    if data.contact_phone is not None:
        supplier.contact_phone = data.contact_phone
    if data.status is not None:
        supplier.status = data.status

    supplier.updated_at = datetime.now(timezone.utc)

    record_audit_event(
        db,
        action="SUPPLIER_UPDATED",
        resource_type="SUPPLIER",
        resource_id=supplier.id,
        user=user,
        organization_id=org_id,
        status="SUCCESS",
        details={"name": supplier.name, "code": supplier.code, "status": supplier.status},
        commit=False,
    )

    db.commit()
    db.refresh(supplier)
    return supplier


def delete_supplier(
    db: Session,
    org_id: int,
    supplier_id: int,
    user: Optional[User] = None,
) -> None:
    """Delete a supplier with tenant isolation safeguard."""
    supplier = get_supplier_by_id(db, org_id, supplier_id)

    record_audit_event(
        db,
        action="SUPPLIER_DELETED",
        resource_type="SUPPLIER",
        resource_id=supplier_id,
        user=user,
        organization_id=org_id,
        status="SUCCESS",
        details={"name": supplier.name, "code": supplier.code},
        commit=False,
    )

    db.delete(supplier)
    db.commit()


# ─── Documents Management ─────────────────────────────────────────────────────

def add_supplier_document(
    db: Session,
    org_id: int,
    supplier_id: int,
    file_bytes: bytes,
    filename: str,
    mime_type: str,
    document_type: str,
    title: str,
    document_category: Optional[str] = None,
    issue_date: Optional[datetime] = None,
    expiry_date: Optional[datetime] = None,
    notes: Optional[str] = None,
    user: Optional[User] = None,
) -> SupplierDocument:
    """Upload and attach a compliance certificate or ESG policy to a supplier with security validation."""
    supplier = get_supplier_by_id(db, org_id, supplier_id)

    # Perform thorough security validation
    validate_file_content(file_bytes, filename)

    safe_stem, safe_ext = sanitize_filename(filename)
    unique_name = f"{supplier.id}_{uuid.uuid4().hex[:8]}_{safe_stem}{safe_ext}"

    base_dir = (Path("uploads/suppliers") / f"org_{org_id}" / f"supplier_{supplier_id}").resolve()
    base_dir.mkdir(parents=True, exist_ok=True)
    saved_path = (base_dir / unique_name).resolve()

    if os.path.commonpath([str(base_dir), str(saved_path)]) != str(base_dir):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path traversal attempt detected in document storage.",
        )

    with open(saved_path, "wb") as f:
        f.write(file_bytes)

    try:
        # Determine initial verification status based on expiry
        initial_status = "Verified"
        now_utc = datetime.now(timezone.utc)
        if expiry_date:
            exp = expiry_date.replace(tzinfo=timezone.utc) if expiry_date.tzinfo is None else expiry_date
            if exp < now_utc:
                initial_status = "Expired"

        cat = classify_document(document_type, document_category)

        doc = SupplierDocument(
            supplier_id=supplier.id,
            document_type=document_type,
            document_category=cat,
            title=title,
            file_path=str(saved_path).replace("\\", "/"),
            file_size=len(file_bytes),
            mime_type=mime_type or "application/pdf",
            issue_date=issue_date,
            expiry_date=expiry_date,
            verification_status=initial_status,
            notes=notes,
        )
        db.add(doc)
        db.flush()

        # If valid renewed document, auto-resolve previous expiry alerts for this supplier & doc_type
        if expiry_date:
            exp = expiry_date.replace(tzinfo=timezone.utc) if expiry_date.tzinfo is None else expiry_date
            if exp > now_utc:
                from app.platform.services.notification_service import resolve_notifications_for_supplier_doctype
                resolve_notifications_for_supplier_doctype(db, org_id, supplier.id, document_type)

        record_audit_event(
            db,
            action="DOCUMENT_UPLOADED",
            resource_type="DOCUMENT",
            resource_id=doc.id,
            user=user,
            organization_id=org_id,
            status="SUCCESS",
            details={
                "supplier_id": supplier.id,
                "title": doc.title,
                "filename": filename,
                "file_size": len(file_bytes),
                "document_type": document_type,
            },
            commit=False,
        )

        db.commit()
        db.refresh(doc)
        return doc
    except Exception:
        db.rollback()
        try:
            if saved_path.exists():
                saved_path.unlink()
        except Exception as cleanup_err:
            logger.warning(f"Failed to cleanup orphaned supplier document file {saved_path}: {cleanup_err}")
        raise


def list_supplier_documents(
    db: Session,
    org_id: int,
    supplier_id: int,
) -> List[SupplierDocument]:
    """Retrieve all compliance documents for a specific supplier under tenant isolation."""
    supplier = get_supplier_by_id(db, org_id, supplier_id)
    return (
        db.query(SupplierDocument)
        .filter(SupplierDocument.supplier_id == supplier.id)
        .order_by(SupplierDocument.uploaded_at.desc())
        .all()
    )


def get_supplier_document_file(
    db: Session,
    org_id: int,
    supplier_id: int,
    doc_id: int,
) -> Tuple[Path, str, str]:
    """Retrieve verified file path for document download with tenant containment check."""
    supplier = get_supplier_by_id(db, org_id, supplier_id)
    doc = (
        db.query(SupplierDocument)
        .filter(SupplierDocument.id == doc_id, SupplierDocument.supplier_id == supplier.id)
        .first()
    )
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document #{doc_id} not found for supplier #{supplier_id}.",
        )

    file_path = Path(doc.file_path).resolve()
    base_dir = (Path("uploads/suppliers") / f"org_{org_id}" / f"supplier_{supplier_id}").resolve()

    if os.path.commonpath([str(base_dir), str(file_path)]) != str(base_dir) or not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document file not found on disk or invalid path.",
        )

    return file_path, doc.title, doc.mime_type


# ─── Findings & Risk Evaluation ───────────────────────────────────────────────

def list_supplier_findings(
    db: Session,
    org_id: int,
    supplier_id: int,
) -> List[SupplierFinding]:
    """Retrieve compliance findings and recommendations for a supplier."""
    supplier = get_supplier_by_id(db, org_id, supplier_id)
    return (
        db.query(SupplierFinding)
        .filter(SupplierFinding.supplier_id == supplier.id)
        .order_by(SupplierFinding.risk_score.desc())
        .all()
    )


def create_supplier_finding(
    db: Session,
    org_id: int,
    supplier_id: int,
    data: SupplierFindingCreate,
) -> SupplierFinding:
    """Create a new compliance finding with ISO 31000 risk scoring."""
    supplier = get_supplier_by_id(db, org_id, supplier_id)
    score = calculate_risk_score(data.likelihood, data.impact)

    clean_title = data.title.strip()
    # Idempotency / deduplication check: update if an open finding with same title exists
    existing_finding = (
        db.query(SupplierFinding)
        .filter(
            SupplierFinding.supplier_id == supplier.id,
            func.lower(SupplierFinding.title) == clean_title.lower(),
            SupplierFinding.status == "Open",
        )
        .first()
    )
    if existing_finding:
        existing_finding.category = data.category
        existing_finding.severity = data.severity
        existing_finding.likelihood = data.likelihood
        existing_finding.impact = data.impact
        existing_finding.risk_score = score
        existing_finding.description = data.description.strip()
        existing_finding.recommendation = data.recommendation.strip()
        db.commit()
        db.refresh(existing_finding)
        evaluate_supplier_risk(db, org_id, supplier.id, policy_comparison=False)
        return existing_finding

    finding = SupplierFinding(
        supplier_id=supplier.id,
        title=clean_title,
        category=data.category,
        severity=data.severity,
        likelihood=data.likelihood,
        impact=data.impact,
        risk_score=score,
        description=data.description.strip(),
        recommendation=data.recommendation.strip(),
        status=data.status,
    )
    db.add(finding)
    db.commit()
    db.refresh(finding)

    # Trigger automatic risk recalculation without requiring external policy comparison
    evaluate_supplier_risk(db, org_id, supplier.id, policy_comparison=False)
    return finding


def evaluate_supplier_risk(
    db: Session,
    org_id: int,
    supplier_id: int,
    document_id: Optional[int] = None,
    policy_comparison: bool = True,
    user: Optional[User] = None,
) -> Dict[str, Any]:
    """Evaluate supplier risk using Member 2 /api/risk-report or local ISO 31000 matrix.

    Modes:
    1. policy_comparison=True (Default):
       - Compares a supplier POLICY document against the organization's enterprise baseline policy.
       - Rejects non-policy documents (certificates, audits) with HTTP 400.
       - Rejects if organization has no enterprise baseline policy configured with HTTP 400.
       - Invokes Member 2 /api/risk-report via evaluate_via_member2_api.
       - Gracefully falls back to local ISO 31000 calculation if Member 2 is unreachable.
       - Ingests policy discrepancy findings into SupplierFinding.
    2. policy_comparison=False:
       - Evaluates supplier risk directly from findings and certificate expiry statuses.
    """
    supplier = get_supplier_by_id(db, org_id, supplier_id)
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")

    if policy_comparison:
        # 1. Verify organization baseline policy configuration
        if not org.baseline_policy_path or not Path(org.baseline_policy_path).exists():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Enterprise baseline policy is not configured for this organization. "
                    "Please upload an enterprise baseline policy before running policy risk evaluation."
                ),
            )

        # 2. Select supplier policy document
        policy_doc: Optional[SupplierDocument] = None
        if document_id is not None:
            policy_doc = (
                db.query(SupplierDocument)
                .filter(SupplierDocument.id == document_id, SupplierDocument.supplier_id == supplier.id)
                .first()
            )
            if not policy_doc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Supplier document #{document_id} not found.",
                )
            # Validate document category: must be a policy, not a certificate
            if policy_doc.document_category != "POLICY" and policy_doc.document_type not in POLICY_DOCUMENT_CATEGORIES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Document '{policy_doc.title}' is classified as a {policy_doc.document_category}. "
                        "Only policy documents (e.g., Code of Conduct, Environmental Policy) can be evaluated against the baseline policy."
                    ),
                )
        else:
            # Query latest active document classified as POLICY
            policy_doc = (
                db.query(SupplierDocument)
                .filter(
                    SupplierDocument.supplier_id == supplier.id,
                    or_(
                        SupplierDocument.document_category == "POLICY",
                        SupplierDocument.document_type.in_(POLICY_DOCUMENT_CATEGORIES),
                    ),
                )
                .order_by(SupplierDocument.uploaded_at.desc())
                .first()
            )
            if not policy_doc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "No policy document found for this supplier. "
                        "Please upload a supplier policy document (e.g., Code of Conduct, Environmental Policy) or specify document_id."
                    ),
                )

        # 3. Call Member 2 /api/risk-report via risk_adapter
        eval_result = evaluate_via_member2_api(
            old_policy_path=org.baseline_policy_path,
            new_policy_path=policy_doc.file_path,
        )

        # 4. If Member 2 returned remote risks, ingest any new findings
        risks_list = eval_result.get("risks", [])
        if risks_list:
            for r in risks_list:
                if not isinstance(r, dict):
                    continue
                finding_title = f"Policy Discrepancy: {r.get('category', 'Governance')} - {r.get('classification', 'Gap')}"
                # Check for existing open finding with this title
                existing = (
                    db.query(SupplierFinding)
                    .filter(
                        SupplierFinding.supplier_id == supplier.id,
                        SupplierFinding.title == finding_title,
                    )
                    .first()
                )
                if not existing:
                    severity = r.get("severity", "Medium")
                    l_val = int(r.get("likelihood", 3))
                    i_val = int(r.get("impact", 3))
                    f_score = float(r.get("risk_score", calculate_risk_score(l_val, i_val)))

                    new_finding = SupplierFinding(
                        supplier_id=supplier.id,
                        title=finding_title,
                        category=r.get("category", "Governance").capitalize(),
                        severity=severity,
                        likelihood=l_val,
                        impact=i_val,
                        risk_score=f_score,
                        description=r.get("explanation") or r.get("evidence") or "Discrepancy identified against enterprise baseline policy.",
                        recommendation=r.get("recommendation") or "Review and align supplier policy with enterprise standard.",
                        status="Open",
                    )
                    db.add(new_finding)
            db.commit()

        # If fallback engaged, calculate local score based on supplier findings + certificates
        if eval_result.get("evaluation_mode") == "LOCAL_ISO31000_ADAPTER_FALLBACK":
            fallback_eval = _evaluate_local_findings_and_certificates(db, supplier)
            supplier.risk_score = fallback_eval["risk_score"]
            supplier.risk_level = fallback_eval["risk_level"]
            supplier.environmental_score = fallback_eval["environmental"]
            supplier.social_score = fallback_eval["social"]
            supplier.governance_score = fallback_eval["governance"]
            supplier.overall_score = fallback_eval["overall"]
            eval_result["risk_score"] = fallback_eval["risk_score"]
            eval_result["risk_level"] = fallback_eval["risk_level"]
            eval_result["environmental"] = fallback_eval["environmental"]
            eval_result["social"] = fallback_eval["social"]
            eval_result["governance"] = fallback_eval["governance"]
            eval_result["overall"] = fallback_eval["overall"]
        else:
            supplier.risk_score = eval_result["risk_score"]
            supplier.risk_level = eval_result["risk_level"]
            supplier.environmental_score = eval_result["environmental"]
            supplier.social_score = eval_result["social"]
            supplier.governance_score = eval_result["governance"]
            supplier.overall_score = eval_result["overall"]

        supplier.last_assessment_date = datetime.now(timezone.utc)

        record_audit_event(
            db,
            action="SUPPLIER_EVALUATED",
            resource_type="SUPPLIER",
            resource_id=supplier.id,
            user=user,
            organization_id=org_id,
            status="SUCCESS",
            details={
                "risk_level": supplier.risk_level,
                "risk_score": supplier.risk_score,
                "overall_score": supplier.overall_score,
                "policy_comparison": True,
            },
            commit=False,
        )

        if (supplier.risk_level or "").upper() in ("HIGH", "CRITICAL"):
            from app.platform.services.notification_service import create_notification
            create_notification(
                db=db,
                organization_id=org_id,
                category="SUPPLIER_RISK",
                severity="CRITICAL" if supplier.risk_level.upper() == "CRITICAL" else "WARNING",
                title=f"Elevated Supplier Risk: {supplier.name}",
                message=f"Supplier '{supplier.name}' ({supplier.code}) assessed with {supplier.risk_level} risk (score: {supplier.risk_score}).",
                resource_type="supplier",
                resource_id=str(supplier.id),
                event_key=f"supplier:{supplier.id}:risk:{supplier.risk_level.upper()}",
                link_url="suppliers.html",
                commit=False,
            )
        elif (supplier.risk_level or "").upper() in ("LOW", "MODERATE"):
            from app.platform.models import Notification
            now_utc = datetime.now(timezone.utc)
            active_risk_alerts = (
                db.query(Notification)
                .filter(
                    Notification.organization_id == org_id,
                    Notification.category == "SUPPLIER_RISK",
                    Notification.resource_type == "supplier",
                    Notification.resource_id == str(supplier.id),
                    Notification.status == "ACTIVE",
                )
                .all()
            )
            for alert in active_risk_alerts:
                alert.status = "RESOLVED"
                alert.resolved_at = now_utc

        db.commit()
        db.refresh(supplier)

        return {
            "supplier_id": supplier.id,
            "supplier_name": supplier.name,
            "risk_score": supplier.risk_score,
            "risk_level": supplier.risk_level,
            "environmental_score": supplier.environmental_score,
            "social_score": supplier.social_score,
            "governance_score": supplier.governance_score,
            "overall_score": supplier.overall_score,
            "evaluated_findings_count": eval_result.get("risk_count", len(risks_list)),
            "methodology": eval_result.get("methodology", "ISO 31000:2018"),
            "evaluation_mode": eval_result.get("evaluation_mode", "MEMBER2_REMOTE_API"),
            "service_status": eval_result.get("service_status", "ONLINE"),
            "evaluated_by": eval_result.get("evaluated_by", "Member 2 Policy Risk Engine (/api/risk-report)"),
            "remote_endpoint": eval_result.get("remote_endpoint"),
            "fallback_reason": eval_result.get("fallback_reason"),
            "policy_comparison": f"Compared supplier policy '{policy_doc.title}' against enterprise baseline '{org.baseline_policy_name or 'Enterprise Baseline'}'",
        }

    else:
        # Findings and certificate status evaluation without external policy comparison
        eval_result = _evaluate_local_findings_and_certificates(db, supplier)
        supplier.risk_score = eval_result["risk_score"]
        supplier.risk_level = eval_result["risk_level"]
        supplier.environmental_score = eval_result["environmental"]
        supplier.social_score = eval_result["social"]
        supplier.governance_score = eval_result["governance"]
        supplier.overall_score = eval_result["overall"]
        supplier.last_assessment_date = datetime.now(timezone.utc)

        record_audit_event(
            db,
            action="SUPPLIER_EVALUATED",
            resource_type="SUPPLIER",
            resource_id=supplier.id,
            user=user,
            organization_id=org_id,
            status="SUCCESS",
            details={
                "risk_level": supplier.risk_level,
                "risk_score": supplier.risk_score,
                "overall_score": supplier.overall_score,
                "policy_comparison": False,
            },
            commit=False,
        )

        if (supplier.risk_level or "").upper() in ("HIGH", "CRITICAL"):
            from app.platform.services.notification_service import create_notification
            create_notification(
                db=db,
                organization_id=org_id,
                category="SUPPLIER_RISK",
                severity="CRITICAL" if supplier.risk_level.upper() == "CRITICAL" else "WARNING",
                title=f"Elevated Supplier Risk: {supplier.name}",
                message=f"Supplier '{supplier.name}' ({supplier.code}) assessed with {supplier.risk_level} risk (score: {supplier.risk_score}).",
                resource_type="supplier",
                resource_id=str(supplier.id),
                event_key=f"supplier:{supplier.id}:risk:{supplier.risk_level.upper()}",
                link_url="suppliers.html",
                commit=False,
            )
        elif (supplier.risk_level or "").upper() in ("LOW", "MODERATE"):
            from app.platform.models import Notification
            now_utc = datetime.now(timezone.utc)
            active_risk_alerts = (
                db.query(Notification)
                .filter(
                    Notification.organization_id == org_id,
                    Notification.category == "SUPPLIER_RISK",
                    Notification.resource_type == "supplier",
                    Notification.resource_id == str(supplier.id),
                    Notification.status == "ACTIVE",
                )
                .all()
            )
            for alert in active_risk_alerts:
                alert.status = "RESOLVED"
                alert.resolved_at = now_utc

        db.commit()
        db.refresh(supplier)

        return {
            "supplier_id": supplier.id,
            "supplier_name": supplier.name,
            "risk_score": supplier.risk_score,
            "risk_level": supplier.risk_level,
            "environmental_score": supplier.environmental_score,
            "social_score": supplier.social_score,
            "governance_score": supplier.governance_score,
            "overall_score": supplier.overall_score,
            "evaluated_findings_count": eval_result.get("evaluated_count", 0),
            "methodology": "ISO 31000:2018-aligned 5x5 screening matrix (Local Deterministic)",
            "evaluation_mode": "LOCAL_ISO31000_ADAPTER",
            "service_status": "OFFLINE",
            "evaluated_by": "Member 5 ISO 31000:2018 Adapter",
            "remote_endpoint": None,
            "fallback_reason": None,
            "policy_comparison": "Local findings & certificate expiry evaluation",
        }


def _evaluate_local_findings_and_certificates(db: Session, supplier: Supplier) -> Dict[str, Any]:
    """Calculate local deterministic ISO 31000 score from active findings and expired certificates."""
    findings = (
        db.query(SupplierFinding)
        .filter(SupplierFinding.supplier_id == supplier.id, SupplierFinding.status != "Resolved")
        .all()
    )

    findings_payload = [
        {
            "category": f.category,
            "risk_score": f.risk_score,
            "likelihood": f.likelihood,
            "impact": f.impact,
        }
        for f in findings
    ]

    docs = db.query(SupplierDocument).filter(SupplierDocument.supplier_id == supplier.id).all()
    now = datetime.now(timezone.utc)
    for d in docs:
        if d.expiry_date:
            exp = d.expiry_date.replace(tzinfo=timezone.utc) if d.expiry_date.tzinfo is None else d.expiry_date
            if exp < now:
                findings_payload.append({
                    "category": "Governance",
                    "risk_score": calculate_risk_score(4, 4),
                    "likelihood": 4,
                    "impact": 4,
                })

    res = evaluate_supplier_findings_risk(findings_payload)
    res["evaluated_count"] = len(findings_payload)
    return res
