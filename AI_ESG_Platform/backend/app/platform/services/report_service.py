"""Enterprise ESG Reporting & PDF Export Service (Member 5 Phase 5E).

Compiles and formats executive-ready sustainability reports across 6 report types:
1. Enterprise ESG Summary Report
2. Environmental Performance Report
3. Social Performance Report
4. Governance Performance Report
5. Supplier Risk and Compliance Report
6. Findings and Recommendations Report

Enforces:
- Strict multi-tenant isolation (scoped by organization_id)
- Truthful metrics: missing metrics rendered as 'Pending Assessment' or null, never 0 or 80
- Strict separation of NOT_ASSESSED suppliers from Low risk
- Full data provenance disclosure for Members 1–5
- Pure in-memory PDF generation using ReportLab Platypus
"""

from __future__ import annotations

from datetime import datetime, timezone
import io
import logging
from typing import Any, Dict, List, Optional
import uuid

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.platform.models import Organization, Supplier, SupplierDocument, SupplierFinding, User
from app.platform.schemas import (
    ReportDataResponse,
    ReportGenerateRequest,
    ReportSectionData,
    ReportType,
    ReportTypeDefinition,
    UnifiedScoreMetric,
)
from app.platform.services.dashboard_service import aggregate_dashboard_metrics

logger = logging.getLogger(__name__)


# ─── Report Definitions Catalog ───────────────────────────────────────────────

REPORT_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    ReportType.ENTERPRISE_SUMMARY.value: {
        "title": "Enterprise ESG Summary Report",
        "description": "Comprehensive enterprise sustainability audit aggregating Environmental, Social, and Governance metrics across supply chain and digital infrastructure.",
        "category": "All",
        "default_sections": [
            "executive_summary",
            "kpi_overview",
            "module_health",
            "supplier_risk_distribution",
            "digital_infrastructure",
            "priority_findings",
            "strategic_recommendations",
            "disclosures",
        ],
        "supported_filters": ["reporting_period", "category"],
    },
    ReportType.ENVIRONMENTAL.value: {
        "title": "Environmental Performance Report",
        "description": "Dedicated assessment of Green Code computational efficiency, Cloud Infrastructure power & emissions, and Environmental supply chain compliance.",
        "category": "Environmental",
        "default_sections": [
            "executive_summary",
            "green_software_analysis",
            "cloud_carbon_emissions",
            "environmental_supplier_compliance",
            "environmental_findings_actions",
            "disclosures",
        ],
        "supported_filters": ["reporting_period"],
    },
    ReportType.SOCIAL.value: {
        "title": "Social Performance Report",
        "description": "Detailed evaluation of supplier labor standards, occupational safety, human rights compliance, and social accountability.",
        "category": "Social",
        "default_sections": [
            "executive_summary",
            "social_risk_distribution",
            "labor_and_human_rights_compliance",
            "social_findings_actions",
            "disclosures",
        ],
        "supported_filters": ["reporting_period"],
    },
    ReportType.GOVERNANCE.value: {
        "title": "Governance Performance Report",
        "description": "Audit of corporate policy baseline alignment, regulatory compliance certificates (ISO 9001/14001/27001), document expiry health, and governance gaps.",
        "category": "Governance",
        "default_sections": [
            "executive_summary",
            "policy_baseline_status",
            "compliance_certificate_register",
            "governance_findings_actions",
            "disclosures",
        ],
        "supported_filters": ["reporting_period"],
    },
    ReportType.SUPPLIER_RISK.value: {
        "title": "Supplier Risk and Compliance Report",
        "description": "In-depth supply chain risk register detailing tier, geography, ISO 31000 risk scores, unassessed status tracking, and document verification.",
        "category": "Supply Chain",
        "default_sections": [
            "executive_summary",
            "supplier_risk_summary",
            "supplier_compliance_register",
            "expiring_compliance_evidence",
            "disclosures",
        ],
        "supported_filters": ["reporting_period", "category"],
    },
    ReportType.FINDINGS_RECOMMENDATIONS.value: {
        "title": "Findings and Recommendations Report",
        "description": "Comprehensive corrective action plan and prioritized risk register across all platform modules.",
        "category": "Audit & Compliance",
        "default_sections": [
            "executive_summary",
            "priority_findings_register",
            "corrective_action_roadmap",
            "disclosures",
        ],
        "supported_filters": ["reporting_period", "category"],
    },
}


