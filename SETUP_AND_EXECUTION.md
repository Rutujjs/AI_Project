# Platform Setup, Execution & Operations Guide

This guide provides instructions for setting up, configuring, and operating the AI-Powered Enterprise ESG Sustainability Platform on Windows, Linux, and macOS systems.

---

## 1. System Requirements

### Hardware
- **Processor**: Intel Core i5 / AMD Ryzen 5 or higher (x86_64 or Apple Silicon ARM64).
- **Memory**: Minimum 4 GB RAM (8 GB recommended for simultaneous embeddings and PDF processing).
- **Disk Space**: At least 2.5 GB available space for dependencies, models, and local databases.

### Software
- **Operating System**: Windows 10/11, Ubuntu 20.04/22.04/24.04 LTS, or macOS 12+.
- **Python**: Python 3.10, 3.11, 3.12, or 3.13 installed and accessible in the system PATH.
- **PowerShell**: PowerShell 5.1+ (Windows) or PowerShell Core 7+ (cross-platform).
- **Web Browser**: Any modern browser (Google Chrome, Microsoft Edge, Mozilla Firefox, Brave, Safari).

---

## 2. Directory & Virtual Environment Topology

The project utilizes two dedicated virtual environments to isolate microservice dependencies:

```
c:\Users\poter\Downloads\AI-CP-main\
├── .venv/                                   # Virtual Environment for Member 2 Policy Microservice
├── AI_ESG_Platform/
│   └── backend/
│       └── venv/                            # Virtual Environment for Core Platform & RAG Backend
├── integrated-frontend/                     # Unified Web Frontend (served statically)
├── start_platform.bat / start_platform.ps1  # Automated Safe Launchers
└── stop_platform.bat  / stop_platform.ps1   # Safe Graceful Shutdown Managers
```

---

## 3. Fresh Machine Installation (Step-by-Step)

If deploying the repository onto a fresh computer from scratch:

### Step 3.1: Set Up Member 2 Virtual Environment (Root)
```powershell
# In the repository root:
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\pip install -r "esg-enterprise-frontend-complete (2)\esg-enterprise-frontend-complete\esg-cr\backend\requirements.txt"
```

### Step 3.2: Set Up Core Platform Virtual Environment
```powershell
# Navigate to the platform backend:
cd AI_ESG_Platform\backend
python -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\pip install -r requirements.txt
cd ..\..
```

### Step 3.3: Pre-Cache Offline Embedding Model (Sentence Transformers)
Member 1 uses `all-MiniLM-L6-v2` for vector embeddings. To ensure the platform can run 100% offline without network connectivity during evaluation:

```powershell
# Run a one-time pre-download command:
.\AI_ESG_Platform\backend\venv\Scripts\python.exe -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```
This stores the model snapshot permanently in `~/.cache/huggingface/hub/models--sentence-transformers--all-MiniLM-L6-v2`.

### Step 3.4: Configure Environment Files
Ensure `.env` exists in both backend locations:
1. `AI_ESG_Platform/backend/.env`:
   ```env
   ENVIRONMENT=development
   SECRET_KEY=esg-platform-enterprise-secret-key-2026-secure
   DATABASE_URL=sqlite:///platform_db/platform.db
   GEMINI_API_KEY=demo-gemini-api-key-2026
   HF_HUB_OFFLINE=1
   TRANSFORMERS_OFFLINE=1
   ACCESS_TOKEN_EXPIRE_MINUTES=1440
   MEMBER2_API_URL=http://localhost:8000
   ```
2. `esg-enterprise-frontend-complete (2)/esg-enterprise-frontend-complete/esg-cr/.env`:
   ```env
   PORT=8000
   GEMINI_API_KEY=demo-gemini-api-key-2026
   ```

---

## 4. Automated Platform Startup (Recommended)

### Using Windows Batch Launcher
Double-click `start_platform.bat` or open Command Prompt:
```cmd
start_platform.bat
```

