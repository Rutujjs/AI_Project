"""Pydantic schemas for Member 5: Authentication, RBAC, Organizations, and Suppliers."""

from __future__ import annotations

from datetime import datetime
import enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


# ─── Auth Schemas ─────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str = Field(..., description="Username or email address")
    password: str = Field(..., description="Plaintext password")


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    email: str
    username: str
    full_name: Optional[str] = None
    role: str
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(..., min_length=6)
    full_name: Optional[str] = None
    role: str = Field(default="viewer", pattern="^(admin|auditor|developer|viewer)$")


# ─── Organization Schemas ──────────────────────────────────────────────────────

class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    industry: Optional[str] = None
    reporting_period: Optional[str] = None
    created_at: datetime


class OrganizationUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    industry: Optional[str] = Field(None, max_length=150)
    reporting_period: Optional[str] = Field(None, max_length=50)


# ─── Supplier Documents Schemas ───────────────────────────────────────────────

class SupplierDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    supplier_id: int
    document_type: str
    document_category: str = "CERTIFICATE"
    title: str
    file_path: str
    file_size: int
    mime_type: str
    issue_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None
    verification_status: str
    expiry_status: str = "VALID"
    days_until_expiry: Optional[int] = None
    notes: Optional[str] = None
    uploaded_at: datetime


# ─── Supplier Findings Schemas ────────────────────────────────────────────────

class SupplierFindingCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    category: str = Field(..., pattern="^(Environmental|Social|Governance)$")
    severity: str = Field(default="Medium", pattern="^(Critical|High|Medium|Low)$")
    likelihood: int = Field(default=3, ge=1, le=5)
    impact: int = Field(default=3, ge=1, le=5)
    description: str = Field(..., min_length=5)
    recommendation: str = Field(..., min_length=5)
    status: str = Field(default="Open", pattern="^(Open|In Progress|Resolved|Waived)$")


class SupplierFindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    supplier_id: int
    title: str
    category: str
    severity: str
    likelihood: int
    impact: int
    risk_score: float
    description: str
    recommendation: str
    status: str
    identified_date: datetime
    resolved_date: Optional[datetime] = None
    created_at: datetime


# ─── Supplier Core Schemas ────────────────────────────────────────────────────

class SupplierCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    code: str = Field(..., min_length=2, max_length=50)
    category: str = Field(default="Manufacturing", max_length=100)
    tier: str = Field(default="Tier 1", pattern="^(Tier 1|Tier 2|Tier 3)$")
    country: str = Field(default="Germany", max_length=100)
    contact_person: Optional[str] = Field(None, max_length=255)
    contact_email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    contact_phone: Optional[str] = Field(None, max_length=50)
    status: str = Field(default="Active", pattern="^(Active|Under Review|Suspended|Inactive)$")


class SupplierUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    code: Optional[str] = Field(None, min_length=2, max_length=50)
    category: Optional[str] = Field(None, max_length=100)
    tier: Optional[str] = Field(None, pattern="^(Tier 1|Tier 2|Tier 3)$")
    country: Optional[str] = Field(None, max_length=100)
    contact_person: Optional[str] = Field(None, max_length=255)
    contact_email: Optional[str] = Field(None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    contact_phone: Optional[str] = Field(None, max_length=50)
    status: Optional[str] = Field(None, pattern="^(Active|Under Review|Suspended|Inactive)$")


class SupplierResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    name: str
    code: str
    category: str
    tier: str
    country: str
    contact_person: Optional[str] = None
    contact_email: str
    contact_phone: Optional[str] = None
    status: str
    risk_score: Optional[float] = None
    risk_level: str = "NOT_ASSESSED"
    environmental_score: float
    social_score: float
    governance_score: float
    overall_score: float
    last_assessment_date: Optional[datetime] = None
    document_count: int = 0
    finding_count: int = 0
    created_at: datetime
    updated_at: datetime


class SupplierDetailResponse(SupplierResponse):
    documents: List[SupplierDocumentResponse] = []
    findings: List[SupplierFindingResponse] = []


class SupplierListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    items: List[SupplierResponse]


class SupplierStatsResponse(BaseModel):
    total_suppliers: int
    high_risk_count: int
    expiring_documents_count: int
    average_esg_score: float


class EvaluateRiskResponse(BaseModel):
    supplier_id: int
    supplier_name: str
    risk_score: Optional[float] = None
    risk_level: str = "NOT_ASSESSED"
    environmental_score: float
    social_score: float
    governance_score: float
    overall_score: float
    evaluated_findings_count: int
    methodology: str
    evaluation_mode: str = "LOCAL_ISO31000_ADAPTER_FALLBACK"
    service_status: str = "OFFLINE"
    evaluated_by: str = "Member 5 ISO 31000:2018 Adapter"
    remote_endpoint: Optional[str] = None
    fallback_reason: Optional[str] = None
    policy_comparison: Optional[str] = None


class BaselinePolicyResponse(BaseModel):
    organization_id: int
    organization_name: str
    baseline_policy_name: Optional[str] = None
    baseline_policy_path: Optional[str] = None
    is_configured: bool = False
    updated_at: Optional[datetime] = None


# ─── Member 5D: Unified Enterprise Dashboard Schemas ─────────────────────────

class ModuleHealthStatus(BaseModel):
    module_name: str
    service_status: str  # ONLINE, OFFLINE, DEGRADED
    data_status: str     # ACTIVE, NO_DATA, NOT_CONFIGURED, PENDING, NO_ACTIVE_SESSION
    endpoint: Optional[str] = None
    last_updated: Optional[datetime] = None
    note: Optional[str] = None


class UnifiedScoreMetric(BaseModel):
    label: str
    score: Optional[float] = None
    status: str  # ASSESSED, PENDING, NO_DATA
    source: str
    methodology: str


class UnifiedFindingItem(BaseModel):
    id: str
    title: str
    category: str
    severity: str
    source_module: str
    description: str
    recommendation: Optional[str] = None
    identified_date: Optional[datetime] = None


class UnifiedRecommendationItem(BaseModel):
    id: str
    title: str
    category: str
    priority: str
    source_module: str
    reason: str
    action: str


class SupplierDashboardSummary(BaseModel):
    total_suppliers: int
    assessed_count: int
    not_assessed_count: int
    high_or_critical_count: int
    moderate_risk_count: int
    low_risk_count: int
    average_esg_score: Optional[float] = None
    expiring_documents_count: int
    total_documents_count: int


class GreenSoftwareDashboardSummary(BaseModel):
    service_status: str
    data_status: str
    analyzed_prs_count: int
    average_green_score: Optional[float] = None
    high_priority_findings_count: int
    energy_efficiency_score: Optional[float] = None
    carbon_footprint_score: Optional[float] = None


class CloudCarbonDashboardSummary(BaseModel):
    service_status: str
    data_status: str
    has_active_session: bool
    total_estimated_kwh: Optional[float] = None
    total_estimated_kg_co2e: Optional[float] = None
    anomaly_count: int = 0
    note: str


class PolicyCheckerDashboardSummary(BaseModel):
    service_status: str
    data_status: str
    baseline_configured: bool
    baseline_policy_name: Optional[str] = None
    latest_policy_risk_level: Optional[str] = None
    latest_overall_esg_score: Optional[float] = None
    note: str


class DocumentIntelligenceDashboardSummary(BaseModel):
    service_status: str
    document_count: int
    note: str


class UnifiedDashboardResponse(BaseModel):
    organization_id: int
    organization_name: str
    reporting_period: str
    generated_at: datetime
    filters_applied: Dict[str, Any]
    module_health: Dict[str, ModuleHealthStatus]
    kpi_scores: List[UnifiedScoreMetric]
    suppliers: SupplierDashboardSummary
    green_software: GreenSoftwareDashboardSummary
    cloud_carbon: CloudCarbonDashboardSummary
    policy_checker: PolicyCheckerDashboardSummary
    document_intelligence: DocumentIntelligenceDashboardSummary
    risk_overview: Dict[str, int]
    priority_findings: List[UnifiedFindingItem]
    recommendations: List[UnifiedRecommendationItem]


# ─── Member 5E: Enterprise ESG Reporting & PDF Export Schemas ─────────────────

class ReportType(str, enum.Enum):
    ENTERPRISE_SUMMARY = "ENTERPRISE_SUMMARY"
    ENVIRONMENTAL = "ENVIRONMENTAL"
    SOCIAL = "SOCIAL"
    GOVERNANCE = "GOVERNANCE"
    SUPPLIER_RISK = "SUPPLIER_RISK"
    FINDINGS_RECOMMENDATIONS = "FINDINGS_RECOMMENDATIONS"


class ReportFormat(str, enum.Enum):
    JSON = "JSON"
    PDF = "PDF"


class ReportTypeDefinition(BaseModel):
    id: str
    title: str
    description: str
    category: str
    default_sections: List[str]
    supported_filters: List[str]


class ReportGenerateRequest(BaseModel):
    report_type: ReportType = Field(default=ReportType.ENTERPRISE_SUMMARY)
    reporting_period: Optional[str] = Field(default=None, description="Report metadata period (e.g. FY 2025–26)")
    category: Optional[str] = Field(default="All", description="Pillar filter: All, Environmental, Social, Governance")
    include_sections: Optional[List[str]] = Field(default=None, description="Optional custom section filter")
    sections: Optional[List[str]] = Field(default=None, description="Optional custom section filter (alias)")
    notes: Optional[str] = Field(default=None, description="Optional executive remarks to include")
    report_data: Optional[Dict[str, Any]] = Field(default=None, description="Exact report preview data to render into PDF")


class ReportSectionData(BaseModel):
    key: str
    title: str
    content_type: str  # text, kpi_grid, table, risk_breakdown
    text_content: Optional[str] = None
    items: Optional[List[Dict[str, Any]]] = None
    table_headers: Optional[List[str]] = None
    table_rows: Optional[List[List[Any]]] = None
    note: Optional[str] = None


class ReportDataResponse(BaseModel):
    report_id: str
    report_type: str
    title: str
    organization_id: int
    organization_name: str
    reporting_period: str
    generated_at: datetime
    generated_by_user: str
    generated_by_role: str
    executive_summary: str
    kpi_summary: List[UnifiedScoreMetric]
    sections: List[ReportSectionData]
    disclosures_and_limitations: List[str]


# ─── Phase 5F: Audit Logging & Notification Schemas ───────────────────────────

class AuditLogResponse(BaseModel):
    id: int
    organization_id: Optional[int] = None
    user_id: Optional[int] = None
    username: str
    user_role: Optional[str] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    status: str
    details: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditLogListResponse(BaseModel):
    items: List[AuditLogResponse]
    total: int
    limit: int
    offset: int


class NotificationResponse(BaseModel):
    id: int
    organization_id: int
    user_id: Optional[int] = None
    category: str
    severity: str
    title: str
    message: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    link_url: Optional[str] = None
    status: str
    is_read: bool = False
    read_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationListResponse(BaseModel):
    items: List[NotificationResponse]
    total: int
    unread_count: int
    limit: int
    offset: int


class UnreadCountResponse(BaseModel):
    unread_count: int


class MarkAllReadResponse(BaseModel):
    marked_read: int


class ExpiryCheckResponse(BaseModel):
    scanned_documents: int
    created_notifications: int
    superseded_notifications: int


