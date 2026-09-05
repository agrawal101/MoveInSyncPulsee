# Submission — MoveInSync Pulse

**Project:** MoveInSync Pulse — Autonomous Cross-Signal Mobility Intelligence
**Team:** _<fill in team name / members before submitting>_
**Tagline:** Detect what dashboards miss.

## Problem statement
Enterprise mobility data lives in separate reports (trips, vendors, billing, safety, shifts, feedback). Managers must manually correlate them, so anomalies that only appear *across* domains stay hidden.

## Solution
A deterministic-analytics-first system that **senses → correlates → investigates → reasons → acts**: a cross-domain anomaly engine detects multi-signal patterns, a LangGraph agent gathers supporting evidence, and an LLM explains each finding and recommends a next action — with every number grounded in analytics.

## Key innovation
**Cross-domain anomaly detection with an explainable risk score.** Patterns that are invisible on any single dashboard — e.g. *safety alerts rising while delay and no-show improve* — are detected deterministically, benchmarked historically and against peers, sample-protected, and scored transparently (`cross_signal_risk_score` = historical + correlated-signals + peer + confidence). Billing risks are framed conservatively as *potential irregularities requiring reconciliation review* — never proven fraud.

## Architecture
`CSV → data quality/normalization → DuckDB/Parquet → deterministic analytics → cross-domain anomaly engine → LangGraph orchestrator → grounded LLM synthesis → numeric validation/fallback → FastAPI → React UI → human review.`
Principle: **the LLM never calculates operational metrics; raw data never reaches the LLM.**
Diagram: [docs/architecture/architecture.svg](docs/architecture/architecture.svg) · Details: [docs/architecture/architecture.md](docs/architecture/architecture.md).

## Tech stack
React · TypeScript · Vite · Tailwind · Recharts · Python · FastAPI · Pydantic · DuckDB · Parquet · Pandas/SQL · LangGraph · pluggable LLM (Sarvam / OpenAI / Anthropic).

## How to run
See [SETUP.md](SETUP.md). Short version: build the DuckDB from the dataset (`scripts/preprocess.py` → `scripts/build_analytics.py`), `uvicorn app.main:app`, then `frontend/` `npm install && npm run dev`. The dashboard runs with **no LLM key**.

## Demo flow
Overview → Cross-Signal Intelligence → investigate the Aarav Petrov safety divergence → Ask Pulse → billing/data-integrity → executive brief → architecture. Script: [docs/demo/demo-script.md](docs/demo/demo-script.md).

## Repository structure
```
app/ (analytics · agents · api · data · db · llm · models)
frontend/src/ (React UI)
scripts/ (preprocess, build_analytics, run_analytics)
tests/
docs/ (architecture · product · examples · demo · screenshots)
presentation/ (deck + outline)
README.md · SETUP.md · SUBMISSION.md · .env.example
```

## Real July 2026 findings (from the deterministic engine)
- **Safety divergence — Aarav Petrov Travel (risk 91, HIGH):** alerts 139.2/1k (~+55% vs June, peer median 68.6) while delay & no-show improved.
- **Data-integrity concentration:** several vendors bill at scale with ≈100% zero-distance rows (cost/km unreconcilable).
- **Potential billing irregularities:** billing up while valid-distance coverage collapsed (reconciliation review, not fraud).
- **Shift readiness:** shifts 06:30 and 13:00 show high late-pickup across many offices/vendors.

## Known limitations
- Hackathon prototype: single-file DuckDB, single tenant, on-demand detection.
- Processed DB (~270 MB) is not committed; rebuild from the dataset (see SETUP §0).
- LLM narration is optional; without a provider the system uses a deterministic fallback.
- Utilization was broadly stable in the data, so no billing-vs-utilization anomaly was manufactured.

## Future work
S3 lake + scheduled/event-driven ingestion; warehouse/operational store; incremental & precomputed aggregates; durable approval workflows; multi-tenancy, RBAC, audit logging; model gateway; observability. See [docs/product/scalability.md](docs/product/scalability.md).

---

## Final submission checklist
- [ ] Team name / members filled in above
- [ ] `data/processed/mobility.duckdb` built (SETUP §0–2)
- [ ] Backend tests pass: `python -m pytest -q`
- [ ] Frontend builds: `cd frontend && npm run build`
- [ ] Screenshots captured in `docs/screenshots/` (see list in that folder's README)
- [ ] `.env` / keys absent from git; exposed Anthropic key from earlier **revoked**
- [ ] Deck reviewed: `presentation/MoveInSync_Pulse_Hackathon.pptx`
- [ ] Demo dry-run completed with [docs/demo/demo-checklist.md](docs/demo/demo-checklist.md)
- [ ] Decide dataset delivery (separate upload / release asset — DB exceeds GitHub 100 MB)
