# Provider contracts — not configured

## Human-work-surface adapter

`ClickUpCanonicalAdapter.fetch_record(record_id)` and `.write_receipt(record_id, receipt)` are interface sketches only. No ClickUp adapter is present or connected. A future implementation must define record/version authority, conflicts, attachment identity, user permissions, status mapping, receipt provenance, and retry behavior before it may sync. No workspace destination has been chosen.

## Publisher adapter

`PublishingAdapter.publish(record, idempotency_key)` returns `PublishResult(outcome, receipt, detail)` where outcome is `sent`, `definite_failure`, or `unknown`. `.reconcile(idempotency_key)` must use provider evidence. A timeout is ambiguous, not “not sent.” Live sent results must include verifiable provider, provider reference and public URL; otherwise the outbox retains `UNKNOWN`.

The only configured publisher is `SimulatedPublishingAdapter`, which produces no external side effect, no post, no live URL, and a `SIMULATED ONLY` notice. `NotConfiguredPublishingAdapter` and `NotConfiguredClickUpAdapter` raise `NotConfigured`. The engine defaults live publish off and repeats preflight at execution regardless of adapter. No automatic token refresh, impersonation, spend, or messages are implemented.

A future live adapter requires least-privilege credentials from a secret manager, human opt-in and account-owner approval, provider-side idempotency or duplicate reconciliation, due-time worker/monitoring, verified receipts, incident recovery and security review. No secrets should be stored in JSON or source.