def get_available_report_types() -> List[ReportTypeDefinition]:
    """Return catalog of available report templates and supported sections."""
    return [
        ReportTypeDefinition(
            id=key,
            title=meta["title"],
            description=meta["description"],
            category=meta["category"],
            default_sections=meta["default_sections"],
            supported_filters=meta["supported_filters"],
        )
        for key, meta in REPORT_DEFINITIONS.items()
    ]


# ─── Report Data Compilation (Strict Tenant Isolation) ────────────────────────

async def compile_report_data(
    db: Session,
    org_id: int,
    user: User,
    req: ReportGenerateRequest,
) -> ReportDataResponse:
    """Aggregate, filter, and structure enterprise data for preview and PDF export."""
    now = datetime.now(timezone.utc)
    report_type_val = req.report_type.value if isinstance(req.report_type, ReportType) else str(req.report_type)
    meta = REPORT_DEFINITIONS.get(report_type_val, REPORT_DEFINITIONS[ReportType.ENTERPRISE_SUMMARY.value])

    # 1. Tenant Organization & Period
    org = db.query(Organization).filter(Organization.id == org_id).first()
    org_name = org.name if org else "Enterprise Tenant"
    active_period = req.reporting_period or (org.reporting_period if org else "FY 2025–26")

    # 2. Live Multi-Member Dashboard Aggregation Base
    category_param = None if req.category in (None, "All", "all") else req.category
    dash = await aggregate_dashboard_metrics(
        db=db,
        org_id=org_id,
        category=category_param,
        reporting_period=active_period,
    )

    # 3. Query Detailed Tenant Entities
    suppliers = db.query(Supplier).filter(Supplier.organization_id == org_id).all()
    supplier_ids = [s.id for s in suppliers]

    docs = (
        db.query(SupplierDocument)
        .filter(SupplierDocument.supplier_id.in_(supplier_ids))
        .all()
        if supplier_ids
        else []
    )

    findings = (
        db.query(SupplierFinding)
        .filter(SupplierFinding.supplier_id.in_(supplier_ids), SupplierFinding.status != "Resolved")
        .all()
        if supplier_ids
        else []
    )

    # Filter findings and recommendations by category if applicable
    target_category = category_param.capitalize() if category_param else None
    if target_category and target_category != "All":
        findings = [f for f in findings if (f.category or "").capitalize() == target_category]

    # 4. Synthesize Executive Summary
    exec_summary = _generate_executive_summary(report_type_val, org_name, active_period, dash, req.notes)

    # 5. Build Report Sections
    chosen_sections = req.include_sections or req.sections
    sections = _build_report_sections(report_type_val, dash, suppliers, docs, findings, org, active_period, chosen_sections)

    # 6. Formal Data Provenance Disclosures & Limitations
    disclosures = [
        f"Tenant Boundary: All metrics and entity records are strictly scoped to organization tenant boundary ID #{org_id} ({org_name}).",
        f"Data Provenance: Metric data aggregated across Member 1 (Document Intelligence), Member 2 (Policy Risk Engine), Member 3 (Green Software), Member 4 (Cloud Carbon), and Member 5 (Supplier Registry).",
        "Supplier & Document Lifecycle: Supplier profiles and verified compliance evidence in the platform database reflect current lifecycle status; historical fiscal-year partitioning is not supported for these records.",
        "Cloud Infrastructure Emissions: Member 4 emissions data is calculated from active workload export sessions and does not represent historical multi-year records.",
        "Corporate Policy Alignment: Member 2 is a stateless policy comparison service; un-evaluated policy documents are honestly reported as NOT_EVALUATED with null scores.",
        "Risk Classification Integrity: Suppliers without completed evaluations are strictly classified as NOT_ASSESSED and are never collapsed into Low risk.",
    ]

    report_id = f"REP-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    return ReportDataResponse(
        report_id=report_id,
        report_type=report_type_val,
        title=meta["title"],
        organization_id=org_id,
        organization_name=org_name,
        reporting_period=active_period,
        generated_at=now,
        generated_by_user=user.username or user.email,
        generated_by_role=(user.role or "viewer").upper(),
        executive_summary=exec_summary,
        kpi_summary=dash.kpi_scores,
        sections=sections,
        disclosures_and_limitations=disclosures,
    )


