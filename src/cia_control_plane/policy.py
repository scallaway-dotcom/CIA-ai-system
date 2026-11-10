from __future__ import annotations

from datetime import timedelta
from typing import Any

from .util import parse_time, utc_now


SENSITIVE_FLAG = "sensitive"


def sensitive_hard_lock(body: dict[str, Any]) -> bool:
    """True sensitive data is an absolute model and publication lock."""
    flags = body.get("risk_flags") or {}
    return isinstance(flags, dict) and flags.get(SENSITIVE_FLAG) is True


def triage_presence(body: dict[str, Any], policy: dict[str, Any], *, now=None) -> dict[str, Any]:
    """Deterministic early gate only: expiry, evidence availability, basic intake.

    Deliberately does not check account authorization or whether a finished asset exists.
    Semantic relevance is evaluated separately by Engine.triage's simulated reviewer.
    """
    now = now or utc_now()
    reasons: list[str] = []
    risk_flags = body.get("risk_flags", {})
    if not isinstance(risk_flags, dict):
        reasons.append("risk_flags must be an object")
    if sensitive_hard_lock(body):
        reasons.append("sensitive-data hard lock; no model, approval, or publish path")
    expiry = body.get("expires_at")
    if not expiry:
        reasons.append("content expiry is required for triage")
    else:
        try:
            if parse_time(expiry) <= now:
                reasons.append("content has expired")
        except (TypeError, ValueError):
            reasons.append("content expiry timestamp is invalid")
    evidence = body.get("evidence") or {}
    if not isinstance(evidence, dict):
        reasons.append("evidence must be an object")
        evidence = {}
    sources = evidence.get("sources") or []
    if not isinstance(sources, list) or not sources:
        reasons.append("evidence availability: at least one source required")
        sources = []
    else:
        if any(not isinstance(s, (str, dict)) or
               (isinstance(s, str) and not s.strip()) or
               (isinstance(s, dict) and not any(isinstance(s.get(k), str) and s.get(k).strip() for k in ("url", "evidence_id", "ref")))
               for s in sources):
            reasons.append("evidence sources must contain a non-empty URL or reference")
        checked = evidence.get("checked_at")
        if not checked:
            reasons.append("evidence checked_at timestamp required")
        else:
            try:
                checked_at = parse_time(checked)
                age = now - checked_at
                max_age = int(policy.get("max_evidence_age_days", 30))
                if age < -timedelta(minutes=5):
                    reasons.append("evidence timestamp is in the future")
                elif age > timedelta(days=max_age):
                    reasons.append(f"source evidence is stale (>{max_age} days)")
            except (TypeError, ValueError):
                reasons.append("evidence timestamp is invalid")
    if not isinstance(body.get("copy"), str) or not body.get("copy", "").strip():
        reasons.append("intake copy/context is empty")
    return {"eligible": not reasons, "reasons": reasons, "gate": "triage_presence",
            "sensitive_hard_lock": sensitive_hard_lock(body)}


