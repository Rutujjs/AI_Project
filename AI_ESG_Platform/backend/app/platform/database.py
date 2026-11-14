"""Database setup and session management for Member 5.

Supports PostgreSQL and local SQLite databases without external migrations.
Includes automatic table creation and initial seed data for the 4 core roles.
"""

from datetime import datetime, timezone, timedelta
import logging
from sqlalchemy import create_engine, inspect, text, event
from sqlalchemy.orm import sessionmaker, Session

from app.platform.config import (
    DATABASE_URL,
    DEFAULT_ORGANIZATION_NAME,
    DEFAULT_ORGANIZATION_SLUG,
    DEFAULT_INDUSTRY,
    DEFAULT_REPORTING_PERIOD,
)
from app.platform.models import (
    Base,
    Organization,
    Supplier,
    SupplierDocument,
    SupplierFinding,
    User,
    UserRole,
)

logger = logging.getLogger(__name__)

# Connection arguments (SQLite requires check_same_thread=False for FastAPI concurrency)
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False
    connect_args["timeout"] = 30

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    if DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency yielding an isolated database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _seed_initial_data(db: Session) -> None:
    """Idempotently seed the default organization, the 4 mandatory role users, and suppliers."""
    from app.platform.security import hash_password

    # 1. Seed Organization
    org = db.query(Organization).filter(Organization.slug == DEFAULT_ORGANIZATION_SLUG).first()
    if not org:
        org = Organization(
            name=DEFAULT_ORGANIZATION_NAME,
            slug=DEFAULT_ORGANIZATION_SLUG,
            industry=DEFAULT_INDUSTRY,
            reporting_period=DEFAULT_REPORTING_PERIOD,
        )
        db.add(org)
        db.commit()
        db.refresh(org)
        logger.info(f"Initialized default tenant organization: {org.name}")

    # 2. Seed 4 Core Role Accounts
    default_users = [
        {
            "username": "admin",
            "email": "admin@esg-intelligence.local",
            "full_name": "Platform Administrator",
            "role": UserRole.ADMIN.value,
        },
        {
            "username": "auditor",
            "email": "auditor@esg-intelligence.local",
            "full_name": "Lead ESG Auditor",
            "role": UserRole.AUDITOR.value,
        },
        {
            "username": "developer",
            "email": "developer@esg-intelligence.local",
            "full_name": "Sustainability Engineer",
            "role": UserRole.DEVELOPER.value,
        },
        {
            "username": "viewer",
            "email": "viewer@esg-intelligence.local",
            "full_name": "Executive Stakeholder",
            "role": UserRole.VIEWER.value,
        },
    ]

    for u_data in default_users:
        existing = db.query(User).filter(User.username == u_data["username"]).first()
        if not existing:
            user = User(
                organization_id=org.id,
                username=u_data["username"],
                email=u_data["email"],
                full_name=u_data["full_name"],
                role=u_data["role"],
                hashed_password=hash_password("esg2026"),
                is_active=True,
            )
            db.add(user)
    db.commit()

    # 3. Seed Default Suppliers, Documents, and Findings (idempotent per supplier code)
    if db.query(Supplier).filter(Supplier.organization_id == org.id, Supplier.code == "SUP-001").count() == 0:
        now = datetime.now(timezone.utc)
        suppliers_seed = [
            {
                "name": "Apex Components",
                "code": "SUP-001",
                "category": "Electronics & Hardware",
                "tier": "Tier 1",
                "country": "Germany",
                "contact_person": "Hans Weber",
                "contact_email": "compliance@apex-components.de",
                "contact_phone": "+49 89 2020 4011",
                "status": "Active",
                "risk_score": 16.0,
                "risk_level": "LOW",
                "environmental_score": 86.0,
                "social_score": 77.0,
                "governance_score": 84.0,
                "overall_score": 82.33,
                "last_assessment_date": now - timedelta(days=12),
                "documents": [
                    {"type": "ISO 14001", "title": "ISO 14001 Environmental Management Certificate", "expiry": now + timedelta(days=240), "status": "Verified"},
                    {"type": "ISO 45001", "title": "ISO 45001 Occupational Health & Safety", "expiry": now + timedelta(days=180), "status": "Verified"},
                    {"type": "Code of Conduct", "title": "Supplier Code of Conduct Attestation 2026", "expiry": now + timedelta(days=365), "status": "Verified"},
                ],
                "findings": [],
            },
            {
                "name": "Northstar Logistics",
                "code": "SUP-002",
                "category": "Logistics & Transport",
                "tier": "Tier 1",
                "country": "Netherlands",
                "contact_person": "Lars van Dijk",
                "contact_email": "sustainability@northstar-logistics.nl",
                "contact_phone": "+31 20 889 1200",
                "status": "Active",
                "risk_score": 36.0,
                "risk_level": "MODERATE",
                "environmental_score": 70.0,
                "social_score": 68.0,
                "governance_score": 81.0,
                "overall_score": 73.0,
                "last_assessment_date": now - timedelta(days=20),
                "documents": [
                    {"type": "Fleet Carbon Audit", "title": "Scope 1 & 2 Fleet Carbon Audit FY25", "expiry": now + timedelta(days=15), "status": "Verified"},
                    {"type": "ISO 9001", "title": "Quality Management System Certification", "expiry": now + timedelta(days=300), "status": "Verified"},
                ],
                "findings": [
                    {
                        "title": "Fleet electrification milestone behind schedule",
                        "category": "Environmental",
                        "severity": "Medium",
                        "likelihood": 3,
                        "impact": 3,
                        "risk_score": 36.0,
                        "description": "EV transition across European delivery hubs has reached 14% against the target of 30% for 2026.",
                        "recommendation": "Request a revised decarbonization roadmap with quarter-by-quarter milestone commits.",
                        "status": "Open",
                    }
                ],
            },
            {
                "name": "GreenField Packaging",
                "code": "SUP-003",
                "category": "Packaging Materials",
                "tier": "Tier 2",
                "country": "Sweden",
                "contact_person": "Elin Lindqvist",
                "contact_email": "esg@greenfield-pkg.se",
                "contact_phone": "+46 8 555 1234",
                "status": "Active",
                "risk_score": 8.0,
                "risk_level": "LOW",
                "environmental_score": 94.0,
                "social_score": 88.0,
                "governance_score": 90.0,
                "overall_score": 90.67,
                "last_assessment_date": now - timedelta(days=5),
                "documents": [
                    {"type": "FSC Chain of Custody", "title": "FSC-STD-40-004 Certified Pulp & Paper", "expiry": now + timedelta(days=400), "status": "Verified"},
                    {"type": "ISO 14001", "title": "Environmental Management Standard Certificate", "expiry": now + timedelta(days=310), "status": "Verified"},
                ],
                "findings": [],
            },
            {
                "name": "Vertex Manufacturing",
                "code": "SUP-004",
                "category": "Heavy Manufacturing",
                "tier": "Tier 1",
                "country": "Poland",
                "contact_person": "Marek Kowalski",
                "contact_email": "quality@vertex-mfg.pl",
                "contact_phone": "+48 22 411 9800",
                "status": "Under Review",
                "risk_score": 64.0,
                "risk_level": "HIGH",
                "environmental_score": 58.0,
                "social_score": 62.0,
                "governance_score": 64.0,
                "overall_score": 61.33,
                "last_assessment_date": now - timedelta(days=2),
                "documents": [
                    {"type": "SA 8000 Labour Standard", "title": "Labour Standards & Social Accountability Certificate", "expiry": now - timedelta(days=45), "status": "Expired"},
                    {"type": "ISO 14001", "title": "Environmental Management Certification", "expiry": now + timedelta(days=90), "status": "Verified"},
                ],
                "findings": [
                    {
                        "title": "Labour compliance certificate expired",
                        "category": "Social",
                        "severity": "High",
                        "likelihood": 4,
                        "impact": 4,
                        "risk_score": 64.0,
                        "description": "Labour compliance certificate expired on 30 Aug 2026 without formal renewal submission.",
                        "recommendation": "Request updated evidence and audit report; place procurement on conditional approval.",
                        "status": "Open",
                    }
                ],
            },
            {
                "name": "Orion Services",
                "code": "SUP-005",
                "category": "Facilities & IT",
                "tier": "Tier 3",
                "country": "United Kingdom",
                "contact_person": "Sarah Jenkins",
                "contact_email": "ops@orionservices.co.uk",
                "contact_phone": "+44 20 7946 0912",
                "status": "Active",
                "risk_score": 16.0,
                "risk_level": "LOW",
                "environmental_score": 81.0,
                "social_score": 76.0,
                "governance_score": 80.0,
                "overall_score": 79.0,
                "last_assessment_date": now - timedelta(days=18),
                "documents": [
                    {"type": "ISO 27001", "title": "Information Security & Data Protection Certificate", "expiry": now + timedelta(days=280), "status": "Verified"},
                    {"type": "Modern Slavery Statement", "title": "Annual Modern Slavery & Human Rights Review", "expiry": now + timedelta(days=320), "status": "Verified"},
                ],
                "findings": [],
            },
        ]

        for s_data in suppliers_seed:
            if db.query(Supplier).filter(Supplier.organization_id == org.id, Supplier.code == s_data["code"]).first():
                continue
            supplier = Supplier(
                organization_id=org.id,
                name=s_data["name"],
                code=s_data["code"],
                category=s_data["category"],
                tier=s_data["tier"],
                country=s_data["country"],
                contact_person=s_data["contact_person"],
                contact_email=s_data["contact_email"],
                contact_phone=s_data["contact_phone"],
                status=s_data["status"],
                risk_score=s_data["risk_score"],
                risk_level=s_data["risk_level"],
                environmental_score=s_data["environmental_score"],
                social_score=s_data["social_score"],
                governance_score=s_data["governance_score"],
                overall_score=s_data["overall_score"],
                last_assessment_date=s_data["last_assessment_date"],
            )
            db.add(supplier)
            db.flush()

            for doc in s_data["documents"]:
                d_obj = SupplierDocument(
                    supplier_id=supplier.id,
                    document_type=doc["type"],
                    title=doc["title"],
                    file_path=f"uploads/suppliers/seed_{supplier.id}_{doc['type'].replace(' ', '_').lower()}.pdf",
                    file_size=204800,
                    mime_type="application/pdf",
                    issue_date=now - timedelta(days=300),
                    expiry_date=doc["expiry"],
                    verification_status=doc["status"],
                )
                db.add(d_obj)

            for f_data in s_data["findings"]:
                finding = SupplierFinding(
                    supplier_id=supplier.id,
                    title=f_data["title"],
                    category=f_data["category"],
                    severity=f_data["severity"],
                    likelihood=f_data["likelihood"],
                    impact=f_data["impact"],
                    risk_score=f_data["risk_score"],
                    description=f_data["description"],
                    recommendation=f_data["recommendation"],
                    status=f_data["status"],
                    identified_date=now - timedelta(days=10),
                )
                db.add(finding)

        db.commit()
        logger.info(f"Initialized 5 default suppliers for tenant: {org.name}")



