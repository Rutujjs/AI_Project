# College Evaluation Demonstration Script & Presentation Guide

This guide provides a structured, minute-by-minute walkthrough script for presenting the **AI-Powered Enterprise ESG Sustainability Platform** to academic evaluators and project review committees.

---

## 1. Demonstration Strategy & Time Allocation

| Phase | Time | Topic & Focus Area | Responsible Module |
| :--- | :---: | :--- | :--- |
| **Phase 1** | 0:00 – 2:00 | Architecture Overview, Dual-Backend Startup & Authentication | Platform Architecture |
| **Phase 2** | 2:00 – 4:30 | Document Intelligence & RAG Q&A | **Member 1** |
| **Phase 3** | 4:30 – 7:00 | Policy Comparison & ISO 31000 Risk Engine | **Member 2** |
| **Phase 4** | 7:00 – 9:00 | Green Software AST Static Analysis & Scoring | **Member 3** |
| **Phase 5** | 9:00 – 11:00 | Cloud Carbon Emissions & SCI Intensity Modeling | **Member 4** |
| **Phase 6** | 11:00 – 13:30| Enterprise Multi-Tenancy, Suppliers, Dashboard, PDF & Audit | **Member 5** |
| **Phase 7** | 13:30 – 15:00| Technical Defense, Security Verification & Evaluator Q&A | All Members |

---

## 2. Truth in Demonstration Matrix

To ensure transparency during evaluation, the following matrix distinguishes live model inference, deterministic fallbacks, and pre-seeded data:

| Feature / Action | Operational Mode | Execution Mechanism | Fallback Behavior |
| :--- | :--- | :--- | :--- |
| **Document Embeddings** | **Live AI (Local)** | Hugging Face `all-MiniLM-L6-v2` | Runs 100% offline from local disk weights |
| **Document RAG Q&A** | **Live AI (Cloud)** | Google Gemini API | Synthesizes response from retrieved ChromaDB chunks |
| **Policy Commitments** | **Live / Deterministic**| PDFPlumber extraction | Heuristic regex parser extracts commitments if Gemini is offline |
| **Policy Risk Scoring** | **Deterministic Formula**| ISO 31000 Likelihood $\times$ Impact matrix | Mathematical calculation (zero LLM dependency) |
| **Green Code AST Scan** | **Deterministic AST** | Python AST tree traversal | Scans source files locally for anti-patterns |
| **Green Code AI Insights** | **Live AI (Opt-In)** | Google Gemini API (via AI Enrichment toggle)| Skips LLM explanation if unchecked |
| **Cloud Carbon SCI** | **Deterministic Standard**| GSF Software Carbon Intensity formula | Uses standard regional grid emission factors |
| **Supplier ESG Scoring** | **Deterministic Formula**| Multi-pillar weighted scoring | Stored in relational database |
| **Audit Log Immutability**| **Database Trigger** | SQLite/Postgres `BEFORE UPDATE/DELETE` triggers | Throws security violation on tampering |
| **PDF Report Export** | **Live Generation** | ReportLab dynamic PDF builder | SHA-256 cryptographic stamp on footer |

---

## 3. Pre-Flight Preparation (Before Evaluators Arrive)

1. Open PowerShell in the project root:
   ```powershell
   cd C:\Users\poter\Downloads\AI-CP-main
   ```
2. Launch the entire platform using the safe startup orchestrator:
   ```powershell
   .\start_platform.ps1
   ```
3. Verify that all three services output `READY (HTTP 200 OK)`:
   - Policy Intelligence: `http://localhost:8000/health`
   - Platform Backend: `http://localhost:8001/health`
   - Unified Frontend: `http://localhost:5500`
4. Open Google Chrome and navigate to: **`http://localhost:5500/login.html`**

---

## 4. Minute-by-Minute Presentation Script

### Phase 1: Platform Overview & Multi-Tenant Authentication (0:00 – 2:00)

**Presenter Script:**
> *"Good morning/afternoon, evaluators. Today we present our AI-Powered Enterprise ESG Sustainability Platform. In modern enterprise operations, sustainability is no longer just marketing—it requires quantifiable engineering, automated policy compliance, green computing, and audit-grade governance.*
>
> *Our platform combines five distinct modules into a unified dual-backend microservices architecture. On Port 8000, we run a specialized Policy Intelligence engine. On Port 8001, we run our Core Platform supporting Document RAG, Green Software, Cloud Carbon, and Governance. The entire system is orchestrated via our unified web interface on Port 5500.*
>
> *Let us begin by logging in as the System Administrator."*

**Action:**
1. On `http://localhost:5500/login.html`, enter:
   - Username: `admin`
   - Password: `esg2026`
2. Click **Sign In**.
3. Point out the instant authentication: PBKDF2-HMAC-SHA256 verification and issuance of an HS256 JWT bearer token.

---

### Phase 2: Member 1 — Document Intelligence & Semantic RAG (2:00 – 4:30)

**Presenter Script:**
> *"Now we turn to Member 1's Document Intelligence and RAG module. Corporate sustainability reports are often hundreds of pages of unstructured narrative. Our system ingests these reports, extracts the text using PyMuPDF, chunks them semantically, and indexes them in a persistent ChromaDB vector store using local sentence transformers."*

