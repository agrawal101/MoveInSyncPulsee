# Agentic Design

## The loop

```
Sense → Detect → Investigate → Reason → Recommend → Communicate
```

| Stage | Owner | Where |
|---|---|---|
| **Sense** | Deterministic analytics over DuckDB | `app/analytics/service.py` |
| **Detect** | Cross-domain anomaly engine | `app/analytics/cross_domain_anomalies.py` |
| **Investigate** | LangGraph plans and gathers supporting evidence | `app/agents/graph.py` |
| **Reason** | LLM synthesizes the correlated evidence | synthesize node + `app/agents/prompts.py` |
| **Recommend** | Qualitative, approval-gated actions | `RecommendedAction` |
| **Communicate** | REST → React UI (Overview, Insights, Drawer, Reports) | `frontend/` |

---

## Why this is agentic, not a chatbot

A chatbot waits for a human to ask a question. Pulse acts on its own:

1. Pulse **detects** an anomaly automatically (no prompt required).
2. The agent **decides what supporting evidence is needed** for that specific anomaly — a billing anomaly pulls cost + data-quality tools; a safety anomaly pulls alert analytics + delay context.
3. The agent **invokes deterministic tools** in a planned order.
4. The agent **checks data quality** on the collected evidence.
5. The LLM **synthesizes** the evidence into an explanation and recommendation.
6. The system **recommends an action** (approval-gated).

Concretely, investigating the top July anomaly runs this real tool chain (verified, no LLM required for the deterministic path):

```
detect_cross_domain_anomalies_tool
  → analyze_vendor_tool
  → analyze_safety_alerts_tool
  → analyze_delay_causes_tool
```

The human never chose those tools — the agent did, based on the anomaly's type.

---

## Ask Pulse is only one interface

Ask Pulse (natural-language Q&A) is a convenience surface. The **primary intelligence is proactive**: cross-domain detection + automated investigation happen without anyone asking. The same graph powers three entry points:

- **Investigate** — deep-dive one anomaly (`/api/agent/investigate`).
- **Ask Pulse** — free-form question routed to the right tools (`/api/agent/query`).
- **Executive summary** — leadership brief assembled from the month's strongest signals (`/api/reports/executive-summary`).

---

## Why not RAG?

The core problem is **structured analytical reasoning over tabular operational data**, not semantic retrieval over documents. RAG would:

- retrieve fuzzy text chunks where we need exact aggregates;
- provide no guarantee that a cited number is correct;
- add embedding/vector infrastructure that solves a problem we don't have.

Instead, Pulse gives the model **exact, ID-tagged deterministic evidence** and validates every number it returns. Grounding comes from computed facts, not retrieved passages.

---

## Guardrails built into the loop

- **Evidence IDs** — the model must cite an `evidence_id` for every number.
- **Numeric validation** — cited values are checked against the referenced aggregate; mismatches are rejected.
- **Bounded repair** — one conservative retry, then stop.
- **Deterministic fallback** — provider failure or repeated rejection yields an analytics-backed answer, so the product never hard-fails and needs no LLM key to run.
- **Conservative language** — billing risks are "potential irregularities requiring reconciliation review", never proven fraud (enforced in prompt, engine, and tests).