_migrations_applied = False


def _migrate_sqlite_suppliers(conn, inspector) -> None:
    """Migrate SQLite suppliers table safely via atomic table recreation."""
    # 1. Fetch pre-migration counts for verification
    pre_supplier_count = conn.execute(text("SELECT count(*) FROM suppliers;")).scalar()
    pre_doc_count = conn.execute(text("SELECT count(*) FROM supplier_documents;")).scalar()
    pre_finding_count = conn.execute(text("SELECT count(*) FROM supplier_findings;")).scalar()

    # 2. Map existing findings per supplier to detect and preserve ambiguous records
    finding_rows = conn.execute(text("SELECT supplier_id, count(*) FROM supplier_findings GROUP BY supplier_id;")).fetchall()
    finding_counts = {r[0]: r[1] for r in finding_rows}

    # 3. Disable foreign keys during table replacement
    conn.execute(text("PRAGMA foreign_keys = OFF;"))

    # 4. Create new suppliers table with nullable risk_score and default 'NOT_ASSESSED'
    conn.execute(text("""
        CREATE TABLE suppliers__new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            code VARCHAR(50) NOT NULL,
            category VARCHAR(100) NOT NULL DEFAULT 'Manufacturing',
            tier VARCHAR(20) NOT NULL DEFAULT 'Tier 1',
            country VARCHAR(100) NOT NULL DEFAULT 'Germany',
            contact_person VARCHAR(255),
            contact_email VARCHAR(255) NOT NULL,
            contact_phone VARCHAR(50),
            status VARCHAR(50) NOT NULL DEFAULT 'Active',
            risk_score FLOAT,
            risk_level VARCHAR(50) NOT NULL DEFAULT 'NOT_ASSESSED',
            environmental_score FLOAT NOT NULL DEFAULT 80.0,
            social_score FLOAT NOT NULL DEFAULT 80.0,
            governance_score FLOAT NOT NULL DEFAULT 80.0,
            overall_score FLOAT NOT NULL DEFAULT 80.0,
            last_assessment_date DATETIME,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        );
    """))

    # 5. Build migrated records preserving assessed records and reporting ambiguous legacy records
    existing_rows = conn.execute(text("""
        SELECT id, organization_id, name, code, category, tier, country,
               contact_person, contact_email, contact_phone, status,
               risk_score, risk_level, environmental_score, social_score,
               governance_score, overall_score, last_assessment_date,
               created_at, updated_at
        FROM suppliers ORDER BY id;
    """)).fetchall()

    migrated_rows = []
    for row in existing_rows:
        s_id = row[0]
        r_score = row[11]
        r_level = row[12]
        last_assess = row[17]
        has_findings = finding_counts.get(s_id, 0) > 0

        is_assessed = (last_assess is not None)
        has_assessment_data = (
            (r_score is not None and r_score > 0.0)
            or (r_level not in ("LOW", "NOT_ASSESSED", ""))
            or has_findings
        )

        if not is_assessed and has_assessment_data:
            logger.warning(
                f"Ambiguous legacy supplier record detected (id={s_id}, name='{row[2]}'): "
                f"last_assessment_date is NULL but score={r_score}, level='{r_level}', "
                f"findings={finding_counts.get(s_id, 0)}. Preserving assessment data."
            )
            new_score = r_score
            new_level = r_level
        elif not is_assessed and not has_assessment_data:
            new_score = None
            new_level = "NOT_ASSESSED"
        else:
            new_score = r_score
            new_level = r_level

        new_row = list(row)
        new_row[11] = new_score
        new_row[12] = new_level
        migrated_rows.append(tuple(new_row))

    for m_row in migrated_rows:
        conn.execute(
            text("""
                INSERT INTO suppliers__new (
                    id, organization_id, name, code, category, tier, country,
                    contact_person, contact_email, contact_phone, status,
                    risk_score, risk_level, environmental_score, social_score,
                    governance_score, overall_score, last_assessment_date,
                    created_at, updated_at
                ) VALUES (
                    :id, :org_id, :name, :code, :cat, :tier, :country,
                    :cp, :ce, :cph, :status,
                    :r_score, :r_level, :e_score, :s_score,
                    :g_score, :o_score, :last_assess,
                    :created, :updated
                );
            """),
            {
                "id": m_row[0],
                "org_id": m_row[1],
                "name": m_row[2],
                "code": m_row[3],
                "cat": m_row[4],
                "tier": m_row[5],
                "country": m_row[6],
                "cp": m_row[7],
                "ce": m_row[8],
                "cph": m_row[9],
                "status": m_row[10],
                "r_score": m_row[11],
                "r_level": m_row[12],
                "e_score": m_row[13],
                "s_score": m_row[14],
                "g_score": m_row[15],
                "o_score": m_row[16],
                "last_assess": m_row[17],
                "created": m_row[18],
                "updated": m_row[19],
            },
        )

    # 6. Swap tables
    conn.execute(text("DROP TABLE suppliers;"))
    conn.execute(text("ALTER TABLE suppliers__new RENAME TO suppliers;"))

    # 7. Recreate indexes
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_suppliers_id ON suppliers (id);"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_suppliers_organization_id ON suppliers (organization_id);"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_suppliers_name ON suppliers (name);"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_suppliers_code ON suppliers (code);"))

    # 8. Integrity check: Verify zero foreign key violations
    fk_violations = conn.execute(text("PRAGMA foreign_key_check;")).fetchall()
    if fk_violations:
        raise RuntimeError(f"Database migration aborted: PRAGMA foreign_key_check detected violations: {fk_violations}")

    conn.execute(text("PRAGMA foreign_keys = ON;"))

    # 9. Verify record counts
    post_supplier_count = conn.execute(text("SELECT count(*) FROM suppliers;")).scalar()
    post_doc_count = conn.execute(text("SELECT count(*) FROM supplier_documents;")).scalar()
    post_finding_count = conn.execute(text("SELECT count(*) FROM supplier_findings;")).scalar()

    if pre_supplier_count != post_supplier_count:
        raise RuntimeError(f"Supplier count mismatch post-migration: {pre_supplier_count} -> {post_supplier_count}")
    if pre_doc_count != post_doc_count:
        raise RuntimeError(f"Supplier document count mismatch post-migration: {pre_doc_count} -> {post_doc_count}")
    if pre_finding_count != post_finding_count:
        raise RuntimeError(f"Supplier finding count mismatch post-migration: {pre_finding_count} -> {post_finding_count}")

    logger.info(f"SQLite suppliers table migrated successfully ({post_supplier_count} records preserved, 0 FK violations).")