# ─── Executive Summary Generators ─────────────────────────────────────────────

def _generate_executive_summary(
    report_type: str,
    org_name: str,
    period: str,
    dash: Any,
    user_notes: Optional[str] = None,
) -> str:
    sup = dash.suppliers
    avg_score_str = f"{sup.average_esg_score}/100" if sup.average_esg_score is not None else "Pending Assessment"

    base_summary = ""
    if report_type == ReportType.ENTERPRISE_SUMMARY.value:
        base_summary = (
            f"This executive ESG summary report provides a unified sustainability performance overview for {org_name} "
            f"for reporting period {period}. The supply chain encompasses {sup.total_suppliers} tracked suppliers, "
            f"with {sup.assessed_count} formally assessed (average ESG benchmark of {avg_score_str}) and "
            f"{sup.not_assessed_count} unassessed suppliers. Digital infrastructure analysis tracks "
            f"{dash.green_software.analyzed_prs_count} green code repository evaluations and active cloud infrastructure power metrics. "
            f"{len(dash.priority_findings)} priority compliance findings and {len(dash.recommendations)} strategic recommendations "
            f"are flagged for executive remediation."
        )
    elif report_type == ReportType.ENVIRONMENTAL.value:
        green_score_str = f"{dash.green_software.average_green_score}/100" if dash.green_software.average_green_score is not None else "Pending Analysis"
        emissions_str = f"{dash.cloud_carbon.total_estimated_kg_co2e:,.1f} kg CO2e" if dash.cloud_carbon.total_estimated_kg_co2e is not None else "No Active Session"
        base_summary = (
            f"This Environmental Performance Report details {org_name}'s computational efficiency and environmental footprint "
            f"for {period}. Green Software static analysis reports an average repository score of {green_score_str} "
            f"with {dash.green_software.high_priority_findings_count} high-priority compute bottlenecks. Cloud infrastructure "
            f"emissions from active workload exports report {emissions_str} with {dash.cloud_carbon.anomaly_count} utilization anomalies."
        )
    elif report_type == ReportType.SOCIAL.value:
        base_summary = (
            f"This Social Performance Report audits human rights, occupational health and safety, and labor standards across "
            f"{org_name}'s supply chain for {period}. A total of {sup.total_suppliers} supplier partners were reviewed, "
            f"identifying {sup.high_or_critical_count} critical/high social risk flags and tracking workforce compliance certifications."
        )
    elif report_type == ReportType.GOVERNANCE.value:
        pol_status = dash.policy_checker.data_status
        base_summary = (
            f"This Governance Performance Report audits corporate compliance, regulatory alignment, and policy adherence for "
            f"{org_name} ({period}). Enterprise baseline policy configuration status: "
            f"{'Configured (' + (dash.policy_checker.baseline_policy_name or '') + ')' if dash.policy_checker.baseline_configured else 'Awaiting Configuration'}. "
            f"Policy evaluation comparison status is {pol_status}. {sup.total_documents_count} compliance certificates are monitored, "
            f"with {sup.expiring_documents_count} requiring renewal within 30 days."
        )
    elif report_type == ReportType.SUPPLIER_RISK.value:
        base_summary = (
            f"This Supplier Risk and Compliance Report provides an in-depth ISO 31000 screening register for {org_name}'s "
            f"{sup.total_suppliers} suppliers ({period}). Risk distribution reflects {dash.risk_overview.get('Critical', 0)} Critical, "
            f"{dash.risk_overview.get('High', 0)} High, {dash.risk_overview.get('Medium', 0)} Moderate, "
            f"{dash.risk_overview.get('Low', 0)} Low, and {dash.risk_overview.get('NOT_ASSESSED', 0)} Unassessed suppliers. "
            f"Unassessed suppliers require onboarding audit evidence before formal scoring."
        )
    elif report_type == ReportType.FINDINGS_RECOMMENDATIONS.value:
        base_summary = (
            f"This audit register consolidates all open discrepancy findings and corrective action recommendations across "
            f"Members 1–5 for {org_name} ({period}). A total of {len(dash.priority_findings)} priority findings are active, "
            f"accompanied by {len(dash.recommendations)} concrete mitigation roadmap items."
        )

    if user_notes:
        base_summary += f"\n\nExecutive Notes: {user_notes.strip()}"
    return base_summary


