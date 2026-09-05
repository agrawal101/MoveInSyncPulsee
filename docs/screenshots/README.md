# Screenshots

Automated capture was **not** run (no headless browser is provisioned in this environment, and capturing requires the live backend + frontend). Screenshots are therefore **not fabricated** — capture them manually and drop the PNGs here using the exact filenames below, then they can be embedded in the deck (slide 7) and README.

## How to capture
1. Start backend (`uvicorn app.main:app`) and frontend (`npm run dev`) — see [../../SETUP.md](../../SETUP.md).
2. Open `http://127.0.0.1:5173`, month = **2026-07**.
3. Capture each screen at ~1440px wide.

## Required shots
| File | Screen | Notes |
|---|---|---|
| `overview.png` | Overview | KPIs + Cross-Signal Intelligence cards |
| `cross-signal-card.png` | Overview / Insights | Close-up of the Aarav Petrov "Safety divergence" card with signal chips |
| `investigation-drawer.png` | Investigation drawer | Why-flagged, signals, historical + peer, risk components, tool activity |
| `safety.png` | Safety | Alert distribution / concentration |
| `shift-readiness.png` | Shift Readiness | Ranked shifts |
| `ask-pulse.png` | Ask Pulse | Evidence-backed answer to "Why is Aarav Petrov Travel high risk?" |
| `executive-brief.png` | Reports | Generated executive summary |
