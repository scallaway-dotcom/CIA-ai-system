"""Provider contracts. Real adapters are deliberately absent and fail closed."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class NotConfigured(RuntimeError):
    """Raised instead of pretending a live provider is connected."""


@dataclass(frozen=True)
class PublishResult:
    outcome: str  # sent | definite_failure | unknown
    receipt: dict[str, Any] | None = None
    detail: str = ""


class ClickUpCanonicalAdapter(Protocol):
    def fetch_record(self, record_id: str) -> dict[str, Any]: ...
    def write_receipt(self, record_id: str, receipt: dict[str, Any]) -> None: ...


class PublishingAdapter(Protocol):
    def publish(self, *, record: dict[str, Any], idempotency_key: str) -> PublishResult: ...
    def reconcile(self, *, idempotency_key: str) -> PublishResult: ...


class NotConfiguredClickUpAdapter:
    def fetch_record(self, record_id: str) -> dict[str, Any]:
        raise NotConfigured("ClickUp adapter is not configured; no live sync performed")

    def write_receipt(self, record_id: str, receipt: dict[str, Any]) -> None:
        raise NotConfigured("ClickUp adapter is not configured; receipt remains local")


class NotConfiguredPublishingAdapter:
    def publish(self, *, record: dict[str, Any], idempotency_key: str) -> PublishResult:
        raise NotConfigured("publishing adapter is not configured; no external publication performed")

    def reconcile(self, *, idempotency_key: str) -> PublishResult:
        raise NotConfigured("publishing adapter is not configured; unknown outcomes require provider reconciliation")


class SimulatedPublishingAdapter:
    """Dry-run only: returns no public URL and marks the receipt as simulated."""
    def publish(self, *, record: dict[str, Any], idempotency_key: str) -> PublishResult:
        return PublishResult("sent", {
            "simulated": True,
            "provider": "local-dry-run",
            "idempotency_key": idempotency_key,
            "public_url": None,
            "published_at": None,
            "notice": "SIMULATED ONLY; no external post was created",
        }, "SIMULATED ONLY; no external post was created")

    def reconcile(self, *, idempotency_key: str) -> PublishResult:
        return PublishResult("unknown", detail="dry-run adapter has no external provider to reconcile")
