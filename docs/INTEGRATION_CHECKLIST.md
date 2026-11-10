# Integration checklist — proposed work, not executed

Every box below remains not configured or not verified for live use.

## Ownership, review, and source of truth
- [ ] Name an accountable content owner and publishing/account owner for a small, current evergreen pilot.
- [ ] Name a routine approver; separately name founder approver and paid budget owner where applicable.
- [ ] Proposed accountability only: Steven as coordinator; publishing owner TBD; routine approver TBD; Zeb as proposed founder-approval role; paid budget owner TBD. These are not ClickUp assignments, approvals, or confirmed commitments.
- [ ] Select a ClickUp destination only after inspection/review. Define canonical authority, stable IDs, version conflicts, attachments, and receipt writeback. No destination was chosen.
- [ ] Validate current source evidence, claims, consent, expiry, asset, account permissions and platform disclosure rules for each pilot item; do not bulk-import historical briefs or expired seasonal content.

## Identity, privacy, and controls
- [ ] Implement authenticated user identity; replace demo role strings with IAM roles and explicit approval/revocation policy.
- [ ] Implement private/sensitive-data handling, access controls, audit retention, backups/restore, monitoring, and security review.
- [ ] Verify account-owner authorization and voluntary account opt-in; exclude personal employee accounts.
- [ ] Add a real paid-spend budget approval and cap if ever in scope. Founder and paid content use separate approver permissions. Sensitive content remains prohibited from this workflow.
- [ ] Add real evidence/source validation and model semantic evaluation; never allow model output to mutate deterministic results.

## Live provider and operations
- [ ] Implement provider idempotency, due-time worker, safe rate-limits, token health/revocation and receipt validation.
- [ ] Implement provider-side reconcile for `UNKNOWN`; never retry until confirmed not sent. Define human escalation/incident runbook.
- [ ] Implement owned blocker escalation (named owner + staffed escalation) without assuming messages may be sent.
- [ ] Configure pause authority, active WIP cap, daily/total call budget, dead-letter operations, telemetry and operational SLOs.
- [ ] Connect actual channel-specific performance baselines and 24h/72h data provenance; missing baselines remain insufficient data.

## Acceptance target
- [ ] Acceptance test: **“one blocked brief → verified live receipt without manual chasing.”** NOT MET by this starter. It requires real IAM/owners, source and asset review, authorized brand account, live adapter, monitored worker, actual verified receipt, and staffed exception handling. The local demo proves only synthetic blocker resolution and simulation.
