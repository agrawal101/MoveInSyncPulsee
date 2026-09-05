# Judge Q&A

Concise, technically credible answers to likely questions.

**What makes this agentic?**
Pulse acts without being asked. It detects an anomaly, then the LangGraph agent decides what supporting evidence that specific anomaly needs, invokes deterministic tools in a planned order, checks data quality, and only then has the LLM synthesize. A safety anomaly auto-pulls a different tool chain than a billing one. The human didn't choose the tools — the agent did.

**Why isn't this just a dashboard?**
A dashboard shows one domain and waits for a human to correlate across tabs. Pulse *does the correlation itself* and surfaces combinations that appear in no single view — e.g. safety worsening while service improves. Detection is proactive, not a query you run.

**Why use an LLM at all?**
Only for what it's good at: turning structured evidence into a clear business explanation and a qualitative recommendation. It never computes metrics. Remove it and the product still works (deterministic fallback) — the LLM adds narrative, not facts.

**Why not let the LLM query raw CSV?**
Correctness and privacy. LLMs can't be trusted to aggregate millions of rows exactly, and we don't want raw trip/employee data in a prompt. We compute exact aggregates in SQL and hand the model a small, ID-tagged evidence set instead.

**How do you prevent hallucination?**
Every number the model cites must reference an `evidence_id` we stamped onto a real aggregate; a validator checks each value against that aggregate and rejects mismatches. Operational numbers are stripped from prose. One bounded repair, then a deterministic fallback. Nothing numeric reaches the UI unvalidated.

**How do you detect fraud? / Are you proving fraud?**
We do **not** prove fraud. We detect *potential billing irregularities* — e.g. billing rising while valid-distance coverage collapses, so cost can't be reconciled — and label them "requires reconciliation review." Fraud is only ever framed as a possible risk to investigate. Tests fail if output asserts fraud.

**How is anomaly scoring calculated?**
`cross_signal_risk_score` (0–100) is a transparent additive sum: historical deviation + correlated-signal count + peer deviation + data confidence. Each component and its rationale are returned with the anomaly. No ML black box — deliberately, for explainability.

**How does this scale? / Real-time?**
Analytics run on aggregate tables, so cost grows with vendors/shifts, not trips. Production path: S3 lake → incremental processing → precomputed aggregate/feature layer → scheduled or event-driven detection → cached anomaly feed. The serve path becomes a read. (Current build is on-demand over an embedded DuckDB file.)

**Why DuckDB?**
Zero-ops embedded columnar OLAP — the whole warehouse is one file, sub-second aggregate scans, reproducible SQL. Perfect for a deterministic-analytics product without standing up a database server.

**Why LangGraph?**
It models the investigation as an explicit, auditable state graph (plan → collect → quality-check → synthesize), giving deterministic control flow while confining the LLM to one node.

**Why one agent, not multi-agent?**
The task is bounded — a fixed tool catalogue over one warehouse. Multiple autonomous agents would add non-determinism and token cost without analytical gain. The intelligence is in the deterministic engine, not in agent negotiation.

**What happens if the LLM fails?**
Graceful degradation: the graph catches provider/validation errors and returns an analytics-backed response built from the same evidence. The dashboard and investigations need no LLM key at all.

**How do you protect sensitive data?**
Raw records never leave the deterministic layer. The model receives only compact aggregate evidence. DuckDB is opened read-only at serve time. `.env`/keys are gitignored; `.env.example` ships blank.

**How would this integrate into MoveInSync?**
It consumes the same operational feeds MoveInSync already produces (trips, employees, alerts, billing, feedback). Swap the CSV preprocessing stage for the production ingestion path; the analytics, anomaly engine, agent and UI stay the same. The LLM layer is provider-agnostic behind an abstraction.

**What would you build next?**
Scheduled + event-driven detection with a persisted anomaly feed; durable approval/corrective-action workflows; multi-tenancy with RBAC and audit logging; a model gateway; richer office/vehicle drill-downs in investigations.

**Why should MoveInSync adopt this?**
It turns fragmented mobility data into prioritized, explainable, grounded decisions — catching safety, billing and operational risks earlier than single-metric dashboards, without asking managers to manually reconcile reports.
