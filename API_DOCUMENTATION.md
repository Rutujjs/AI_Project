# Complete API Reference & Endpoint Specification

This document provides the exhaustive API specification for both microservices comprising the AI-Powered Enterprise ESG Sustainability Platform.

---

## 1. Global API Conventions

### Base URLs
- **Policy Intelligence Microservice**: `http://localhost:8000`
- **Core Platform & Intelligence Microservice**: `http://localhost:8001`
- **Unified Frontend Web Client**: `http://localhost:5500`

### Authentication Header
Endpoints requiring authentication enforce standard HTTP Bearer tokens:
```http
Authorization: Bearer <JWT_ACCESS_TOKEN>
```

### Standard HTTP Status Codes
| Status Code | Meaning | Description |
| :--- | :--- | :--- |
| `200 OK` | Success | The request succeeded and payload is returned. |
| `201 Created` | Resource Created | Resource (supplier, evaluation, user) successfully created. |
| `400 Bad Request` | Client Error | Malformed request, invalid parameters, or bad file upload. |
| `401 Unauthorized` | Authentication Error | Missing, expired, invalid, or revoked JWT token. |
| `403 Forbidden` | Authorization Error | Insufficient role permissions or deactivated account/tenant. |
| `404 Not Found` | Not Found | Resource not found or blocked by tenant boundary. |
| `422 Unprocessable`| Validation Error | Pydantic payload validation failure. |
| `500 Server Error` | Internal Error | Unhandled server exception. |

---

## 2. Policy Intelligence Microservice (Port 8000)

### 2.1 Health Check
- **Endpoint**: `GET /health`
- **Auth**: None
- **Response** (`200 OK`):
  ```json
  {
    "status": "ok"
  }
  ```

### 2.2 Extract Commitments from Policy Document
- **Endpoint**: `POST /api/extract-commitments`
- **Auth**: None
- **Request**: Multipart form-data (`file`: PDF binary)
- **Response** (`200 OK`):
  ```json
  {
    "filename": "corporate_esg_policy_2025.pdf",
    "commitments_count": 14,
    "commitments": [
      {
        "id": "c-001",
        "category": "Environmental",
        "topic": "Net Zero GHG Emissions",
        "commitment": "Reduce absolute Scope 1 and 2 emissions by 50% by 2030.",
        "target_year": 2030,
        "baseline_year": 2019,
        "metrics": "50% reduction",
        "confidence": 0.94
      }
    ]
  }
  ```

### 2.3 Side-by-Side Policy Comparison
- **Endpoint**: `POST /api/compare-policies`
- **Auth**: None
- **Request**: Multipart form-data (`old_policy`: PDF, `new_policy`: PDF)
- **Response** (`200 OK`):
  ```json
  {
    "summary": {
      "strengthened": 5,
      "weakened": 1,
      "unchanged": 8,
      "new": 3,
      "removed": 0,
      "modified": 2
    },
    "comparisons": [
      {
        "topic": "Renewable Electricity Procurement",
        "category": "Environmental",
        "status": "STRENGTHENED",
        "old_commitment": "Source 60% renewable electricity across corporate sites by 2030.",
        "new_commitment": "Source 100% certified renewable electricity globally by 2028.",
        "analysis": "Accelerated target year by 2 years and expanded scope from 60% to 100%."
      }
    ]
  }
  ```

### 2.4 ISO 31000 Risk Report
- **Endpoint**: `POST /api/risk-report`
- **Auth**: None
- **Request**: Multipart form-data (`old_policy`: PDF, `new_policy`: PDF)
- **Response** (`200 OK`):
  ```json
  {
    "standard": "ISO 31000:2018 Risk Management",
    "overall_risk_score": 68.5,
    "risk_level": "MODERATE",
    "risk_breakdown": {
      "environmental_risk": 22.0,
      "social_risk": 24.5,
      "governance_risk": 22.0
    },
    "critical_findings": [
      {
        "finding": "Weakened supplier audit periodicity from annual to biennial.",
        "severity": "HIGH",
        "likelihood": 4,
        "impact": 4,
        "iso_clause": "Clause 6.4.3 - Risk Evaluation"
      }
    ]
  }
  ```

### 2.5 Mitigation Recommendations
- **Endpoint**: `POST /api/recommendations`
- **Auth**: None
- **Request**: JSON payload with identified policy gaps
- **Response** (`200 OK`):
  ```json
  {
    "recommendations": [
      {
        "priority": "HIGH",
        "action": "Restore mandatory annual Scope 3 supplier on-site audits.",
        "framework_alignment": "GRI 308-1 / ISO 31000 Clause 6.5",
        "expected_risk_reduction": "High (-18% governance risk)"
      }
    ]
  }
  ```

---

## 3. Core Platform & Intelligence Backend (Port 8001)

### 3.1 Member 1: Document Intelligence & RAG

#### Health Check
- **Endpoint**: `GET /health`
- **Auth**: None
- **Response**: `{"status": "healthy"}`