def _run_migrations(db_engine) -> None:
    """Ensure newly added columns and updated constraints exist in existing SQLite/Postgres tables."""
    global _migrations_applied
    if _migrations_applied:
        return

    from sqlalchemy import inspect, text
    inspector = inspect(db_engine)
    table_names = inspector.get_table_names()
    dialect_name = db_engine.dialect.name

    # 1. Check organizations table for enterprise baseline columns and is_active
    if "organizations" in table_names:
        org_cols = [c["name"] for c in inspector.get_columns("organizations")]
        with db_engine.begin() as conn:
            if "baseline_policy_path" not in org_cols:
                conn.execute(text("ALTER TABLE organizations ADD COLUMN baseline_policy_path VARCHAR(500);"))
            if "baseline_policy_name" not in org_cols:
                conn.execute(text("ALTER TABLE organizations ADD COLUMN baseline_policy_name VARCHAR(255);"))
            if "is_active" not in org_cols:
                if dialect_name == "sqlite":
                    conn.execute(text("ALTER TABLE organizations ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1;"))
                else:
                    conn.execute(text("ALTER TABLE organizations ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE;"))

    # 2. Check supplier_documents table for document_category column
    if "supplier_documents" in table_names:
        doc_cols = [c["name"] for c in inspector.get_columns("supplier_documents")]
        with db_engine.begin() as conn:
            if "document_category" not in doc_cols:
                conn.execute(text("ALTER TABLE supplier_documents ADD COLUMN document_category VARCHAR(50) DEFAULT 'CERTIFICATE';"))

    # 3. Check suppliers table for risk_score nullability and risk_level default
    if "suppliers" in table_names:
        if dialect_name == "sqlite":
            with db_engine.connect() as conn:
                pragma_cols = conn.execute(text("PRAGMA table_info(suppliers);")).fetchall()
            risk_score_info = [c for c in pragma_cols if c[1] == "risk_score"]
            needs_migration = False
            if risk_score_info and risk_score_info[0][3] == 1:
                # notnull flag is 1 -> requires table recreation to make nullable
                needs_migration = True

            if needs_migration:
                with db_engine.begin() as conn:
                    _migrate_sqlite_suppliers(conn, inspector)

        elif dialect_name == "postgresql":
            supplier_cols = {c["name"]: c for c in inspector.get_columns("suppliers")}
            if "risk_score" in supplier_cols and not supplier_cols["risk_score"].get("nullable", True):
                with db_engine.begin() as conn:
                    conn.execute(text("SELECT pg_advisory_xact_lock(7429103);"))
                    conn.execute(text("ALTER TABLE suppliers ALTER COLUMN risk_score DROP NOT NULL;"))
                    conn.execute(text("ALTER TABLE suppliers ALTER COLUMN risk_level SET DEFAULT 'NOT_ASSESSED';"))
                    conn.execute(text("""
                        UPDATE suppliers
                        SET risk_score = NULL, risk_level = 'NOT_ASSESSED'
                        WHERE last_assessment_date IS NULL
                          AND risk_score = 0.0
                          AND risk_level IN ('LOW', 'NOT_ASSESSED', '')
                          AND id NOT IN (SELECT DISTINCT supplier_id FROM supplier_findings);
                    """))
                    logger.info("PostgreSQL suppliers table altered to nullable risk_score and default NOT_ASSESSED.")

    # 4. Enforce append-only immutability database triggers on audit_logs
    if "audit_logs" in table_names:
        with db_engine.begin() as conn:
            if dialect_name == "sqlite":
                conn.execute(text("""
                    CREATE TRIGGER IF NOT EXISTS trg_audit_logs_no_update
                    BEFORE UPDATE ON audit_logs
                    BEGIN
                        SELECT RAISE(ABORT, 'AuditLog records are append-only and strictly immutable.');
                    END;
                """))
                conn.execute(text("""
                    CREATE TRIGGER IF NOT EXISTS trg_audit_logs_no_delete
                    BEFORE DELETE ON audit_logs
                    BEGIN
                        SELECT RAISE(ABORT, 'AuditLog records are append-only and cannot be deleted.');
                    END;
                """))
            elif dialect_name == "postgresql":
                conn.execute(text("""
                    CREATE OR REPLACE FUNCTION trg_audit_logs_reject() RETURNS trigger AS $$
                    BEGIN
                        RAISE EXCEPTION 'AuditLog records are append-only and strictly immutable.';
                    END;
                    $$ LANGUAGE plpgsql;
                """))
                conn.execute(text("""
                    DROP TRIGGER IF EXISTS trg_audit_logs_no_mutation ON audit_logs;
                    CREATE TRIGGER trg_audit_logs_no_mutation BEFORE UPDATE OR DELETE ON audit_logs
                    FOR EACH ROW EXECUTE FUNCTION trg_audit_logs_reject();
                """))

    _migrations_applied = True


def init_db() -> None:
    """Create all platform tables and seed default accounts."""
    Base.metadata.create_all(bind=engine)
    _run_migrations(engine)
    db = SessionLocal()
    try:
        _seed_initial_data(db)
    finally:
        db.close()


# Initialize database schemas and seed accounts on import
init_db()

