# Demo Checklist

Run top-to-bottom ~10 minutes before presenting.

## Environment
- [ ] `.venv` active; `python -m pip install -r requirements.txt` done
- [ ] Processed DB exists: `data/processed/mobility.duckdb` (else run `scripts/preprocess.py` then `scripts/build_analytics.py` — see [../../SETUP.md](../../SETUP.md))
- [ ] Frontend deps installed: `frontend/` → `npm install`
- [ ] `frontend/.env` present (`cp frontend/.env.example frontend/.env`)

## Backend
- [ ] `python -m uvicorn app.main:app --reload` starts with no errors
- [ ] `http://127.0.0.1:8000/api/health` returns `{"status":"ok", ...}`
- [ ] Swagger loads: `http://127.0.0.1:8000/docs`

## Frontend
- [ ] `npm run dev` in `frontend/`; app loads at `http://127.0.0.1:5173`
- [ ] No red errors in browser console
- [ ] Network tab shows API calls succeeding (not `backend_unavailable`)

## Data smoke checks (month = 2026-07)
- [ ] Overview KPIs render (total trips ≈ 215,885)
- [ ] Cross-Signal Intelligence shows cards; top card = **Aarav Petrov Travel — Safety divergence (risk 91)**
- [ ] AI Insights category filters work (Billing Integrity / Safety / Vendor / Shift / Data Integrity)
- [ ] Investigation drawer opens and shows: why-flagged, signals, historical + peer, risk components, recommended steps, tool activity
- [ ] Safety and Shift Readiness pages load

## Agent / LLM
- [ ] If an LLM provider is configured: Ask Pulse returns an answer; executive summary generates
- [ ] If **not** configured: confirm the **deterministic fallback** works (Ask Pulse / Investigate still return content with `synthesis_mode: deterministic_fallback`) — this is the safe demo mode

## Backup
- [ ] Screenshots captured in `docs/screenshots/` (Overview, cross-signal card, investigation drawer, Safety, Shift Readiness, Ask Pulse, Executive Brief)
- [ ] `docs/examples/sample-responses.md` open in a tab as a fallback if the app misbehaves

## Fallback plan if the LLM provider is unavailable mid-demo
1. State plainly: "The LLM narration layer is optional; the deterministic engine is the product."
2. Continue the demo — Overview, cross-domain anomalies, investigation, and reports all work on the fallback path with identical grounded numbers.
3. If needed, show `docs/examples/sample-responses.md` for a pre-captured investigation payload.

## Reset between runs
- Reselect month `2026-07`; close any open drawer; hard-refresh the browser.