#### Upload & Process ESG Document
- **Endpoint**: `POST /documents/upload`
- **Auth**: None
- **Request**: Multipart form-data (`file`: PDF)
- **Response** (`200 OK`):
  ```json
  {
    "filename": "apple_esg_2024.pdf",
    "chunks_created": 42,
    "vector_ids": ["c1", "c2"],
    "analysis": {
      "commitments": [...],
      "targets": [...]
    }
  }
  ```

#### Semantic Search
- **Endpoint**: `POST /documents/search`
- **Auth**: None
- **Request Body**:
  ```json
  {
    "query": "What are the Scope 1 emissions reduction targets?",
    "n_results": 3
  }
  ```
- **Response** (`200 OK`):
  ```json
  {
    "results": [
      {
        "chunk_id": "chunk_12",
        "text": "The company commits to reducing Scope 1 GHG emissions...",
        "distance": 0.28
      }
    ]
  }
  ```

#### RAG Generative Q&A
- **Endpoint**: `POST /documents/ask`
- **Auth**: None
- **Request Body**:
  ```json
  {
    "query": "Explain the water replenishment targets.",
    "n_results": 3
  }
  ```
- **Response** (`200 OK`):
  ```json
  {
    "query": "Explain the water replenishment targets.",
    "answer": "According to the uploaded disclosure, the enterprise achieved 100% water replenishment in high-stress basins...",
    "sources": ["chunk_4", "chunk_5"]
  }
  ```

---

### 3.2 Member 3: Green Software Intelligence

#### Green Software Health
- **Endpoint**: `GET /green/health`
- **Auth**: None
- **Response**: `{"status": "healthy", "module": "green_software"}`

#### Connect GitHub Account
- **Endpoint**: `POST /green/github/connect`
- **Auth**: None
- **Request Body**:
  ```json
  {
    "demo": true
  }
  ```
  *(Or provide `{"token": "ghp_..."}` for real GitHub access)*
- **Response** (`200 OK`):
  ```json
  {
    "id": 1,
    "username": "demo-enterprise-org",
    "connected_at": "2026-11-11T12:00:00Z"
  }
  ```

#### Run Green Code Analysis
- **Endpoint**: `POST /green/analysis/analyze?enrich=false`
- **Auth**: None
- **Request Body**:
  ```json
  {
    "repository_id": 1,
    "pr_number": 42
  }
  ```
- **Response** (`200 OK`):
  ```json
  {
    "analysis_id": 1,
    "green_code_score": 78.4,
    "dimensions": {
      "network": 85.0,
      "database": 70.0,
      "compute": 80.0,
      "caching": 65.0,
      "cicd": 90.0,
      "code_quality": 80.0
    },
    "findings_count": 4,
    "findings": [
      {
        "file": "services/export.py",
        "line": 45,
        "rule": "repeated_api_calls",
        "severity": "HIGH",
        "description": "Repeated network query detected inside loop without caching."
      }
    ]
  }
  ```

---

### 3.3 Member 4: Cloud Carbon & SCI Intelligence

#### Cloud Carbon Health
- **Endpoint**: `GET /api/cloud-carbon/health`
- **Auth**: None
- **Response**: `{"status": "healthy", "module": "cloud_carbon"}`

#### Upload Cloud Usage Dataset
- **Endpoint**: `POST /api/cloud-carbon/upload-usage`
- **Auth**: None
- **Request**: Multipart form-data (`file`: CSV/JSON with compute hours, region, instance type)
- **Response** (`200 OK`):
  ```json
  {
    "session_id": "session_8f93e2b1",
    "rows_processed": 1250,
    "providers_detected": ["AWS", "Azure"],
    "total_compute_hours": 14200.5
  }
  ```

#### Calculate SCI Emissions Breakdown
- **Endpoint**: `GET /api/cloud-carbon/emissions?session_id=session_8f93e2b1`
- **Auth**: None
- **Response** (`200 OK`):
  ```json
  {
    "total_co2e_kg": 452.8,
    "operational_emissions_kg": 380.2,
    "embodied_emissions_kg": 72.6,
    "sci_score": 0.0318,
    "unit": "kg CO2e per 1,000 API transactions",
    "regional_distribution": {
      "us-east-1": 210.5,
      "eu-west-1": 142.3,
      "ap-south-1": 100.0
    }
  }
  ```

---

### 3.4 Member 5: Enterprise Governance & Platform

#### 3.4.1 Authentication & Authorization

##### User Login
- **Endpoint**: `POST /api/auth/login`
- **Auth**: None
- **Request Body**:
  ```json
  {
    "username": "admin",
    "password": "esg2026"
  }
  ```
