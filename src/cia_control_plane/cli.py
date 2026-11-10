from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .engine import Engine, GateError
from .storage import Store

BASE = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = BASE / "examples" / "policy.demo.json"
DEFAULT_SEED = BASE / "examples" / "demo-dossier.json"
DEMO_NOW = "2026-11-03T12:00:00Z"


def read_json(path: str | Path) -> Any:
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def engine_for(args) -> Engine:
    return Engine(Store(getattr(args, "db", "cia-control-plane.sqlite3")),
                  read_json(getattr(args, "policy", None) or DEFAULT_POLICY))


def emit(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def demo(args) -> int:
    engine = engine_for(args)
    if not engine.demo_mode:
        raise GateError("complete demo requires a policy explicitly marked demo_mode")
    engine.set_demo_time(DEMO_NOW)
    body = read_json(args.seed or DEFAULT_SEED)
    record = engine.import_record(body)
    record_id = record["record_id"]
    print("== 1 Intake ==")
    emit({"record_id": record_id, "version": record["version"], "hash": record["content_hash"], "demo_only": True})
    print("== 2 Triage: deterministic presence + simulated semantic relevance ==")
    emit(engine.context(record_id))
    triage = engine.triage(record_id)
    emit(triage)
    if triage["status"] != "TRIAGED":
        return 2
    print("== 3 Production + 4 Review/rework (simulated; no asset generation) ==")
    production = engine.produce(record_id)
    emit(production)
    if production["status"] != "PASS":
        return 2
    print("== 5 Approval (role-based demo identity; not authentication) ==")
    approval = engine.approve(record_id, "demo-routine-approver")
    emit(approval)
    print("== 6 Preflight: blocked until named demo roles resolve durable blockers ==")
    blocked = engine.preflight(record_id)
    emit(blocked)
    if blocked["eligible"]:
        raise GateError("demo seed expected to fail preflight before blocker resolution")
    blockers = engine.blockers(record_id)
    for blocker in blockers:
        if blocker["code"] == "account_not_authorized":
            resolved = engine.resolve_blocker(
                blocker["blocker_id"], "demo-account-owner",
                evidence="Synthetic demo account-owner authorization record; not a live provider grant.",
                patch={"account": {"authorized": True, "owner_approved": True,
                                   "owner_approved_by": "demo-account-owner",
                                   "authorization_evidence_ref": "demo://approved-account-owner"}})
            emit(resolved)
        elif blocker["code"] == "asset_not_ready":
            resolved = engine.resolve_blocker(
                blocker["blocker_id"], "demo-asset-owner",
                evidence="Synthetic demo asset-ready review; no actual media generated.",
                patch={"asset_status": "ready", "asset_refs": ["demo://assets/reviewed-evergreen.png"]})
            emit(resolved)
    print("== Re-triage and bounded rework after blocker edits invalidated approval ==")
    emit(engine.triage(record_id))
    revised = engine.produce(record_id, revision_note="Re-review the version updated by the named demo blocker owners.")
    emit(revised)
    if revised["status"] != "PASS":
        return 2
    print("== Re-approval for the exact revised version and plan ==")
    emit(engine.approve(record_id, "demo-routine-approver"))
    print("== Preflight ==")
    preflight = engine.preflight(record_id)
    emit(preflight)
    if not preflight["eligible"]:
        return 2
    scheduled = engine.schedule(record_id)
    print("== 7 Publish: local scheduler/outbox ==")
    emit(scheduled)
    print("== 7 Publish worker only after pinned clock reaches due time ==")
    emit({"pinned_clock_before": engine.now().isoformat(),
          "advanced_clock": engine.advance_demo_time(seconds=300)})
    published = engine.publish(scheduled["idempotency_key"])
    emit(published)
    if published.get("status") != "RECEIPT":
        return 2
    print("== 8 Reconcile: durable simulated receipt confirmed; no UNKNOWN, live provider, or manual claim ==")
    emit({"idempotency_key": scheduled["idempotency_key"], "state": "receipt_recorded",
          "receipt_provenance": "SIMULATED ONLY", "unknown_reconciliation": "not_required_for_successful_simulated_receipt"})
    print("== 9 Measure: operational, quality, and performance ==")
    engine.capture_metrics(record_id, "24h", {"impressions": 120, "engagements": 9})
    engine.capture_metrics(record_id, "72h", {"impressions": 240, "engagements": 17})
    engine.feedback(record_id, "Demo only: evergreen framing retained; engagement does not promote publishing autonomy.")
    emit(engine.measure(record_id))
    print("== Escalation queue (inspection only; no messages sent) ==")
    emit(engine.escalation_queue())
    print("== Audit chain ==")
    emit(engine.store.verify_audit())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cia", description="CIA Control Plane local, fail-closed CLI")
    parser.add_argument("--db", default="cia-control-plane.sqlite3", help="local SQLite database")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY), help="hand-editable policy JSON")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    imp = sub.add_parser("import")
    imp.add_argument("--file", required=True)
    edit = sub.add_parser("edit")
    edit.add_argument("record_id")
    edit.add_argument("--file", required=True)
    triage = sub.add_parser("triage")
    triage.add_argument("record_id")
    for name in ("context", "evaluate", "show", "produce", "preflight", "blockers", "escalations", "measure"):
        cmd = sub.add_parser(name)
        if name != "escalations":
            cmd.add_argument("record_id", nargs="?" if name == "blockers" else None)
        if name == "produce":
            cmd.add_argument("--revision-note", default="")
    approve = sub.add_parser("approve")
    approve.add_argument("record_id")
    approve.add_argument("--approver", required=True)
    approve.add_argument("--decision", choices=("approve", "revise", "block"), default="approve")
    approve.add_argument("--reason", default="")
    resolve = sub.add_parser("resolve-blocker")
    resolve.add_argument("blocker_id")
    resolve.add_argument("--resolver", required=True)
    resolve.add_argument("--evidence", required=True)
    resolve.add_argument("--patch", default="{}", help="JSON object to apply to canonical dossier")
    schedule = sub.add_parser("schedule")
    schedule.add_argument("record_id")
    publish = sub.add_parser("publish")
    publish.add_argument("idempotency_key")
    reconcile = sub.add_parser("reconcile")
    reconcile.add_argument("idempotency_key")
    reconcile.add_argument("--outcome", required=True, choices=("confirmed_sent", "confirmed_not_sent"))
    reconcile.add_argument("--operator", required=True)
    reconcile.add_argument("--evidence", required=True)
    reconcile.add_argument("--receipt", default="{}")
    sub.add_parser("recover")
    metrics = sub.add_parser("metrics")
    metrics.add_argument("record_id")
    metrics.add_argument("--phase", required=True, choices=("24h", "72h"))
    metrics.add_argument("--values", default="{}")
    fb = sub.add_parser("feedback")
    fb.add_argument("record_id")
    fb.add_argument("--text", required=True)
    pause = sub.add_parser("pause")
    pause.add_argument("--reason", required=True)
    sub.add_parser("resume")
    sub.add_parser("audit")
    demo_cmd = sub.add_parser("demo", help="run full synthetic nine-stage demo with pinned 2026-11-03 clock")
    demo_cmd.add_argument("--seed", default=str(DEFAULT_SEED))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        engine = engine_for(args)
        cmd = args.command
        if cmd == "demo": return demo(args)
        if cmd == "init": emit({"initialized": True, "live_publish_enabled": False, "providers": "not configured"})
        elif cmd == "import": emit(engine.import_record(read_json(args.file)))
        elif cmd == "edit": emit(engine.edit_record(args.record_id, read_json(args.file)))
        elif cmd == "triage": emit(engine.triage(args.record_id))
        elif cmd == "context": emit(engine.context(args.record_id))
        elif cmd == "evaluate": emit(engine.evaluate(args.record_id))
        elif cmd == "show": emit(engine.store.get_record(args.record_id))
        elif cmd == "produce": emit(engine.produce(args.record_id, revision_note=args.revision_note))
        elif cmd == "preflight": emit(engine.preflight(args.record_id))
        elif cmd == "blockers": emit(engine.blockers(args.record_id))
        elif cmd == "escalations": emit(engine.escalation_queue())
        elif cmd == "measure": emit(engine.measure(args.record_id))
        elif cmd == "approve": emit(engine.approve(args.record_id, args.approver, decision=args.decision, reason=args.reason))
        elif cmd == "resolve-blocker": emit(engine.resolve_blocker(args.blocker_id, args.resolver,
                                      evidence=args.evidence, patch=json.loads(args.patch)))
        elif cmd == "schedule": emit(engine.schedule(args.record_id))
        elif cmd == "publish": emit(engine.publish(args.idempotency_key))
        elif cmd == "reconcile": emit(engine.resolve_unknown(args.idempotency_key, args.outcome,
                                      operator=args.operator, evidence=args.evidence, receipt=json.loads(args.receipt)))
        elif cmd == "recover": emit({"converted_to_unknown": engine.recover_interrupted_claims(),
                                      "warning": "Run only after confirming the old worker is no longer active."})
        elif cmd == "metrics": emit(engine.capture_metrics(args.record_id, args.phase, json.loads(args.values)))
        elif cmd == "feedback": engine.feedback(args.record_id, args.text); emit({"saved": True, "provenance": "SIMULATED_DEMO"})
        elif cmd == "pause": engine.store.set_paused(True, args.reason); emit({"paused": True, "reason": args.reason})
        elif cmd == "resume": engine.store.set_paused(False, "operator resumed"); emit({"paused": False})
        elif cmd == "audit":
            ok, message = engine.store.verify_audit(); emit({"ok": ok, "message": message}); return 0 if ok else 3
        return 0
    except (GateError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