# ─── Report Section Builders ──────────────────────────────────────────────────

def _build_report_sections(
    report_type: str,
    dash: Any,
    suppliers: List[Supplier],
    docs: List[SupplierDocument],
    findings: List[SupplierFinding],
    org: Optional[Organization],
    period: str,
    custom_sections: Optional[List[str]] = None,
) -> List[ReportSectionData]:
    sections: List[ReportSectionData] = []
    sup = dash.suppliers

    def should_include(section_key: str) -> bool:
        if not custom_sections:
            return True
        return section_key in custom_sections

    # 1. Executive Summary
    if should_include("executive_summary"):
        sections.append(
            ReportSectionData(
                key="executive_summary",
                title="1. Executive Summary",
                content_type="text",
                text_content=_generate_executive_summary(report_type, org.name if org else "Enterprise", period, dash),
            )
        )

    # 2. KPI Overview
    if should_include("kpi_overview"):
        kpi_rows = []
        for k in dash.kpi_scores:
            score_disp = f"{k.score:.1f}" if k.score is not None else "Pending Assessment"
            kpi_rows.append([k.label, score_disp, k.status, k.source, k.methodology])
        sections.append(
            ReportSectionData(
                key="kpi_overview",
                title="2. Key Sustainability Performance Indicators",
                content_type="table",
                table_headers=["Metric", "Score / Value", "Status", "Source Module", "Methodology"],
                table_rows=kpi_rows,
                note="Scores are calculated on a 0–100 scale where applicable. Missing metrics are designated as Pending Assessment.",
            )
        )

    # 3. Supplier Risk Summary
    if should_include("supplier_risk_distribution") or should_include("supplier_risk_summary"):
        risk_rows = [
            ["Critical Severity", str(dash.risk_overview.get("Critical", 0)), "Immediate procurement freeze & audit review"],
            ["High Severity", str(dash.risk_overview.get("High", 0)), "Executive review & 30-day corrective action plan"],
            ["Moderate Severity", str(dash.risk_overview.get("Medium", 0)), "Quarterly compliance monitoring & documentation renewal"],
            ["Low Severity", str(dash.risk_overview.get("Low", 0)), "Standard operational monitoring"],
            ["NOT ASSESSED (Pending)", str(dash.risk_overview.get("NOT_ASSESSED", 0)), "Collect onboarding self-assessment & compliance evidence"],
        ]
        sections.append(
            ReportSectionData(
                key="supplier_risk_distribution",
                title="Supply Chain ISO 31000 Risk Distribution",
                content_type="table",
                table_headers=["Risk Classification", "Supplier Count", "Recommended Governance Action"],
                table_rows=risk_rows,
                note="Unassessed suppliers are strictly isolated and never classified as Low risk.",
            )
        )

    # 4. Detailed Supplier Register
    if should_include("supplier_compliance_register"):
        sup_rows = []
        for s in suppliers[:25]:
            r_score_str = f"{s.risk_score:.1f}" if s.risk_score is not None else "—"
            last_date_str = s.last_assessment_date.strftime("%Y-%m-%d") if s.last_assessment_date else "Never Assessed"
            sup_rows.append([s.code, s.name, s.category, s.tier, s.country, r_score_str, s.risk_level, last_date_str])

        sections.append(
            ReportSectionData(
                key="supplier_compliance_register",
                title="Supplier Profile & Risk Register",
                content_type="table",
                table_headers=["Code", "Supplier Name", "Category", "Tier", "Country", "Risk Score", "Risk Level", "Last Assessment"],
                table_rows=sup_rows,
                note=f"Showing top {len(sup_rows)} of {len(suppliers)} verified suppliers under tenant boundary.",
            )
        )

    # 5. Compliance Document Register
    if should_include("compliance_certificate_register") or should_include("expiring_compliance_evidence"):
        doc_rows = []
        now = datetime.now(timezone.utc)
        for d in docs[:25]:
            exp_str = d.expiry_date.strftime("%Y-%m-%d") if d.expiry_date else "No Expiry"
            status_str = d.verification_status
            if d.expiry_date:
                exp_tz = d.expiry_date.replace(tzinfo=timezone.utc) if d.expiry_date.tzinfo is None else d.expiry_date
                if exp_tz < now:
                    status_str = "EXPIRED"
                elif (exp_tz - now).days <= 30:
                    status_str = "EXPIRING SOON"
            doc_rows.append([str(d.supplier_id), d.document_type, d.document_category, d.title[:35], exp_str, status_str])

        sections.append(
            ReportSectionData(
                key="compliance_certificate_register",
                title="Compliance Evidence & Certification Register",
                content_type="table",
                table_headers=["Supplier ID", "Document Type", "Category", "Title", "Expiry Date", "Verification Status"],
                table_rows=doc_rows,
                note=f"Audited {len(docs)} compliance documents. {sup.expiring_documents_count} documents are expiring within 30 days.",
            )
        )

    # 6. Green Software & Digital Infrastructure
    if should_include("green_software_analysis") or should_include("digital_infrastructure"):
        grn = dash.green_software
        cc = dash.cloud_carbon
        infra_rows = [
            ["Member 3: Green Software Intelligence", grn.service_status, f"{grn.analyzed_prs_count} PRs Evaluated", f"Avg Score: {grn.average_green_score or 'Pending'}", f"{grn.high_priority_findings_count} high-severity efficiency bottlenecks"],
            ["Member 4: Cloud & Carbon Module", cc.service_status, f"Session: {cc.data_status}", f"Emissions: {f'{cc.total_estimated_kg_co2e:,.1f} kg CO2e' if cc.total_estimated_kg_co2e is not None else 'No Active Session'}", f"{cc.anomaly_count} infrastructure utilization anomalies"],
        ]
        sections.append(
            ReportSectionData(
                key="digital_infrastructure",
                title="Digital Infrastructure & Computational Software Sustainability",
                content_type="table",
                table_headers=["Module", "Service Status", "Scope", "Performance Metric", "Key Findings"],
                table_rows=infra_rows,
                note="Cloud metrics represent the active upload export session. Green code analysis reflects static analysis repository scores.",
            )
        )

    # 7. Priority Findings Register
    if should_include("priority_findings") or should_include("priority_findings_register"):
        find_rows = []
        for f in dash.priority_findings[:20]:
            find_rows.append([f.id, f.title[:38], f.severity, f.category, f.source_module, f.description[:70]])

        sections.append(
            ReportSectionData(
                key="priority_findings",
                title="Priority ESG Compliance Findings Register",
                content_type="table",
                table_headers=["ID", "Title", "Severity", "Pillar", "Source", "Observation Summary"],
                table_rows=find_rows if find_rows else [["—", "No open discrepancy findings", "Low", "All", "Platform", "No active risk items."]],
                note=f"{len(dash.priority_findings)} open findings require operational alignment.",
            )
        )

    # 8. Strategic Recommendations
    if should_include("strategic_recommendations") or should_include("corrective_action_roadmap"):
        rec_rows = []
        for r in dash.recommendations[:15]:
            rec_rows.append([r.priority, r.category, r.title[:35], r.action[:70], r.source_module])

        sections.append(
            ReportSectionData(
                key="strategic_recommendations",
                title="Strategic Recommendations & Corrective Actions",
                content_type="table",
                table_headers=["Priority", "Pillar", "Recommendation Title", "Action Required", "Source"],
                table_rows=rec_rows if rec_rows else [["Low", "General", "Maintain Standard Compliance", "Continue regular supplier and infrastructure monitoring.", "Platform"]],
                note="Prioritized by risk severity to support executive governance and audit readiness.",
            )
        )

    return sections