**Action:**
1. Navigate to **Document Center** (`document-center.html`) from the sidebar.
2. Click **Upload Document** and select a sample ESG disclosure PDF (e.g. from `samples/` or any ESG report).
3. Point out the processing steps: text extraction, chunking, and embedding generation.
4. Go to the **Ask Questions (RAG)** tab:
   - Enter query: *"What are the enterprise targets for greenhouse gas reduction?"*
   - Click **Ask AI**.
5. Highlight how ChromaDB retrieves the top 3 most semantically relevant chunks via cosine distance, and the LLM synthesizes an exact, sourced answer with source chunk references.

---

### Phase 3: Member 2 — Policy Intelligence & ISO 31000 Risk Engine (4:30 – 7:00)

**Presenter Script:**
> *"Member 2's module solves a critical governance challenge: tracking policy drift. When enterprises update environmental or labor policies, commitments are frequently altered or weakened without clear disclosure. Member 2 extracts commitments from old and new policy versions and compares them side-by-side using an ISO 31000 risk framework."*

**Action:**
1. Navigate to **Policy Checker** (`policy-checker.html`).
2. In the upload section, select an **Original Policy PDF** and a **Revised Policy PDF**.
3. Click **Compare Policies**.
4. Review the results:
   - Status classifications: `STRENGTHENED`, `WEAKENED`, `MODIFIED`, `UNCHANGED`.
   - Point out the **ISO 31000 Risk Report**: Likelihood vs Impact severity calculation.
   - Point out the **AI / Rule-Based Recommendations** suggesting corrective actions to maintain compliance.

---

### Phase 4: Member 3 — Green Software Intelligence (7:00 – 9:00)

**Presenter Script:**
> *"Member 3 addresses Scope 2 and Scope 3 IT emissions through Green Software Engineering. Software efficiency directly correlates to data center energy consumption. Our Green Code module analyzes source code repositories to detect carbon-inefficient algorithmic patterns."*

**Action:**
1. Navigate to **Green Code** (`green-code.html`).
2. Click **Use Demo Mode** (or enter a GitHub token).
3. Select a demo repository and pull request (e.g. PR #42).
4. Click **Run Green Analysis**.
5. Walk through the findings:
   - Point out detected anti-patterns: repeated network calls inside loops, unindexed queries, missing caching.
   - Show the **Green Code Score** broken down across the 6 dimensions: Network, Database, Compute, Caching, CI/CD, and Code Quality.

---

### Phase 5: Member 4 — Cloud Carbon & SCI Intelligence (9:00 – 11:00)

**Presenter Script:**
> *"Member 4 models the enterprise cloud footprint using the Software Carbon Intensity (SCI) specification established by the Green Software Foundation. We calculate operational emissions from grid intensity and embodied emissions from hardware manufacturing."*

**Action:**
1. Navigate to **Cloud Carbon** (`cloud-carbon.html`).
2. Upload a sample cloud billing dataset (`cloud_usage_sample.csv`).
3. Click **Calculate SCI Emissions**.
4. Explain the formula displayed:
   $$\text{SCI} = \frac{(E \times I) + M}{R}$$
5. Highlight the regional distribution chart showing how shifting workloads from coal-heavy regions (e.g. `us-east-1`) to renewable grids (e.g. `eu-west-1` or `nordics`) reduces operational CO2e by over 40%.

---

### Phase 6: Member 5 — Enterprise Governance, Suppliers, Dashboard, PDF & Audit (11:00 – 13:30)

**Presenter Script:**
> *"Finally, Member 5 ties all modules together into an enterprise governance platform with strict multi-tenancy, supplier management, live dashboard aggregation, tamper-proof audit trails, and cryptographic reporting."*

**Action:**
1. **Suppliers View (`suppliers.html`)**:
   - View existing vendors. Click **Add Supplier** and create "Nordic Clean Logistics".
   - Click **Evaluate** and submit scores (E: 88, S: 82, G: 90). Show automatic tiering and low-risk classification.
2. **Executive Dashboard (`dashboard.html`)**:
   - Show live aggregation: supplier metrics, green code scores, cloud carbon intensity, and microservice health cards.
   - Point out the honest reporting: if no policy comparison was run during this session, it displays `NOT_EVALUATED` rather than fake data.
3. **Reports & PDF Export (`reports.html`)**:
   - Select **Executive Summary**, choose **FY 2025–26**, and click **Generate Preview**.
   - Click **Export to PDF**. Open the downloaded PDF in Chrome: show executive remarks, KPI tables, and the SHA-256 cryptographic verification stamp at the bottom.
4. **Audit Logs (`audit-logs.html`)**:
   - Point out the newly recorded `USER_LOGIN`, `SUPPLIER_CREATE`, and `REPORT_EXPORT_PDF` audit events.
   - Explain the database immutability triggers: in SQLite/Postgres, `UPDATE` and `DELETE` on this table are strictly blocked at the engine level.
5. **Notifications (`notifications.html`)**:
   - View threshold alert. Click **Mark as Read**. Point out that read status is tracked independently per user via the `notification_reads` association table.

---

### Phase 7: Technical Defense & Evaluator Q&A (13:30 – 15:00)

**Presenter Script:**
> *"To conclude, our platform achieves a 100% pass rate across 274 automated tests, enforces strict multi-tenant database isolation, operates fully offline using cached local embeddings and deterministic fallbacks, and tracks all background processes with zero port conflict risk.*
>
> *We are now ready for your questions and code inspection."*

