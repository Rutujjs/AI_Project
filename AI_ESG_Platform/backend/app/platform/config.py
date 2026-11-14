"""Platform configuration settings for Member 5.

Loads environment variables with safe defaults for local development.
Supports production PostgreSQL and local SQLite databases.
"""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env if present
_BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(_BASE_DIR / ".env", override=False)

# Environment mode
ENVIRONMENT = os.getenv("ENVIRONMENT", os.getenv("ENV", "development")).lower()
INSECURE_DEFAULT_SECRET = "esg-platform-enterprise-secret-key-2026-secure"


def get_secret_key() -> str:
    """Retrieve and validate the JWT secret key.

    In production mode, raises RuntimeError if missing, insecure, or shorter than 32 characters.
    """
    env = os.getenv("ENVIRONMENT", os.getenv("ENV", "development")).lower()
    secret = os.getenv("SECRET_KEY", os.getenv("JWT_SECRET"))
    if env == "production":
        if not secret or secret == INSECURE_DEFAULT_SECRET or len(secret) < 32:
            raise RuntimeError(
                "CRITICAL SECURITY CONFIGURATION ERROR: In production environment, SECRET_KEY "
                "or JWT_SECRET must be explicitly set to a high-entropy string of at least 32 characters."
            )
        return secret
    return secret or INSECURE_DEFAULT_SECRET


# Security & JWT configuration
SECRET_KEY = get_secret_key()
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # 24 hours

# Database configuration
_DEFAULT_DB_DIR = _BASE_DIR / "platform_db"
_DEFAULT_DB_DIR.mkdir(parents=True, exist_ok=True)
_DEFAULT_SQLITE_PATH = _DEFAULT_DB_DIR / "platform.db"

# If DATABASE_URL is set (e.g. postgresql://user:pass@localhost:5432/esg), use it;
# otherwise default to local SQLite.
DATABASE_URL = os.getenv("DATABASE_URL", os.getenv("PLATFORM_DB_PATH", f"sqlite:///{_DEFAULT_SQLITE_PATH.as_posix()}"))

# Normalize postgresql:// scheme if needed (SQLAlchemy 2.0 requires postgresql+psycopg2 or postgresql://)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Platform defaults
DEFAULT_ORGANIZATION_NAME = os.getenv("DEFAULT_ORG_NAME", "Acme Global Logistics Corp")
DEFAULT_ORGANIZATION_SLUG = os.getenv("DEFAULT_ORG_SLUG", "acme-global")
DEFAULT_INDUSTRY = os.getenv("DEFAULT_INDUSTRY", "Logistics & Transportation")
DEFAULT_REPORTING_PERIOD = os.getenv("DEFAULT_REPORTING_PERIOD", "FY 2025–26")

# Member 2 Integration configuration
MEMBER2_API_URL = os.getenv("MEMBER2_API_URL", "http://localhost:8000").rstrip("/")

# File Upload Security Settings
MAX_UPLOAD_SIZE_BYTES = int(os.getenv("MAX_UPLOAD_SIZE_BYTES", str(20 * 1024 * 1024)))  # 20 MB ceiling
ALLOWED_UPLOAD_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".doc",
    ".xlsx",
    ".csv",
    ".txt",
    ".png",
    ".jpg",
    ".jpeg",
}
POLICY_DOCUMENT_CATEGORIES = {
    "Code of Conduct",
    "Environmental Policy",
    "Labour Policy",
    "Governance Policy",
    "ESG Policy",
}