### Using PowerShell Launcher
Run with execution policy bypass:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start_platform.ps1
```

### What the Orchestrator Does:
1. **Audits Ports 8000, 8001, and 5500**: Checks whether the target ports are free.
   - If an unmanaged foreign process occupies a port, the script halts safely without terminating it and displays the conflicting process ID.
   - If occupied by a previously recorded platform launcher process, it cleanly terminates the stale instance.
2. **Launches Background Microservices**:
   - Policy Intelligence on `127.0.0.1:8000`.
   - Core Platform on `127.0.0.1:8001`.
   - Unified Frontend on `127.0.0.1:5500`.
3. **Persists Process Ownership**: Writes owned process IDs to `.platform_pids.json`.
4. **Verifies Health Endpoints**: Probes HTTP status for all three services until ready.
5. **Prints Ready Summary**: Displays URLs and pre-seeded login credentials.

---

## 5. Graceful Platform Shutdown

To stop all running services cleanly without affecting other system tasks:

### Using Batch Script
Double-click `stop_platform.bat`.

### Using PowerShell Script
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\stop_platform.ps1
```

The shutdown script reads `.platform_pids.json` and terminates **strictly** the processes launched by the platform orchestrator.

---

## 6. Manual Startup (Alternative for Development)

If you prefer to run services in separate terminal windows:

### Terminal 1: Policy Intelligence Backend (Port 8000)
```powershell
cd "c:\Users\poter\Downloads\AI-CP-main\esg-enterprise-frontend-complete (2)\esg-enterprise-frontend-complete\esg-cr\backend"
..\..\..\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### Terminal 2: Core Platform Backend (Port 8001)
```powershell
cd "c:\Users\poter\Downloads\AI-CP-main\AI_ESG_Platform\backend"
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

### Terminal 3: Unified Frontend Web Client (Port 5500)
```powershell
cd "c:\Users\poter\Downloads\AI-CP-main\integrated-frontend"
python -m http.server 5500 --bind 127.0.0.1
```

Then navigate to: **`http://localhost:5500/login.html`**

---

## 7. Verification & Health Probing

You can verify all microservices via PowerShell one-liner:

```powershell
Write-Host "Policy Backend (8000):" (Invoke-RestMethod -Uri http://localhost:8000/health).status
Write-Host "Platform Backend (8001):" (Invoke-RestMethod -Uri http://localhost:8001/health).status
Write-Host "Green Software (8001):" (Invoke-RestMethod -Uri http://localhost:8001/green/health).status
Write-Host "Cloud Carbon (8001):" (Invoke-RestMethod -Uri http://localhost:8001/api/cloud-carbon/health).status
Write-Host "Frontend Server (5500):" (Invoke-WebRequest -Uri http://localhost:5500).StatusCode
```

All commands should output `ok`, `healthy`, or `200`.

---

## 8. Troubleshooting & Common Issues

| Issue | Cause | Resolution |
| :--- | :--- | :--- |
| `[CONFLICT ERROR] Port 8000 is occupied by an external process` | Another application (e.g. Docker, Node.js) is using Port 8000 | Close the conflicting process or run `.\stop_platform.ps1 -ForceUnmanaged` if safe. |
| `ValueError: No API key was provided` | `GEMINI_API_KEY` missing from `.env` | Ensure `AI_ESG_Platform/backend/.env` contains `GEMINI_API_KEY=...` (even a test key). |
| SentenceTransformer hangs on import | Hugging Face attempting online network sync | Set `$env:HF_HUB_OFFLINE="1"` and `$env:TRANSFORMERS_OFFLINE="1"` or verify cached weights exist. |
| `TypeError: Failed to fetch` in browser | Backend is offline or blocked by CORS | Ensure both Port 8000 and 8001 are running and report healthy. |
| PDF Export fails | Missing ReportLab library | Install in platform venv: `.\venv\Scripts\pip install reportlab`. |

