# Setup

Complete instructions to run MoveInSync Pulse from a clean machine.

## Prerequisites

- **Python 3.12**
- **Node.js 20+** (tested on v22) and **npm**
- ~1 GB free disk (processed DuckDB ≈ 270 MB)

## 0. Dataset (required — read first)

The processed analytics database (`data/processed/mobility.duckdb`, ≈270 MB) is **not committed** to git (too large for GitHub's 100 MB file limit and excluded via `.gitignore`). You must build it from the hackathon-provided CSVs.

Place these 7 CSVs into `data/raw/` (filenames are matched tolerantly — case, spaces and underscores don't matter):

```
Ride_data _trip-may_2026.csv     # rides, May
Ride_data _trip-June_2026.csv    # rides, June
Ride_data _trip-July_2026.csv    # rides, July
alerts_data.csv                  # safety alerts
bill_data.csv                    # billing
trip_feedback.csv                # feedback
emp_Data.csv                     # employees / boarding
```

```bash
mkdir -p data/raw
# copy the provided dataset in, e.g.:
# cp /path/to/hackathon-dataset/*.csv data/raw/
```

> If you already have a prebuilt `data/processed/mobility.duckdb`, drop it in place and skip step 2.

## 1. Backend environment

```bash
cd MoveInSyncPulse
python3.12 -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 2. Build analytics (preprocessing → DuckDB → aggregates)

Run in this exact order:

```bash
python scripts/preprocess.py          # CSV → normalized Parquet + DuckDB + quality summary
python scripts/build_analytics.py     # build aggregate tables used by the API
```

Optional sanity dump of deterministic analytics:

```bash
python scripts/run_analytics.py | head
```

## 3. Start the backend

```bash
python -m uvicorn app.main:app --reload
```

- API: `http://127.0.0.1:8000`
- Swagger: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/api/health` → `{"status":"ok","llm_configured":<bool>}`

## 4. Start the frontend

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

- App: `http://127.0.0.1:5173`

## 5. Environment variables

### Frontend — `frontend/.env`
```
VITE_API_BASE_URL=http://127.0.0.1:8000
```

### Backend — `.env` (repo root; copy from `.env.example`)
```
LLM_PROVIDER=anthropic          # sarvam | openai | anthropic
LLM_FALLBACK_PROVIDER=openai    # optional second provider
LLM_TIMEOUT_SECONDS=18

SARVAM_API_KEY=
SARVAM_MODEL=sarvam-105b

OPENAI_API_KEY=
OPENAI_MODEL=gpt-5-mini

ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-sonnet-5

DEMO_MODE=false
```

**Do not commit real keys.** `.env` is gitignored; `.env.example` ships blank.

### What needs an LLM key, and what doesn't
- **No key required:** the deterministic dashboard — Overview, AI Insights, cross-domain anomalies, Vendors, Safety, Shift Readiness, and the data pages.
- **LLM access recommended:** Ask Pulse, Investigation narration, and the Executive summary. Without a configured provider these still respond via a **deterministic analytics-backed fallback** (same grounded numbers, `synthesis_mode: deterministic_fallback`).

## 6. Run the tests

```bash
python -m pytest -q
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| **Wrong Python version** | `python --version` must be 3.12.x. Recreate the venv with `python3.12 -m venv .venv`. |
| **`uvicorn: command not found`** | Activate the venv, or run `python -m uvicorn app.main:app --reload`. |
| **`ModuleNotFoundError: langgraph` (or fastapi/duckdb)** | `python -m pip install -r requirements.txt` inside the activated venv. |
| **Frontend can't reach backend** (`backend_unavailable`) | Backend must be running on `:8000`; check `VITE_API_BASE_URL` in `frontend/.env`. |
| **CORS errors in console** | Backend allows only `http://127.0.0.1:5173` / `http://localhost:5173`. Run the frontend on port 5173, or adjust `allow_origins` in `app/main.py`. |
| **`DuckDB not found` / `FileNotFoundError: mobility.duckdb`** | Run step 0 + step 2 to build `data/processed/mobility.duckdb`. |
| **`Expected one CSV matching …` during preprocess** | A raw CSV is missing or misnamed in `data/raw/`; ensure all 7 files from step 0 are present. |
| **LLM endpoints return 503 `llm_not_configured`** | Set a provider + key in `.env`, or rely on the deterministic fallback (dashboard works regardless). |
| **`npm run build` chunk-size warning** | Informational only; the build still succeeds. |