# ─── ReportLab Numbered Canvas (Two-Pass Page Numbering) ──────────────────────

class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas calculating total pages, drawing running headers & footers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states: List[Dict[str, Any]] = []
        self.org_name = "Enterprise Tenant"
        self.report_title = "Enterprise ESG Report"
        self.reporting_period = "FY 2025–26"
        self.gen_timestamp = ""

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, total_pages: int):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#5b6862"))

        # Running header (pages > 1)
        if self._pageNumber > 1:
            self.drawString(36, 756, f"{self.org_name} — {self.report_title}")
            self.drawRightString(576, 756, f"Period: {self.reporting_period}")
            self.setStrokeColor(colors.HexColor("#d5ded8"))
            self.setLineWidth(0.5)
            self.line(36, 750, 576, 750)

        # Running footer
        self.setStrokeColor(colors.HexColor("#d5ded8"))
        self.setLineWidth(0.5)
        self.line(36, 36, 576, 36)
        self.drawString(36, 25, f"CONFIDENTIAL • Generated: {self.gen_timestamp} • Source: AI ESG Sustainability Platform")
        page_str = f"Page {self._pageNumber} of {total_pages}"
        self.drawRightString(576, 25, page_str)
        self.restoreState()


# ─── PDF Generation Engine (ReportLab Platypus) ───────────────────────────────

