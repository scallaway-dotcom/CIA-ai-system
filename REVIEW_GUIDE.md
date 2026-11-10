# CIA Control Plane v2 — reviewer guide

## Release posture

**Distributable local starter, reviewer-ready, not production-ready.** This package is a CLI reference scaffold and simulation. The goal is to make safety boundaries reviewable before any live integration, not to claim connected operations.

## Nine stages and acceptance checks

1. **Intake:** SQLite canonical record ID, version, and content hash. JSON imports are data, not instructions.
2. **Triage:** deterministic expiry/evidence-presence checks precede a simulated semantic relevance judgment. Account and finished asset are deliberately not required yet. Sensitive hard lock skips all models.
3. **Production:** one planner call plus one critic call maximum per revision; total per-record and daily caps include semantic triage and every rework call. Production/asset status is explicit; simulator creates no media.
4. **Review/rework:** `pass` moves to review; `revise` returns to bounded rework; exhausted cycles or `block` create a durable reasoned blocker with owner role. Role-owned blockers require resolution evidence; no escalation messages are emitted.
5. **Approval:** role-based, exact version + content hash + revision + plan hash. Founder and paid are not sensitive hard locks; founder approval and paid approval are distinct. Paid requires a separate budget-owner authorization with amount, cap, and evidence. Both category approvals are needed if a record has both flags.
6. **Preflight:** deterministic publication checks. A human/model cannot override a failed result. Blocker resolution that edits the canonical record increments version and invalidates previous plans/approvals.
7. **Publish:** outbox and stable idempotency key. The worker checks due time and repeats preflight at execution. Default live mode is disabled; only local dry-run is wired.
8. **Reconcile:** `UNKNOWN` never retries automatically. Operator evidence can reconcile confirmed-sent (provider receipt reference required) or confirmed-not-sent. Interrupted claims become `UNKNOWN`; no blind retry.
9. **Measure:** operations (blocked duration, approval latency, publication success), quality (rework/critical misses), and channel-specific performance are separate. No configured channel baseline yields `insufficient_data`. No autonomy promotion from acceptance or engagement.

## Implemented vs mocked vs proposed

| Area | Implemented in this starter | Mocked / local only | Proposed or not connected |
|---|---|---|---|
| Data/runtime | SQLite version/hash records, workflow state, transactional outbox, blockers, audit chain | Demo seed and fixed clock | Production database, backups/HA/retention and alerting |
| Triage | Deterministic expiry/evidence availability checks; sensitive hard lock | Semantic relevance judgement | Real model/provider evaluation and prompt security review |
| Production/review | Revision-bound call caps; bounded cycle and state routing | Planner/critic outputs and copy; no media generation | Actual content/asset production and independent quality review |
| Approvals | Role allowlists and version/plan-bound approval records | Synthetic user IDs; these are not authentication | SSO/IAM, approval UX, revocation, separation of duties |
| Blockers | Durable role, optional assignee, due time, escalation target, evidence; overdue/unassigned queue | Demo owner role names | Real ownership mapping and staffed escalation; no messaging is configured |
| Preflight | Deterministic owner, asset, account, approval, schedule, claims, disclosure, consent, platform, spend checks | Synthetic authorization evidence | Live account permission/token health and platform-rule validation |
| Publishing | Idempotent SQLite outbox; single claim; pause; WIP cap; `UNKNOWN`/dead-letter transitions | Dry-run receipt only, no URL; fixed demo clock | Provider adapter, real due-time worker, live preflight, delivery receipt and provider reconciliation |
| Metrics | Provenance-tagged storage and separated report categories | Demo 24h/72h values | Channel-specific real baselines and analytics adapters |
| Integrations | Typed ClickUp/publisher adapter contracts; not-configured publishers fail closed | None | ClickUp sync/version authority, auth, provider/API wiring; no automatic token refresh |

## Owner/approver proposal — not assignments

- **Steven — coordinator:** proposal for coordinating requirements and review only; not recorded as an actual owner.
- **Publishing owner — TBD.**
- **Routine approver — TBD.**
- **Founder approver — Zeb:** proposed role label only; not inferred as an approval or workspace assignment.
- **Paid budget owner — TBD.**

No real person is assigned in the demo configuration. Its `demo-*` names are fictional local role fixtures.

## Acceptance target not met

> **“One blocked brief → verified live receipt without manual chasing.”**

This remains **NOT MET**. The demo resolves synthetic blockers and emits a simulated receipt; it does not establish an owner, connect an account, authenticate approvals, publish, verify an actual provider receipt, or monitor a live worker. Meeting this target requires at minimum: named accountable owners; approved brand-owned account access; real IAM/role approvals; current evidence/claims/asset review; production provider adapter and token/permission health; a monitored due-time worker with idempotency/reconciliation; verified live receipt; and incident/escalation operations. Human approval and real preflight remain required.

## Run and inspect

```bash
PYTHONPATH=src python -m cia_control_plane.cli --db ./review.sqlite3 demo
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m cia_control_plane.cli --db ./review.sqlite3 audit
```

Review `docs/ARCHITECTURE.md`, `docs/INTEGRATION_CHECKLIST.md`, `docs/PROVIDER_CONTRACTS.md`, the three parent-provided diagram exports in `docs/`, and the code/tests. No ClickUp/GitHub writes, messages, or real-provider calls are part of these commands.
