# Raphael — Dual-Uncertainty Supply Chain Inventory Engine

Production-grade demand forecasting, lead-time prediction, and inventory replenishment decision engine.

---

## Architecture Overview

- **Backend:** FastAPI, Python 3.11+, Uvicorn, SciPy, LightGBM, Prophet, scikit-learn.
- **Frontend:** Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS v4, Three.js, Recharts, Framer Motion.
- **Inventory Engine:** Pure deterministic arithmetic decision layer with dual uncertainty ($L \cdot \sigma_D^2 + D^2 \cdot \sigma_L^2$).

---

## Starting the Servers

### 1. Backend Server (FastAPI / Uvicorn)

The backend module is located in `backend/main.py`. The canonical Uvicorn target is `backend.main:app`.

#### Windows PowerShell:
```powershell
# From the repository root:
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
Or use the convenience startup script:
```powershell
.\scripts\serve.ps1
```

#### Windows Command Prompt (cmd.exe):
```cmd
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

#### Git Bash / MSYS2 / WSL:
> **Note for Bash Users:** Always use forward slashes `/` in file paths. In bash, unquoted backslashes `\` act as escape sequences.
```bash
./.venv/Scripts/python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

- **Health Check:** [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- **Interactive OpenAPI Docs:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **OpenAPI JSON Schema:** [http://127.0.0.1:8000/openapi.json](http://127.0.0.1:8000/openapi.json)

---

### 2. Frontend Dev Server (Next.js)

```bash
cd frontend
npm run dev
```

Navigate to:
- **Overview (Landing):** [http://localhost:3000](http://localhost:3000)
- **Forecast Dashboard:** [http://localhost:3000/forecast](http://localhost:3000/forecast)
- **Inventory Triage:** [http://localhost:3000/inventory](http://localhost:3000/inventory)
- **What-If Simulator:** [http://localhost:3000/simulator](http://localhost:3000/simulator)
- **Methodology & Assumptions:** [http://localhost:3000/methodology](http://localhost:3000/methodology)
- **3D Ribbon Teardown Lab:** [http://localhost:3000/lab/3d](http://localhost:3000/lab/3d)
- **Motion Lab:** [http://localhost:3000/lab/motion](http://localhost:3000/lab/motion)

---

## Running Unit Tests

### Python Backend Tests:
```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

### Frontend Inventory Arithmetic Tests:
```bash
cd frontend
npm test
```

---

## Deployment & Demo Preparation Guide

Raphael supports two operational modes:
1. **Live Cloud/Hybrid Mode:** FastAPI backend running on local PC or server, exposed via Tailscale Funnel or cloud VM, connected to Vercel frontend.
2. **Deterministic Offline Snapshot Mode:** Zero-dependency static presentation serving all 75 pairs from `frontend/public/snapshots/*.json` when the live backend is unreachable.

### 1. Run the API on this PC (Host Server)
To serve the live backend with configured CORS headers:
```powershell
# Set allowed origins (default http://localhost:3000, or your Vercel deployment URL)
$env:CORS_ORIGINS = "http://localhost:3000,https://*.vercel.app"

# Start the server using the helper script:
.\scripts\serve.ps1
```

### 2. Expose with Tailscale Funnel
To provide a secure public HTTPS endpoint for the local backend without opening firewall ports:
> **Prerequisites:** A Tailscale account with Funnel enabled in your Tailscale Access Controls (ACL policy). The host PC must stay powered on with sleep disabled during the demo.

```powershell
# Authenticate and start Tailscale (if not already running)
tailscale up

# Enable Funnel to route public HTTPS traffic to the local FastAPI port 8000:
tailscale funnel --bg 8000

# View the assigned public funnel URL (e.g., https://your-machine.tailnet.ts.net):
tailscale funnel status
```

### 3. Deploy Frontend to Vercel
Deploy the frontend web application to Vercel with zero backend lock-in:
1. In the Vercel Dashboard, import the Git repository.
2. Set **Root Directory** to `frontend`.
3. Configure Environment Variables:
   - `NEXT_PUBLIC_API_URL`: Your Tailscale Funnel public URL (e.g., `https://your-machine.tailnet.ts.net`) or leave unset to default to local/offline snapshot fallback.
4. Deploy. The application automatically detects backend availability and switches gracefully between live API responses and offline snapshots.

### 4. Refreshing Offline Snapshots Before Demo
Whenever new training runs or decision policies are built, regenerate the frontend snapshot cache:
```powershell
# Exports all 260+ endpoints into frontend/public/snapshots/ with manifest.json (< 15 MB)
python scripts/08_export_snapshots.py --force
```

### 5. Automated Pre-Demo Verification
Run the comprehensive pre-demo test and parity checklist before live presentation:
```powershell
python scripts/predemo_check.py
```
Outputs a complete PASS/FAIL checklist verifying artifacts existence, snapshot parity, API health, and unit test suites.

