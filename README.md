# CIA Control Plane — distributable local starter

**Reviewer-ready scaffold; not production-ready.** This non-UI Python CLI is a local reference implementation for human-governed content operations. It implements the safety-oriented nine-stage shape below, but it does not connect to ClickUp, an LLM, social platform, identity provider, analytics source, or message service.

**Architecture references:** [Live design artifact (v4)](https://app.clickup-stg.com/333/artifact/ad-7569021?version=4) — diagram explicitly says DESIGN NOT LIVE. Local unmodified exports: [`docs/CIA_System_Architecture.pdf`](docs/CIA_System_Architecture.pdf), [`docs/CIA_System_Architecture.png`](docs/CIA_System_Architecture.png), and [`docs/CIA_System_Architecture.svg`](docs/CIA_System_Architecture.svg).

## Flow

`Intake → Triage → Production → Review/rework → Approval → Preflight → Publish → Reconcile → Measure`

- **Triage:** deterministic presence/expiry/evidence-availability checks, then a separately recorded *simulated semantic* relevance judgment. It does not require an authorized account or finished asset. True sensitive-data flag short-circuits all model calls and cannot be removed by the normal edit path.
- **Production and review:** local planner + critic simulators, at most one of each per rework revision. Critic `revise` routes back through bounded rework; `block` stores reason and owner in a durable blocker. All calls, including triage and all revisions, count toward per-record and daily caps.
- **Approval:** explicit role-backed decision bound to exact record version, content hash, production revision, and plan hash. Demo role labels are not authentication. Founder and paid each have a distinct approver role; a brief marked both needs both approvals. Paid also needs separate evidence-backed spend authorization within its cap.
- **Preflight:** deterministic publishing-only gate: accountable owner, ready referenced asset, authorized brand account and owner approval (never a personal employee account), current role approvals, schedule, claims/source checks, consent, AI disclosure, and platform allowlist. Neither a model nor human approval can bypass a failed preflight.
- **Execution:** SQLite outbox uses a stable idempotency key. A worker may only claim after the approved due time (`now >= scheduled_at`) and it re-runs preflight. Default live mode is false. Local demo uses an explicitly pinned clock and a dry-run adapter. Ambiguous sends remain `UNKNOWN` until evidence-backed reconciliation; never blindly retry.
- **Blockers and measurement:** blockers store role owner, optional named assignee, due time, escalation target, and resolution evidence. Overdue/unassigned items appear in a deterministic queue; no messages are sent. WIP=3 applies from active production through unknown publish, not intake backlog. Measures are separated into operations, quality, and channel-specific performance; missing baseline means insufficient data. Engagement/acceptance never promotes publishing autonomy.

## Quick start

Python 3.11+. Runtime uses the standard library.

```bash
PYTHONPATH=src python -m cia_control_plane.cli --db ./demo.sqlite3 demo
PYTHONPATH=src python -m unittest discover -s tests -v
```

Optional console script: `python -m pip install -e .`, then `cia --help`. The complete `demo` command uses the explicitly pinned demo time **2026-11-03 12:00Z**, starts with an intentionally blocked synthetic brief, resolves account and asset blockers with two named synthetic role identities, repeats triage/review, role-approves, passes preflight, advances pinned time to the due minute, and emits a clearly `SIMULATED ONLY` receipt with `public_url: null`. Synthetic 24h/72h metrics are not analytics. Demo names, evidence URLs and IDs are fabricated; no brief has been imported from ClickUp.

Useful commands: `import --file`, `triage ID`, `produce ID`, `approve ID --approver USER`, `preflight ID`, `blockers ID`, `resolve-blocker ID --resolver USER --evidence TEXT --patch JSON`, `escalations`, `schedule ID`, `publish KEY`, `reconcile KEY --outcome confirmed_not_sent --operator USER --evidence TEXT`, `measure ID`, `pause --reason TEXT`, `resume`, `audit`. `recover` converts interrupted publishing claims to `UNKNOWN`; run only after verifying the old worker has stopped. See `REVIEW_GUIDE.md` for review boundaries and `docs/ARCHITECTURE.md` for states/events/interfaces.

## Important limits

- All planners/critics and semantic relevance judgments are local simulations; they make no LLM calls. The simulated production plan does not generate media.
- No provider is configured. Not-configured adapters fail closed. `live_publish_enabled` is false by default and the CLI provides no live-enable shortcut. No token refresh, impersonation, payment, ClickUp sync, posting, or messages occur.
- The audit hash chain is tamper-evident, not tamper-proof. SQLite is local operational state, not a production service with backup/HA/monitoring.
- Supplied historical brief counts, owners/access gaps, and token status are not verified as current facts and are not seeded as real records. Expired seasonal material is not reused.
- No workspace or source-control changes were made.