def preflight_checks(body: dict[str, Any], policy: dict[str, Any], *,
                     approval: dict[str, Any] | None, plan: dict[str, Any] | None,
                     active_wip: int = 0, now=None, execution: bool = False) -> dict[str, Any]:
    """Deterministic publication gate, not an editable/overrideable model verdict."""
    now = now or utc_now()
    checks: list[dict[str, Any]] = []

    def check(code: str, ok: bool, reason: str, owner_role: str) -> None:
        if not ok:
            checks.append({"code": code, "reason": reason, "owner_role": owner_role})

    if sensitive_hard_lock(body):
        check("sensitive_hard_lock", False, "sensitive data is never eligible for external publication", "security_operator")
        return {"eligible": False, "gate": "publish_preflight", "checks": checks,
                "category": "sensitive", "expected_approver_role": None,
                "active_wip": active_wip, "max_active_wip": int(policy.get("max_active_wip", 3)),
                "execution": execution}
    owner = body.get("owner") or {}
    if not isinstance(owner, dict) or not owner.get("user_id") or owner.get("accountable") is not True:
        check("accountable_owner_missing", False, "accountable content owner is required", "content_owner")
    asset_status = body.get("asset_status")
    check("asset_not_ready", asset_status == "ready" and bool(body.get("asset_refs")),
          "finished, referenced asset is required", "asset_owner")
    expiry = body.get("expires_at")
    try:
        expiry_at = parse_time(expiry) if expiry else None
        check("content_expired", bool(expiry_at and expiry_at > now),
              "content expiry must still be in the future at publication", "content_owner")
    except (TypeError, ValueError):
        expiry_at = None
        check("content_expired", False, "content expiry timestamp is invalid", "content_owner")

    evidence = body.get("evidence") or {}
    evidence_ok = isinstance(evidence, dict)
    evidence_sources = evidence.get("sources", []) if evidence_ok else []
    checked_at = evidence.get("checked_at") if evidence_ok else None
    try:
        checked_time = parse_time(checked_at) if checked_at else None
        max_age = int(policy.get("max_evidence_age_days", 30))
        source_refs_available = bool(isinstance(evidence_sources, list) and evidence_sources and all(
            (isinstance(source, str) and bool(source.strip())) or
            (isinstance(source, dict) and any(isinstance(source.get(k), str) and source.get(k).strip() for k in ("url", "evidence_id", "ref")))
            for source in evidence_sources))
        evidence_ok = bool(evidence_ok and source_refs_available
                           and checked_time and checked_time <= now + timedelta(minutes=5)
                           and now - checked_time <= timedelta(days=max_age))
    except (TypeError, ValueError):
        evidence_ok = False
    check("evidence_stale_or_missing", evidence_ok,
          "timestamped sources must remain available and fresh at publication", "content_owner")

    account = body.get("account") or {}
    if not isinstance(account, dict):
        account = {}
    account_owner_role = policy.get("role_users", {}).get("account_owner", [])
    check("account_not_authorized", bool(account.get("account_id")) and account.get("authorized") is True
          and account.get("owner_approved") is True and account.get("owner_approved_by") in account_owner_role
          and bool(account.get("authorization_evidence_ref")) and account.get("personal_account") is not True,
          "brand account authorization and account-owner approval are required; personal accounts are excluded",
          "account_owner")

    flags = body.get("risk_flags") or {}
    categories = []
    if isinstance(flags, dict):
        if flags.get("founder") is True: categories.append("founder")
        if flags.get("paid") is True: categories.append("paid")
    if not categories: categories = ["routine"]
    category = "+".join(categories)
    category_roles = policy.get("category_approver_roles", {})
    expected_roles = [category_roles.get(item, f"{item}_approver") for item in categories]
    approved_roles = set(approval.get("approved_roles", [])) if approval else set()
    approved = bool(approval and set(expected_roles).issubset(approved_roles)
                    and plan and approval.get("version") == plan.get("version")
                    and approval.get("content_hash") == plan.get("content_hash")
                    and approval.get("plan_hash") == plan.get("plan_hash")
                    and approval.get("revision") == plan.get("revision"))
    check("approval_missing_or_stale", approved,
          f"current plan/version requires explicit role approval(s): {', '.join(expected_roles)}",
          expected_roles[0] if expected_roles else "routine_approver")
    if not approved and len(expected_roles) > 1:
        checks[-1]["missing_approver_roles"] = [role for role in expected_roles if role not in approved_roles]

    publish_at = body.get("publish_at")
    try:
        due = parse_time(publish_at) if publish_at else None
        max_days = int(policy.get("max_schedule_days", 90))
        if due is None:
            due_valid = False
        elif execution:
            due_valid = now >= due
        else:
            due_valid = due > now and due <= now + timedelta(days=max_days)
        if due_valid and expiry_at is not None and due is not None and due > expiry_at:
            due_valid = False
    except (TypeError, ValueError):
        due = None
        due_valid = False
    check("publish_schedule_invalid", due_valid,
          "publish_at must be a valid future due time within policy horizon" if not execution
          else "scheduled time has not arrived", "content_owner")

    reviewed_claims = bool(plan and plan.get("review_status") == "pass"
                           and plan.get("semantic_verdict") == "pass")
    claims = body.get("claims", [])
    evidence = body.get("evidence") or {}
    source_refs: set[str] = set()
    for source in evidence.get("sources", []) if isinstance(evidence, dict) else []:
        if isinstance(source, str):
            source_refs.add(source)
        elif isinstance(source, dict):
            for key in ("url", "evidence_id", "ref"):
                if isinstance(source.get(key), str):
                    source_refs.add(source[key])
    claims_present = isinstance(claims, list) and all(
        isinstance(c, dict) and isinstance(c.get("evidence_refs"), list) and c["evidence_refs"]
        and all(isinstance(ref, str) and ref in source_refs for ref in c["evidence_refs"])
        for c in claims
    )
    check("claims_review_missing", reviewed_claims and claims_present,
          "semantic claim review and deterministic claim-to-source references must both pass", "content_owner")

    consent = body.get("consent") or {}
    consent_ok = isinstance(consent, dict) and (not consent.get("required") or
                  (consent.get("status") == "granted" and bool(consent.get("evidence_ref"))))
    check("consent_missing", consent_ok, "required consent must be evidenced", "content_owner")
    ai_ok = not body.get("ai_generated", False) or body.get("ai_disclosure") == "present"
    check("ai_disclosure_missing", ai_ok, "AI-generated content requires its applicable disclosure", "content_owner")

    if category == "paid":
        spend = body.get("paid_spend_authorization") or {}
        budget_owner_role = policy.get("role_users", {}).get("paid_budget_owner", [])
        spend_ok = (isinstance(spend, dict) and spend.get("authorized") is True
                    and spend.get("budget_owner_approved") is True
                    and spend.get("approved_by") in budget_owner_role
                    and bool(spend.get("evidence_ref")))
        if spend_ok:
            try:
                spend_ok = float(spend.get("amount", -1)) >= 0 and float(spend.get("amount", -1)) <= float(spend.get("cap", -1))
            except (TypeError, ValueError):
                spend_ok = False
        check("paid_spend_not_authorized", spend_ok,
              "paid content requires separately evidenced spend authorization within its cap", "paid_budget_owner")

    platform = body.get("platform")
    check("platform_not_allowed", platform in policy.get("platform_allowlist", []),
          "platform is not allowlisted", "content_owner")
    return {"eligible": not checks, "gate": "publish_preflight", "checks": checks,
            "category": category, "expected_approver_roles": expected_roles,
            "active_wip": active_wip, "max_active_wip": int(policy.get("max_active_wip", 3)),
            "execution": execution}
