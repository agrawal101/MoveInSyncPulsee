# Solution Overview

> **MoveInSync Pulse continuously correlates mobility operations data to identify patterns that are difficult to detect from individual dashboards** — then investigates each pattern, explains its business significance, and recommends a next action.

## The problem, in one line

Enterprise mobility teams are **data-rich but insight-poor**: the numbers exist across trips, vendors, billing, safety, shifts and feedback, but the important anomalies live *between* those reports, where no single dashboard looks.

## What Pulse does

- **Detects cross-signal anomalies** automatically — combinations that are invisible on any one dashboard.
- **Investigates** each anomaly by gathering the right supporting evidence.
- **Explains** it in business language and **recommends** a qualitative next action.
- Keeps **every number grounded** in deterministic analytics — the LLM narrates, it never computes.

## Personas & value

### Transport Manager
*Job:* keep vendors and routes running well day to day.
*Value:* **faster anomaly detection and investigation** — the system surfaces the vendor/shift worth looking at and pre-assembles the evidence, turning an hours-long manual cross-report hunt into a minutes-long review.

### Transport / Facilities Head
*Job:* answer to leadership on cost, safety, reliability and risk.
*Value:* a **leadership-ready view** — an executive brief that combines the top cross-signal concern, the strongest safety and billing risks, shift readiness, and a data-quality note, in conservative, defensible language.

### Line / Shift Manager
*Job:* make sure employees get picked up on time.
*Value:* **shift-readiness and employee-arrival visibility** — which shifts are running late across which offices and vendors, ranked by a sample-protected risk score.

## A real example (July 2026)

The strongest July pattern is a **safety divergence at Aarav Petrov Travel**: safety alert frequency rose sharply *while* delay and no-show performance actually improved. A single vendor-health score would average these out and miss it. Pulse flags it as a **safety-specific deterioration**, not a general vendor decline — precisely the kind of finding that only appears when domains are correlated.

## What it is not

- It does **not** claim to prove fraud. Billing concerns are *potential irregularities requiring reconciliation review.*
- It does **not** invent numbers. Every operational value comes from deterministic analytics.
- It is a **hackathon prototype** — see the production roadmap in [scalability.md](scalability.md) and [../architecture/architecture.md](../architecture/architecture.md).