- **Response** (`200 OK`):
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsIn...",
    "token_type": "bearer",
    "expires_in": 86400,
    "user": {
      "id": 1,
      "username": "admin",
      "email": "admin@esgplatform.internal",
      "role": "admin",
      "organization_id": 1,
      "organization_name": "Acme Global Logistics Corp"
    }
  }
  ```

##### User Logout
- **Endpoint**: `POST /api/auth/logout`
- **Auth**: Bearer Token
- **Response** (`200 OK`):
  ```json
  {
    "status": "success",
    "message": "Successfully logged out. Token has been revoked."
  }
  ```

##### Current User Profile
- **Endpoint**: `GET /api/auth/me`
- **Auth**: Bearer Token
- **Response** (`200 OK`): Returns User Profile object.

#### 3.4.2 Supplier Management (Multi-Tenant)

##### List Suppliers
- **Endpoint**: `GET /api/suppliers?category=Raw+Materials&tier=Tier+1&page=1&page_size=10`
- **Auth**: Bearer Token (All authenticated roles)
- **Response** (`200 OK`): Paginated list of supplier records scoped to tenant.

##### Create Supplier
- **Endpoint**: `POST /api/suppliers`
- **Auth**: Bearer Token (`ADMIN`, `AUDITOR`)
- **Request Body**:
  ```json
  {
    "name": "Global Clean Energy Ltd",
    "category": "Renewable Energy",
    "tier": "Tier 1",
    "country": "Germany",
    "contact_email": "compliance@gce.de"
  }
  ```
- **Response** (`201 Created`): Created Supplier record.

##### Evaluate Supplier ESG Score
- **Endpoint**: `POST /api/suppliers/{id}/evaluate?document_id=...&policy_comparison=true`
- **Auth**: Bearer Token (`ADMIN`, `AUDITOR`)
- **Response** (`200 OK`):
  ```json
  {
    "supplier_id": 1,
    "composite_score": 85.0,
    "risk_level": "LOW",
    "iso_31000_summary": "Passed comprehensive ESG compliance audit.",
    "evaluated_at": "2026-11-11T12:00:00Z"
  }
  ```

#### 3.4.3 Unified Aggregation Dashboard
- **Endpoint**: `GET /api/platform/dashboard?period=FY+2025-26&category=Environmental`
- **Auth**: Bearer Token (All authenticated roles)
- **Response** (`200 OK`):
  ```json
  {
    "organization": {
      "id": 1,
      "name": "Acme Global Logistics Corp",
      "reporting_period": "FY 2025-26"
    },
    "kpis": {
      "overall_esg_score": 82.4,
      "supplier_count": 8,
      "high_risk_suppliers": 1,
      "green_code_score": 78.4,
      "cloud_carbon_sci": 0.0318
    },
    "member_status": {
      "document_rag": "ONLINE",
      "policy_intelligence": "ONLINE",
      "green_software": "ONLINE",
      "cloud_carbon": "ONLINE"
    },
    "policy_risk": {
      "status": "NOT_EVALUATED",
      "message": "Upload policy document pair in Policy Checker to evaluate."
    }
  }
  ```

#### 3.4.4 ESG Report Generation & PDF Export

##### List Available Report Templates
- **Endpoint**: `GET /api/platform/reports/types`
- **Auth**: Bearer Token (All authenticated roles)
- **Response** (`200 OK`): Array of supported report template schemas and section definitions.

##### Preview Structured Report Data
- **Endpoint**: `POST /api/platform/reports/preview`
- **Auth**: Bearer Token (All authenticated roles)
- **Request Body**:
  ```json
  {
    "report_type": "EXECUTIVE_SUMMARY",
    "reporting_period": "FY 2025-26",
    "esg_pillar": "ALL",
    "executive_remarks": "Annual enterprise ESG synthesis."
  }
  ```
- **Response** (`200 OK`): Structured JSON report model with metrics and sections.

##### Export Cryptographic PDF
- **Endpoint**: `POST /api/platform/reports/export-pdf`
- **Auth**: Bearer Token (All authenticated roles)
- **Headers**:
  ```http
  Accept: application/pdf
  ```
- **Response** (`200 OK`):
  - Binary application/pdf stream.
  - Header: `Content-Disposition: attachment; filename="esg-report-executive-summary-20261111.pdf"`
  - Cryptographic validation: Embedded SHA-256 integrity hash on the final page.

#### 3.4.5 Audit Logging (Append-Only)
- **Endpoint**: `GET /api/platform/audit-logs?action=USER_LOGIN&page=1&limit=50`
- **Auth**: Bearer Token (`ADMIN` and `AUDITOR` only)
- **Response** (`200 OK`):
  ```json
  {
    "total": 142,
    "page": 1,
    "items": [
      {
        "id": 1,
        "action": "USER_LOGIN",
        "entity_type": "USER",
        "entity_id": "1",
        "actor_username": "admin",
        "ip_address": "127.0.0.1",
        "created_at": "2026-11-11T12:00:00Z"
      }
    ]
  }
  ```

#### 3.4.6 Per-User Notifications
- **Endpoint**: `GET /api/platform/notifications`
- **Auth**: Bearer Token (All authenticated roles)
- **Response** (`200 OK`):
  ```json
  {
    "unread_count": 2,
    "notifications": [
      {
        "id": 10,
        "title": "Supplier ESG Score Updated",
        "message": "Global Clean Energy Ltd received a composite score of 85.0.",
        "severity": "INFO",
        "is_read": false,
        "created_at": "2026-11-11T12:00:00Z"
      }
    ]
  }
  ```
- **Mark Single Read**: `PATCH /api/platform/notifications/{id}/read`
- **Mark All Read**: `POST /api/platform/notifications/mark-all-read`

