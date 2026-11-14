# Environment Variables Reference & Configuration Guide

This document defines all configuration settings and environment variables across the AI-Powered Enterprise ESG Sustainability Platform.

---

## 1. Configuration Architecture & Precedence

The platform loads configuration using the following hierarchical precedence (highest to lowest):
1. **Explicit Operating System Environment Variables** (e.g. set via Docker, Kubernetes, or shell `$env:VAR`).
2. **Local Environment Files** (`.env` in each backend root directory).
3. **Internal Hardcoded Safe Defaults** (designed strictly for local development).

Both backends include comprehensive `.env.example` templates that can be copied directly to `.env`.

---

## 2. Core Platform Backend (`AI_ESG_Platform/backend/.env`)

| Variable | Type | Default Value | Description & Production Rules |
| :--- | :--- | :--- | :--- |
| `ENVIRONMENT` | String | `development` | Environment mode (`development`, `staging`, `production`). In `production`, strict security guards activate. |
| `SECRET_KEY` | String | `esg-platform-enterprise-secret-key-2026-secure` | Master cryptographic key used for HS256 JWT signature verification. In `production`, **must** be at least 32 characters long with high entropy. |
| `JWT_SECRET` | String | *(Same as SECRET_KEY)* | Alias for `SECRET_KEY`. |
| `JWT_ALGORITHM` | String | `HS256` | Cryptographic algorithm used to sign access tokens. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Integer | `1440` | JWT expiration duration in minutes (1440 min = 24 hours). |
| `DATABASE_URL` | String | `sqlite:///platform_db/platform.db` | Primary relational database connection URI. Supports SQLite (`sqlite:///path`) and PostgreSQL (`postgresql://user:pass@host:5432/dbname`). |
| `PLATFORM_DB_PATH` | String | *(Derived from DATABASE_URL)* | Direct path override for SQLite file storage. |
| `GEMINI_API_KEY` | String | *(None)* | Google Gemini API key used for document RAG synthesis, policy analysis, and green code AI explanations. |
| `HF_HUB_OFFLINE` | Integer | `1` | Forces Hugging Face library into offline mode, preventing network latency and external calls on model import. |
| `TRANSFORMERS_OFFLINE` | Integer | `1` | Forces PyTorch Transformers into offline mode, loading weights strictly from local disk cache. |
| `MEMBER2_API_URL` | String | `http://localhost:8000` | Network URL for Member 2 Policy Intelligence microservice. |
| `DEFAULT_ORG_NAME` | String | `Acme Global Logistics Corp` | Default enterprise tenant created upon initial database seed. |
| `DEFAULT_ORG_SLUG` | String | `acme-global` | Unique URL-safe slug for the default enterprise tenant. |
| `DEFAULT_INDUSTRY` | String | `Logistics & Transportation` | Default enterprise industry classification. |
| `DEFAULT_REPORTING_PERIOD`| String | `FY 2025–26` | Default corporate fiscal reporting period. |
| `MAX_UPLOAD_SIZE_BYTES` | Integer | `20971520` | Maximum allowable file upload size (20 MB ceiling). |

---

## 3. Policy Intelligence Backend (`esg-cr/.env`)

Located at: `esg-enterprise-frontend-complete (2)/esg-enterprise-frontend-complete/esg-cr/.env`

| Variable | Type | Default Value | Description |
| :--- | :--- | :--- | :--- |
| `PORT` | Integer | `8000` | Port on which the Uvicorn ASGI server binds. |
| `GEMINI_API_KEY` | String | *(None)* | Google Gemini API key used for narrative policy commitment extraction. |
| `HUGGINGFACE_API_KEY` | String | *(Optional)* | Optional Hugging Face API key for cloud-based policy recommendation inference. |

---

## 4. Frontend LocalStorage Overrides

The unified frontend on Port 5500 can be dynamically pointed to alternative backend URLs without modifying source code via browser `localStorage` or the **Settings** view (`settings.html`):

| Key | Default Value | Description |
| :--- | :--- | :--- |
| `esg_platform_api_base` | `http://localhost:8001` | Active base URL for Platform & Intelligence APIs. |
| `esg_policy_api_base` | `http://localhost:8000` | Active base URL for Policy Intelligence APIs. |
| `esg_auth_token` | *(Dynamic JWT)* | Persisted JWT token of the currently authenticated user session. |
| `esg_user_profile` | *(JSON Object)* | Cached user profile and role details. |

---

## 5. Production Security Checklist

When deploying to a staging or production server:

1. **Set `ENVIRONMENT=production`**: Activates startup validation guards in `config.py`.
2. **Generate a High-Entropy Secret Key**:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
   Assign the resulting 64-character hex string to `SECRET_KEY`.
3. **Use Production PostgreSQL**: Configure `DATABASE_URL=postgresql://esg_user:strong_password@db.internal:5432/esg_prod`.
4. **Never Commit `.env` Files**: Verify `.env` is listed in `.gitignore`.
5. **Set Access Token Lifetime Appropriately**: Reduce `ACCESS_TOKEN_EXPIRE_MINUTES` to `60` or `120` in production environments, pairing with refresh token flows if required.

