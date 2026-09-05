# Presentation Outline

Deck: `presentation/MoveInSync_Pulse_Hackathon.pptx` (9 slides, 16:9).
Regenerate with `python presentation/build_deck.py` (needs `python-pptx`).

Visual language: enterprise SaaS — white/light background, navy text (#0F2540), MoveInSync blue (#1668E3), teal accent (#14B8A6), sparing red/amber/green for status, strong whitespace, minimal text.

1. **Title** — MoveInSync Pulse · Autonomous Cross-Signal Mobility Intelligence · "Detect what dashboards miss."
2. **The Problem** — data across trips/employees/safety/billing/feedback; data-rich → report-heavy → manual correlation → slow action. "The anomaly may not exist in any one report. It emerges when signals are combined."
3. **Our Solution** — Sense → Correlate → Investigate → Reason → Act. One-sentence definition of Pulse.
4. **Cross-Signal Intelligence** — real anomaly: Aarav Petrov Travel, safety alerts worsening while delay/no-show improving → safety-specific deterioration invisible to a vendor health score.
5. **How It Works** — architecture pipeline; "The LLM never calculates operational metrics."
6. **Agentic Investigation** — detected anomaly → agent chooses tools → vendor/safety/delay/data-quality → grounded recommendation; every finding traces to deterministic evidence.
7. **Product Experience** — Overview / Investigation / Ask Pulse / Executive Brief (drop screenshots from `docs/screenshots/`).
8. **Business Impact** — Transport Manager: minutes not hours; Facilities Head: leadership-ready; Org: earlier safety/billing/operational risk detection. (No unsupported ROI figures.)
9. **Built for Enterprise Evolution** — today: hackathon prototype; tomorrow: multi-tenant, real-time signals, durable workflows, governed actions, audit trail, AWS. Close: "MoveInSync Pulse turns mobility data into decisions."

Speaking notes for the live walk-through: [../docs/demo/demo-script.md](../docs/demo/demo-script.md).