def build_report_pdf(report_data: ReportDataResponse) -> bytes:
    """Render executive multi-page PDF document using ReportLab Platypus."""
    buf = io.BytesIO()

    # Geometry: letter (8.5 x 11 in = 612 x 792 pt), 0.5-inch margins (36 pt)
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=45,
        bottomMargin=45,
    )

    styles = getSampleStyleSheet()

    # Typography & Styles
    c_primary = colors.HexColor("#153f32")
    c_secondary = colors.HexColor("#2a5c4b")
    c_muted = colors.HexColor("#5c6962")
    c_line = colors.HexColor("#e2e8e4")
    c_bg_alt = colors.HexColor("#f8faf9")

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=c_primary,
        spaceAfter=4,
    )

    sub_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=c_muted,
        spaceAfter=12,
    )

    h1_style = ParagraphStyle(
        "SectionH1",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=17,
        textColor=c_secondary,
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True,
    )

    body_style = ParagraphStyle(
        "BodyDark",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#25322c"),
        spaceAfter=6,
    )

    note_style = ParagraphStyle(
        "NoteMuted",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=7.5,
        leading=10,
        textColor=c_muted,
        spaceBefore=3,
        spaceAfter=6,
    )

    cell_style = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#222f29"),
    )

    cell_bold = ParagraphStyle(
        "TableCellBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#182b23"),
    )

    cell_header = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.white,
    )

    story: List[Any] = []

    # ── 1. Document Title & Header Banner ─────────────────────────────────────
    story.append(Paragraph("AI ESG SUSTAINABILITY PLATFORM", ParagraphStyle("Eyebrow", fontName="Helvetica-Bold", fontSize=8, textColor=c_secondary, leading=10, spaceAfter=2)))
    story.append(Paragraph(report_data.title, title_style))
    story.append(
        Paragraph(
            f"<b>Organization:</b> {report_data.organization_name} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"<b>Reporting Period:</b> {report_data.reporting_period} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"<b>Report ID:</b> {report_data.report_id}",
            sub_style,
        )
    )
    story.append(HRFlowable(width="100%", thickness=1.5, color=c_primary, spaceBefore=0, spaceAfter=10))

    # ── 2. Report Metadata Table ──────────────────────────────────────────────
    gen_time_str = report_data.generated_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    meta_data = [
        [
            Paragraph("<b>Generated By:</b>", cell_style),
            Paragraph(f"{report_data.generated_by_user} ({report_data.generated_by_role})", cell_style),
            Paragraph("<b>Date of Issuance:</b>", cell_style),
            Paragraph(gen_time_str, cell_style),
        ],
        [
            Paragraph("<b>Report Type:</b>", cell_style),
            Paragraph(report_data.report_type, cell_style),
            Paragraph("<b>Tenant Boundary:</b>", cell_style),
            Paragraph(f"Org #{report_data.organization_id} (Isolated)", cell_style),
        ],
    ]
    meta_table = Table(meta_data, colWidths=[100, 170, 100, 170])
    meta_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f3f7f5")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d5ded8")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8e4")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ])
    )
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # ── 3. Executive Summary Block ────────────────────────────────────────────
    story.append(Paragraph("1. Executive Summary", h1_style))
    story.append(Paragraph(report_data.executive_summary.replace("\n", "<br/>"), body_style))
    story.append(Spacer(1, 8))

    # ── 4. Key Performance Indicator Summary Table ────────────────────────────
    if report_data.kpi_summary:
        story.append(Paragraph("2. Top-Level Sustainability Metrics", h1_style))
        kpi_table_data = [[
            Paragraph("Metric Pillar", cell_header),
            Paragraph("Score / Metric", cell_header),
            Paragraph("Status", cell_header),
            Paragraph("Source Module", cell_header),
            Paragraph("Evaluation Methodology", cell_header),
        ]]
        for k in report_data.kpi_summary:
            score_text = f"<b>{k.score:.1f} / 100</b>" if k.score is not None else "<i>Pending Assessment</i>"
            if "emissions" in k.label.lower() and k.score is not None:
                score_text = f"<b>{k.score:,.1f} kg CO2e</b>"

            kpi_table_data.append([
                Paragraph(k.label, cell_bold),
                Paragraph(score_text, cell_style),
                Paragraph(k.status, cell_style),
                Paragraph(k.source, cell_style),
                Paragraph(k.methodology, cell_style),
            ])

        kpi_table = Table(kpi_table_data, colWidths=[120, 85, 65, 110, 160])
        kpi_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), c_primary),
                ("BOX", (0, 0), (-1, -1), 0.5, c_line),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, c_line),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, c_bg_alt]),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ])
        )
        story.append(kpi_table)
        story.append(Paragraph("Note: Missing metrics are represented strictly as Pending Assessment and are excluded from arithmetic averages.", note_style))
        story.append(Spacer(1, 10))

    # ── 5. Dynamic Report Sections ────────────────────────────────────────────
    for sec in report_data.sections:
        if sec.key in ("executive_summary", "kpi_overview"):
            continue  # Already rendered in top-level layout

        sec_flowables: List[Any] = []
        sec_flowables.append(Paragraph(sec.title, h1_style))

        if sec.text_content:
            sec_flowables.append(Paragraph(sec.text_content.replace("\n", "<br/>"), body_style))

        if sec.table_headers and sec.table_rows:
            table_data = [[Paragraph(h, cell_header) for h in sec.table_headers]]
            for row in sec.table_rows:
                table_data.append([Paragraph(str(val), cell_style) for val in row])

            num_cols = len(sec.table_headers)
            avail_width = 540  # 612 - 72
            col_width = avail_width / num_cols
            # Optimize widths for typical tables
            col_widths = [col_width] * num_cols
            if num_cols == 3:
                col_widths = [140, 90, 310]
            elif num_cols == 5:
                col_widths = [110, 85, 65, 110, 170]
            elif num_cols == 6:
                col_widths = [60, 110, 70, 70, 90, 140]
            elif num_cols == 8:
                col_widths = [50, 110, 75, 45, 55, 55, 65, 85]

            t = Table(table_data, colWidths=col_widths)
            t.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), c_secondary),
                    ("BOX", (0, 0), (-1, -1), 0.5, c_line),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, c_line),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, c_bg_alt]),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ])
            )
            sec_flowables.append(t)

        if sec.note:
            sec_flowables.append(Paragraph(sec.note, note_style))

        sec_flowables.append(Spacer(1, 10))
        story.append(KeepTogether(sec_flowables[:3]) if len(sec_flowables) >= 3 else KeepTogether(sec_flowables))

    # ── 6. Mandatory Disclosures & Limitations Box ────────────────────────────
    disc_flowables: List[Any] = []
    disc_flowables.append(Paragraph("Audit Disclosures, Data Provenance & Limitations", h1_style))
    disc_items = "".join([f"• <b>{d.split(':', 1)[0]}:</b> {d.split(':', 1)[1]}<br/>" if ":" in d else f"• {d}<br/>" for d in report_data.disclosures_and_limitations])
    disc_box = Table([[Paragraph(disc_items, ParagraphStyle("DiscBody", parent=styles["Normal"], fontName="Helvetica", fontSize=7.5, leading=11, textColor=c_muted))]], colWidths=[540])
    disc_box.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f4f7f5")),
            ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#c5d2cc")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ])
    )
    disc_flowables.append(disc_box)
    story.append(KeepTogether(disc_flowables))

    # ── 7. Build Document with NumberedCanvas ─────────────────────────────────
    def make_canvas(*args, **kwargs):
        c = NumberedCanvas(*args, **kwargs)
        c.org_name = report_data.organization_name
        c.report_title = report_data.title
        c.reporting_period = report_data.reporting_period
        c.gen_timestamp = gen_time_str
        return c

    doc.build(story, canvasmaker=make_canvas)
    return buf.getvalue()

