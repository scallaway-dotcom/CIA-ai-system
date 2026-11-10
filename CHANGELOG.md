# Changelog

## v2 — nine-stage reviewer-ready scaffold

- Reframed workflow as Intake → Triage → Production → Review/rework → Approval → Preflight → Publish → Reconcile → Measure.
- Split early deterministic triage presence/expiry/evidence availability from later publishing preflight; added a separately tracked simulated semantic relevance/claims-review layer.
- Added production state, asset status, bounded revision cycles, critic revise routing, reasoned block outcomes, lifetime and daily model-call caps counting all calls and revisions.
- Added durable role-owned blockers, deadlines, escalation targets, resolution evidence, unassigned operator queue, and no-message guarantee.
- Separated founder/paid approval roles; paid spend authorization requires distinct evidence and amount cap. Sensitive data remains an absolute model/publication lock.
- Moved WIP=3 to active production through unknown reconciliation; intake backlog is excluded.
- Bound approval to version/content/revision/plan hash; resolution edits invalidate it. Preflight is non-overridable and rechecked by the publish worker.
- Enforced due-time check, default-off live mode, stable SQLite outbox key, concurrent claim handling, UNKNOWN recovery and evidence-backed reconciliation.
- Separated operations, quality, and channel-baseline performance metrics; missing baselines report insufficient data; engagement never promotes publishing autonomy.
- Demo is now a blocked synthetic brief resolved by named synthetic roles on an explicitly pinned 2026-11-03 clock and ends in a simulated, not live, receipt.
- Added reviewer matrix, role proposal, acceptance-not-met statement, and parent-provided design diagram exports.
