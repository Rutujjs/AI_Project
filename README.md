# AI-Powered Enterprise ESG Sustainability Platform

[![Platform Version](https://img.shields.io/badge/version-2.0.0-blue.svg)](https://github.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.10%20|%203.11%20|%203.12%20|%203.13-3776AB.svg)](https://python.org)
[![Security Audited](https://img.shields.io/badge/Security-PBKDF2%20|%20RBAC%20|%20HS256-green.svg)](DATABASE_SCHEMA.md)
[![Test Suite](https://img.shields.io/badge/Tests-274%20Total%20|%20149%20Baseline%20Passing-brightgreen.svg)](TESTING_REPORT.md)

A production-grade, collaborative enterprise platform designed to analyze, score, benchmark, and report environmental, social, and corporate governance (ESG) metrics. Combines deep document RAG intelligence, automated ISO 31000 policy risk comparison, green code static analysis, cloud carbon SCI accounting, and enterprise multi-tenant audit governance into a unified, responsive interface.

---

## 1. Project Overview & Module Ownership

The platform brings together five specialized engineering modules developed across team members:

| Module | Member | Primary Responsibilities | Core Technologies | Service Port |
| :--- | :--- | :--- | :--- | :--- |
| **Document Intelligence & RAG** | **Member 1** | ESG PDF parsing, chunking, local vector embeddings, ChromaDB retrieval, generative RAG Q&A | FastAPI, PyMuPDF, `sentence-transformers` (`all-MiniLM-L6-v2`), ChromaDB, Gemini LLM | **8001** |
| **Policy Intelligence & Risk** | **Member 2** | Side-by-side policy diffing, commitment extraction, ISO 31000 risk scoring, recommendations | FastAPI, PDFPlumber, ISO 31000 Risk Engine, Gemini LLM / Heuristic Fallbacks | **8000** |
| **Green Software Intelligence** | **Member 3** | Code repository scanning, AST static efficiency analysis, Green Code Scorer across 6 dimensions | FastAPI, AST Visitor, GitHub REST API, SQLite, Optional Ruff/ESLint | **8001** |
| **Cloud Carbon & SCI** | **Member 4** | Cloud infrastructure emissions modeling, Software Carbon Intensity (SCI) calculation, cloud provider coefficients | FastAPI, SCI Standards, Cloud Provider Baselines, Session Cache | **8001** |
| **Enterprise Platform & Governance** | **Member 5** | Authentication, RBAC, multi-tenancy, supplier ESG scoring, unified dashboard, PDF report export, append-only audit logging, per-user notifications | FastAPI, SQLAlchemy, SQLite/PostgreSQL, PBKDF2-HMAC-SHA256, JWT (HS256), ReportLab | **8001** & **5500** |

---

## 2. Microservices Architecture & Ports

The platform runs as a coordinated dual-backend microservices cluster served by a unified web client:

```
                            [ Web Browser ]
                         http://localhost:5500
                                   │
                 ┌─────────────────┴─────────────────┐
                 │                                   │
      (Policy API Requests)                (Platform & Intel APIs)
                 │                                   │
                 ▼                                   ▼
    ┌─────────────────────────┐         ┌─────────────────────────┐
    │  Member 2 Policy Engine │         │  Core Platform Backend  │
    │  http://localhost:8000  │         │  http://localhost:8001  │
    ├─────────────────────────┤         ├─────────────────────────┤
    │ • /health               │         │ • /health               │
    │ • /api/compare-policies │         │ • /documents/* (M1)     │
    │ • /api/extract-commit...│         │ • /green/*     (M3)     │
    │ • /api/risk-report      │         │ • /api/cloud-carbon/*   │
    │ • /api/recommendations  │         │ • /api/auth/*  (M5)     │
    └─────────────────────────┘         │ • /api/platform/* (M5)  │
                                        └─────────────────────────┘
```

- **Port 5500 (`http://localhost:5500`)**: Unified Web Frontend (Vanilla ES6 JavaScript, HTML5, CSS3, zero external NPM bundler dependencies).
- **Port 8000 (`http://localhost:8000`)**: Member 2 Policy Intelligence & ISO 31000 Microservice (`esg-cr/backend`).
- **Port 8001 (`http://localhost:8001`)**: Core Platform, RAG, Green Code, Cloud Carbon, and Governance Backend (`AI_ESG_Platform/backend`).

---

## 3. Quick Start & Execution

### One-Click Startup (Windows)
Double-click `start_platform.bat` or run in PowerShell:

```powershell
.\start_platform.ps1
```

The orchestrator executes safely:
1. Audits ports 8000, 8001, and 5500. **Guaranteed safe**: Never terminates unmanaged external processes; checks `.platform_pids.json` and only cleans up previously owned launcher instances.
2. Resolves virtual environments (`.venv` and `AI_ESG_Platform\backend\venv`).
3. Launches Policy Backend (8000), Core Platform Backend (8001), and Frontend Server (5500).
4. Performs live health checks against `http://localhost:8000/health`, `http://localhost:8001/health`, and `http://localhost:5500`.
5. Logs active Process IDs to `.platform_pids.json` for deterministic tracking.

### Graceful One-Click Shutdown
Double-click `stop_platform.bat` or run in PowerShell:

```powershell
.\stop_platform.ps1
```
Stops **only** the processes registered in `.platform_pids.json` and cleanly removes the tracking file.

---

## 4. Pre-Seeded Development Demo Accounts

The platform comes pre-seeded with four role accounts for demonstration:

| Username | Password | Role | Permissions & Access Scope |
| :--- | :--- | :--- | :--- |
| `admin` | `esg2026` | **ADMIN** | Unrestricted access: Supplier CRUD, Evaluation, Audit Logs, Settings, User Provisioning, System Reports |
| `auditor` | `esg2026` | **AUDITOR** | Read-only compliance access: View Suppliers, View Evaluations, Full Audit Log Inspection, Read Reports |
| `developer` | `esg2026` | **DEVELOPER** | Engineering access: Green Code Intelligence, Cloud Carbon SCI modeling, Document RAG Q&A |
| `viewer` | `esg2026` | **VIEWER** | Read-only general access: Platform Executive Dashboard, High-level ESG metrics |

---

## 5. Live Service Health Checks & Swagger Endpoints

| Service | Health Check URL | Expected Response | Interactive API Docs |
| :--- | :--- | :--- | :--- |
| **Policy Intelligence** | `http://localhost:8000/health` | `{"status":"ok"}` | `http://localhost:8000/docs` |
| **Core Platform** | `http://localhost:8001/health` | `{"status":"healthy"}` | `http://localhost:8001/docs` |
| **Green Software** | `http://localhost:8001/green/health` | `{"status":"healthy","module":"green_software"}` | Included in 8001 Swagger |
| **Cloud Carbon SCI** | `http://localhost:8001/api/cloud-carbon/health` | `{"status":"healthy","module":"cloud_carbon"}` | Included in 8001 Swagger |
| **Unified Frontend** | `http://localhost:5500/` | HTTP 200 (HTML) | `http://localhost:5500/login.html` |

---

## 6. Project Documentation Index

Comprehensive engineering documents are located in the repository root:

- [Project Architecture & Microservices](PROJECT_ARCHITECTURE.md) — Comprehensive technical architecture, data flow, and module boundaries.
- [Complete API Documentation](API_DOCUMENTATION.md) — Exhaustive REST API specification for Port 8000 and Port 8001.
- [Database Schema & ERD](DATABASE_SCHEMA.md) — Relational schemas, ChromaDB vector store, constraints, triggers, and indices.
- [Setup & Execution Guide](SETUP_AND_EXECUTION.md) — Detailed manual and automated execution steps across Windows and Linux.
- [Environment Variables Reference](ENVIRONMENT_VARIABLES.md) — Complete environment configuration dictionary and production rules.
- [Testing & Quality Assurance Report](TESTING_REPORT.md) — Test suite results, regression methodology, and coverage analysis.
- [Production Deployment Guide](DEPLOYMENT_GUIDE.md) — Containerized deployment, reverse proxy setup, and PostgreSQL migration.
- [Known Limitations & Architecture Notes](KNOWN_LIMITATIONS.md) — Transparent disclosure of headless limitations, stateless boundaries, and session scopes.
- [College Demonstration Script](DEMONSTRATION_GUIDE.md) — 15-minute step-by-step evaluator presentation guide.

---

## 7. License & Academic Attribution
Developed as an advanced collaborative engineering project. All rights reserved by the respective contributing authors.
