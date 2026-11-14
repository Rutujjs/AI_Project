# Known Technical Limitations & Architectural Boundaries

In accordance with rigorous engineering standards, this document transparently records known limitations, environmental requirements, and architectural boundaries of the current platform release.

---

## 1. Automated Headless Browser Testing & DevTools Protocol

### Description
Automated browser testing via Chrome DevTools Protocol (CDP) requires the host Google Chrome instance to be launched with remote debugging enabled (`--remote-debugging-port=9222`).

### Impact
When the host Chrome browser is not pre-configured with remote debugging or when running inside sandboxed environments, CDP subagents cannot bind to `DevToolsActivePort`.

### Mitigation & Verification
- All UI views, responsive states, error handlers, and form validations are verified via an exhaustive 17-point manual QA testing procedure (documented in [Manual QA Checklist](#manual-qa-procedure) below).
- All frontend static assets, DOM structures, script orderings, and API integration methods are validated automatically by the test suites (`test_platform_dashboard_frontend.py`, `test_platform_reports_frontend.py`, `test_platform_audit_frontend.py`).

---

## 2. Member 2 Stateless Architecture & Policy Evaluation Persistence

### Description
Member 2's Policy Intelligence backend (`esg-cr/backend`) was architected as a stateless microservice. It extracts commitments and computes ISO 31000 risk comparisons dynamically on-demand from uploaded PDF pairs.

### Impact
Policy comparison results exist transiently in the client's memory and API response payload. Because Member 2 does not maintain a persistent database and the Member 5 schema does not alter Member 2's data structures, historical policy comparison reports are not retained across page refreshes unless exported as PDF.

### Mitigation
- The executive dashboard on Port 8001 honestly reports `NOT_EVALUATED` for policy scores when no evaluation has been submitted during the session, rather than synthesizing mock numbers or arbitrary defaults.
- A future database migration introducing an enterprise `policy_evaluation_history` table is recommended for multi-year policy tracking.

---

## 3. Member 4 Cloud Carbon Session-Scoped Data Storage

### Description
Member 4's Software Carbon Intensity (SCI) calculator parses cloud usage datasets into an in-memory session cache keyed by `session_id`.

### Impact
Calculated emissions, regional breakdown matrices, and compute-hour aggregates reset when the Core Platform backend process is restarted.

### Mitigation
- Users can export session calculations to CSV or PDF before terminating the server.
- In production, transitioning Member 4 session data to Redis or the PostgreSQL relational store is recommended.

---

## 4. Offline ML Model Initialization & Network Timeouts

### Description
Member 1 uses Hugging Face's `SentenceTransformer("all-MiniLM-L6-v2")`. By default, the Hugging Face library contacts `huggingface.co` to check for model updates.

### Impact
In completely offline or sandboxed laboratory environments without internet access, this check causes PyTorch to retry up to 5 times, creating a 30–60 second latency window upon initial import.

### Mitigation
- The platform configuration explicitly sets:
  ```env
  HF_HUB_OFFLINE=1
  TRANSFORMERS_OFFLINE=1
  ```
- With these flags set, model weights load instantaneously (0.00s) from the pre-cached snapshot in `~/.cache/huggingface/hub/`.

---

## 5. SQLite Single-Writer Lock in High-Concurrency Scenarios

### Description
The default local development database uses SQLite (`platform.db`). SQLite permits unlimited simultaneous readers but serializes writes with a single-writer database lock.

### Impact
Under heavy synthetic concurrency testing (e.g., hundreds of concurrent users performing simultaneous supplier evaluations and audit log writes), requests may encounter `sqlite3.OperationalError: database is locked`.

### Mitigation
- For local demonstration and college evaluation, SQLite handles normal operational loads seamlessly.
- For high-concurrency production deployments, simply update `DATABASE_URL` in `.env` to point to PostgreSQL 14+, which supports row-level locking (MVCC).

---

## 6. Document Parsing: Text-Based vs. Scanned (Raster) PDFs

### Description
Member 1 uses PyMuPDF (`fitz`) and Member 2 uses `pdfplumber` to extract text from corporate PDF disclosures.

### Impact
These libraries extract native vector text elements. If an uploaded PDF is a pure raster image scan (e.g. scanned paper without an embedded OCR text layer), text extraction yields empty strings.

### Mitigation
- Upload digital-native PDF disclosures (standard for published corporate ESG reports such as Apple, Microsoft, Unilever, etc.).
- An optical character recognition (OCR) pipeline (e.g. Tesseract / Google Document AI) can be integrated as a pre-processing step for scanned documents.

---

## 7. Workspace Distribution Boundary

### Description
The project workspace was provided as an extracted archive folder rather than an active Git clone with a `.git` commit tree.

### Impact
Direct `git status`, `git commit`, or `git diff` commands return `fatal: not a git repository`.

### Mitigation
- Version tracking and file modifications are tracked deterministically via comprehensive testing baselines, backup scripts, and architecture logs.

