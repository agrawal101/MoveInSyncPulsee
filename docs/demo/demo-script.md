# 5-Minute Demo Script

**Goal:** show that Pulse detects patterns *across* reports, investigates them agentically, and keeps every number grounded.

**Before you start:** run through [demo-checklist.md](demo-checklist.md). Have `2026-07` selected. Backend on `:8000`, frontend on `:5173`.

---

### 0:00 – 0:30 · The problem
> "Mobility teams already have dashboards for trips, billing, safety, shifts and feedback. The hard part isn't any single report — it's spotting patterns *across* them. The most valuable anomaly often doesn't exist in one report; it emerges when signals are combined. That's what Pulse does."

### 0:30 – 1:00 · Overview
- Land on **Overview**. Point to the July KPIs (total trips, delay rate, no-show rate, billing).
> "These are deterministic — computed in SQL, not by an AI."
- Point to the **Cross-Signal Intelligence** section.
> "This is the new capability: anomalies detected by correlating mobility, safety, billing, employee and experience signals — ranked by an explainable cross-signal risk score."

### 1:00 – 2:15 · The Aarav Petrov safety divergence (the hero finding)
- Open the top card: **Aarav Petrov Travel — Safety divergence, risk 91, HIGH**.
- Read the signal chips: **Safety alerts ↑**, **No-show ↓ (better)**, **Delay ↓ (better)**.
> "Here's the insight a normal vendor score would miss: this vendor's safety alerts jumped sharply — well above the peer median — *while* its delay and no-show performance actually improved. So this is a safety-specific deterioration, not a general vendor decline. Averaging those into one health score would hide it."
- Click **Investigate**.
- In the drawer, walk through: **Why flagged → Signals correlated (current vs baseline vs peer) → Historical & Peer comparison → Cross-signal risk score with its components → Recommended investigation → Tool activity.**
> "Notice the tool activity: the agent decided on its own to pull vendor analytics, then safety alerts, then delay context. And every number traces back to deterministic evidence."

### 2:15 – 3:00 · Ask Pulse
- Go to **Ask Pulse**. Ask: **"Why is Aarav Petrov Travel high risk?"** (month 2026-07, baseline 2026-06).
> "Same engine, conversational entry point. The answer is evidence-backed — the numbers come from analytics, the LLM only explains them."

### 3:00 – 3:45 · A second cross-domain area (billing / data integrity)
- Back to **AI Insights**, filter to **Billing Integrity** (or **Data Integrity**).
> "A different pattern: several vendors bill at scale while almost none of their trips carry valid distance — so cost per kilometre can't be reconciled. Pulse calls this a *potential billing irregularity requiring reconciliation review.* Note the language — we never claim fraud is proven; we flag it for investigation."

### 3:45 – 4:30 · Executive brief
- Go to **Reports** → generate the **executive summary**.
> "For leadership: the top cross-signal concern, the strongest safety and billing risks, shift readiness, a positive trend, and a data-quality note — in conservative, defensible language."

### 4:30 – 5:00 · Architecture & close
- Show [../architecture/architecture.svg](../architecture/architecture.svg).
> "The design in one line: **deterministic analytics finds the evidence, the agent decides what to investigate, the LLM explains it — and every numerical claim stays grounded.** Raw trip data never goes to the model; only compact structured evidence does. MoveInSync Pulse turns mobility data into decisions."

---

### Fallback if the LLM provider is down
Investigations and Ask Pulse still work — they return an **analytics-backed** response (`synthesis_mode: deterministic_fallback`) with the same grounded numbers. Say so out loud; it demonstrates resilience rather than a failure.
