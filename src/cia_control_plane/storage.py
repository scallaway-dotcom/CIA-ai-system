from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .util import canonical_json, digest, iso_now


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS records (
  record_id TEXT PRIMARY KEY, version INTEGER NOT NULL, content_hash TEXT NOT NULL,
  body_json TEXT NOT NULL, workflow_state TEXT NOT NULL DEFAULT 'INTAKE',
  revision_count INTEGER NOT NULL DEFAULT 0, production_started_at TEXT,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS triage_results (
  record_id TEXT NOT NULL, version INTEGER NOT NULL, content_hash TEXT NOT NULL,
  result_json TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY(record_id, version, content_hash)
);
CREATE TABLE IF NOT EXISTS plans (
  plan_id INTEGER PRIMARY KEY AUTOINCREMENT, record_id TEXT NOT NULL, version INTEGER NOT NULL,
  content_hash TEXT NOT NULL, revision INTEGER NOT NULL, plan_hash TEXT NOT NULL,
  plan_json TEXT NOT NULL, critic_json TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(record_id, version, content_hash, revision)
);
CREATE TABLE IF NOT EXISTS model_calls (
  call_id INTEGER PRIMARY KEY AUTOINCREMENT, record_id TEXT NOT NULL, version INTEGER NOT NULL,
  revision INTEGER NOT NULL, stage TEXT NOT NULL, model_name TEXT NOT NULL,
  request_hash TEXT NOT NULL, response_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'RESERVED', created_at TEXT NOT NULL, completed_at TEXT,
  UNIQUE(record_id, version, revision, stage)
);
CREATE INDEX IF NOT EXISTS model_calls_day_idx ON model_calls(created_at);
CREATE TABLE IF NOT EXISTS approvals (
  approval_key TEXT PRIMARY KEY, record_id TEXT NOT NULL, version INTEGER NOT NULL,
  content_hash TEXT NOT NULL, revision INTEGER NOT NULL, plan_hash TEXT NOT NULL,
  approver TEXT NOT NULL, approver_role TEXT NOT NULL, decision TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approval_decisions (
  decision_id INTEGER PRIMARY KEY AUTOINCREMENT, approval_key TEXT NOT NULL,
  decision TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS blockers (
  blocker_id TEXT PRIMARY KEY, record_id TEXT NOT NULL, version INTEGER NOT NULL,
  code TEXT NOT NULL, description TEXT NOT NULL, owner_role TEXT NOT NULL,
  owner_user TEXT, due_at TEXT NOT NULL, escalation_target TEXT NOT NULL,
  status TEXT NOT NULL, resolution_evidence TEXT NOT NULL DEFAULT '',
  resolved_by TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS blocker_open_idx ON blockers(status, due_at);
CREATE TABLE IF NOT EXISTS outbox (
  idempotency_key TEXT PRIMARY KEY, record_id TEXT NOT NULL, version INTEGER NOT NULL,
  content_hash TEXT NOT NULL, revision INTEGER NOT NULL, plan_hash TEXT NOT NULL,
  approval_key TEXT NOT NULL, account_id TEXT NOT NULL, scheduled_at TEXT NOT NULL,
  status TEXT NOT NULL, receipt_json TEXT, error TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS outbox_status_idx ON outbox(status);
CREATE TABLE IF NOT EXISTS metrics (
  metric_id INTEGER PRIMARY KEY AUTOINCREMENT, record_id TEXT NOT NULL, phase TEXT NOT NULL,
  channel TEXT NOT NULL, provenance TEXT NOT NULL, values_json TEXT NOT NULL,
  captured_at TEXT NOT NULL, UNIQUE(record_id, phase)
);
CREATE TABLE IF NOT EXISTS feedback (
  feedback_id INTEGER PRIMARY KEY AUTOINCREMENT, record_id TEXT NOT NULL,
  body TEXT NOT NULL, provenance TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS system_state (
  singleton INTEGER PRIMARY KEY CHECK(singleton = 1), paused INTEGER NOT NULL,
  reason TEXT NOT NULL, updated_at TEXT NOT NULL
);
INSERT OR IGNORE INTO system_state(singleton, paused, reason, updated_at) VALUES(1, 0, '', '');
CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
  event_type TEXT NOT NULL, record_id TEXT NOT NULL DEFAULT '',
  payload_json TEXT NOT NULL, prev_hash TEXT NOT NULL, event_hash TEXT NOT NULL UNIQUE
);
"""

ACTIVE_WIP_STATES = (
    "IN_PRODUCTION", "REWORK", "REVIEWED", "APPROVED", "BLOCKED",
    "PREFLIGHT_BLOCKED", "PREFLIGHT_PASSED", "SCHEDULED", "PUBLISHING", "UNKNOWN",
)


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.read() as conn:
            conn.executescript(SCHEMA)
            self._migrate_legacy(conn)

    @staticmethod
    def _migrate_legacy(conn: sqlite3.Connection) -> None:
        """Make an earlier starter database safe to open; old approvals/outbox are not trusted."""
        conn.execute("DROP INDEX IF EXISTS model_calls_day_idx")
        conn.execute("DROP INDEX IF EXISTS outbox_status_idx")
        tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "metrics" in tables:
            metric_columns = {r["name"] for r in conn.execute("PRAGMA table_info(metrics)")}
            if "channel" not in metric_columns:
                conn.execute("ALTER TABLE metrics ADD COLUMN channel TEXT NOT NULL DEFAULT 'unknown'")
        if "records" in tables:
            columns = {r["name"] for r in conn.execute("PRAGMA table_info(records)")}
            if "workflow_state" not in columns:
                conn.execute("ALTER TABLE records ADD COLUMN workflow_state TEXT NOT NULL DEFAULT 'INTAKE'")
            if "revision_count" not in columns:
                conn.execute("ALTER TABLE records ADD COLUMN revision_count INTEGER NOT NULL DEFAULT 0")
            if "production_started_at" not in columns:
                conn.execute("ALTER TABLE records ADD COLUMN production_started_at TEXT")
        if "plans" in tables:
            columns = {r["name"] for r in conn.execute("PRAGMA table_info(plans)")}
            if "revision" not in columns:
                conn.execute("ALTER TABLE plans RENAME TO plans_legacy_untrusted")
                conn.execute("CREATE TABLE plans (plan_id INTEGER PRIMARY KEY AUTOINCREMENT, record_id TEXT NOT NULL, version INTEGER NOT NULL, content_hash TEXT NOT NULL, revision INTEGER NOT NULL, plan_hash TEXT NOT NULL, plan_json TEXT NOT NULL, critic_json TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(record_id,version,content_hash,revision))")
            if "model_calls" in tables:
                old = {r["name"] for r in conn.execute("PRAGMA table_info(model_calls)")}
                if "revision" not in old:
                    legacy_calls = conn.execute("SELECT * FROM model_calls").fetchall()
                    conn.execute("ALTER TABLE model_calls RENAME TO model_calls_legacy_untrusted")
                    conn.execute("CREATE TABLE model_calls (call_id INTEGER PRIMARY KEY AUTOINCREMENT, record_id TEXT NOT NULL, version INTEGER NOT NULL, revision INTEGER NOT NULL, stage TEXT NOT NULL, model_name TEXT NOT NULL, request_hash TEXT NOT NULL, response_json TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL DEFAULT 'RESERVED', created_at TEXT NOT NULL, completed_at TEXT, UNIQUE(record_id,version,revision,stage))")
                    for item in legacy_calls:
                        legacy_stage = f"legacy_untrusted_{item['stage']}_{item['call_id']}"
                        conn.execute("INSERT INTO model_calls(record_id,version,revision,stage,model_name,request_hash,response_json,status,created_at,completed_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                                     (item["record_id"], item["version"], 0, legacy_stage,
                                      "legacy-untrusted", item["request_hash"], "{}", "COMPLETE",
                                      item["created_at"], item["created_at"]))
                    if legacy_calls:
                        Store.append_event(object.__new__(Store), conn, "migration.legacy_model_calls_counted", payload={"count": len(legacy_calls), "decisions_trusted": False})
            if "approvals" in tables:
                old = {r["name"] for r in conn.execute("PRAGMA table_info(approvals)")}
                if "approver_role" not in old:
                    conn.execute("ALTER TABLE approvals RENAME TO approvals_legacy_untrusted")
                    conn.execute("CREATE TABLE approvals (approval_key TEXT PRIMARY KEY, record_id TEXT NOT NULL, version INTEGER NOT NULL, content_hash TEXT NOT NULL, revision INTEGER NOT NULL, plan_hash TEXT NOT NULL, approver TEXT NOT NULL, approver_role TEXT NOT NULL, decision TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL)")
            if "outbox" in tables:
                old = {r["name"] for r in conn.execute("PRAGMA table_info(outbox)")}
                if "revision" not in old:
                    conn.execute("ALTER TABLE outbox RENAME TO outbox_legacy_untrusted")
                    conn.execute("CREATE TABLE outbox (idempotency_key TEXT PRIMARY KEY, record_id TEXT NOT NULL, version INTEGER NOT NULL, content_hash TEXT NOT NULL, revision INTEGER NOT NULL, plan_hash TEXT NOT NULL, approval_key TEXT NOT NULL, account_id TEXT NOT NULL, scheduled_at TEXT NOT NULL, status TEXT NOT NULL, receipt_json TEXT, error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
        conn.execute("CREATE INDEX IF NOT EXISTS model_calls_day_idx ON model_calls(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS outbox_status_idx ON outbox(status)")

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=20, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=20000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def append_event(self, conn: sqlite3.Connection, event_type: str,
                     record_id: str = "", payload: Any = None) -> None:
        row = conn.execute("SELECT event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        previous = row["event_hash"] if row else "GENESIS"
        created = iso_now()
        payload_json = canonical_json(payload if payload is not None else {})
        event_hash = digest({"created_at": created, "event_type": event_type,
                             "record_id": record_id, "payload_json": payload_json,
                             "prev_hash": previous})
        conn.execute("INSERT INTO events(created_at,event_type,record_id,payload_json,prev_hash,event_hash) VALUES(?,?,?,?,?,?)",
                     (created, event_type, record_id, payload_json, previous, event_hash))

    def verify_audit(self) -> tuple[bool, str]:
        with self.read() as conn:
            rows = conn.execute("SELECT * FROM events ORDER BY seq").fetchall()
        previous = "GENESIS"
        for row in rows:
            expected = digest({"created_at": row["created_at"], "event_type": row["event_type"],
                               "record_id": row["record_id"], "payload_json": row["payload_json"],
                               "prev_hash": previous})
            if row["prev_hash"] != previous or row["event_hash"] != expected:
                return False, f"audit chain invalid at seq {row['seq']}"
            previous = row["event_hash"]
        return True, f"audit chain valid ({len(rows)} events)"

    @staticmethod
    def record_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {"record_id": row["record_id"], "version": row["version"],
                "content_hash": row["content_hash"], "body": json.loads(row["body_json"]),
                "workflow_state": row["workflow_state"], "revision_count": row["revision_count"],
                "production_started_at": row["production_started_at"], "updated_at": row["updated_at"]}

    def get_record(self, record_id: str) -> dict[str, Any] | None:
        with self.read() as conn:
            row = conn.execute("SELECT * FROM records WHERE record_id=?", (record_id,)).fetchone()
        return self.record_from_row(row) if row else None

    def import_record(self, body: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(body, dict):
            raise ValueError("record must be a JSON object")
        record_id = body.get("id")
        if not isinstance(record_id, str) or not record_id:
            raise ValueError("record requires a non-empty id")
        content_hash = digest(body)
        with self.tx() as conn:
            row = conn.execute("SELECT * FROM records WHERE record_id=?", (record_id,)).fetchone()
            if row:
                if row["content_hash"] != content_hash:
                    raise ValueError("record exists with different content; use edit")
                return self.record_from_row(row)
            now = iso_now()
            conn.execute("INSERT INTO records(record_id,version,content_hash,body_json,workflow_state,updated_at) VALUES(?,?,?,?,?,?)",
                         (record_id, 1, content_hash, canonical_json(body), "INTAKE", now))
            self.append_event(conn, "intake.imported", record_id, {"version": 1, "content_hash": content_hash})
        return self.get_record(record_id)

    def edit_record(self, record_id: str, body: dict[str, Any], *, max_revisions: int = 2) -> dict[str, Any]:
        if not isinstance(body, dict) or body.get("id") != record_id:
            raise ValueError("edited record must be a JSON object with its immutable id")
        new_hash = digest(body)
        with self.tx() as conn:
            old = conn.execute("SELECT * FROM records WHERE record_id=?", (record_id,)).fetchone()
            if not old:
                raise KeyError(record_id)
            if old["content_hash"] == new_hash:
                return self.record_from_row(old)
            inflight = conn.execute("SELECT status FROM outbox WHERE record_id=? AND status IN ('PUBLISHING','UNKNOWN') LIMIT 1",
                                    (record_id,)).fetchone()
            if inflight:
                raise ValueError(f"cannot edit while publish is {inflight['status']}; reconcile first")
            old_body = json.loads(old["body_json"])
            old_flags = old_body.get("risk_flags") or {}
            new_flags = body.get("risk_flags") or {}
            old_sensitive = isinstance(old_flags, dict) and old_flags.get("sensitive") is True
            new_sensitive = isinstance(new_flags, dict) and new_flags.get("sensitive") is True
            if old_sensitive and not new_sensitive:
                raise ValueError("sensitive-data hard lock cannot be removed through dossier edits")
            has_plan = conn.execute("SELECT 1 FROM plans WHERE record_id=? AND version=? AND content_hash=? LIMIT 1",
                                    (record_id, old["version"], old["content_hash"])).fetchone()
            revision_count = old["revision_count"] + (1 if has_plan else 0)
            if revision_count > max_revisions:
                raise ValueError("edit would exceed bounded review/rework cycles")
            state = "REWORK" if has_plan else ("SENSITIVE_LOCKED" if old_sensitive else "INTAKE")
            version = old["version"] + 1
            conn.execute("UPDATE records SET version=?,content_hash=?,body_json=?,workflow_state=?,revision_count=?,updated_at=? WHERE record_id=?",
                         (version, new_hash, canonical_json(body), state, revision_count, iso_now(), record_id))
            conn.execute("UPDATE outbox SET status='CANCELLED_STALE',error='canonical record edited; approval/preflight invalidated',updated_at=? WHERE record_id=? AND status='SCHEDULED'",
                         (iso_now(), record_id))
            self.append_event(conn, "record.edited", record_id,
                              {"version": version, "content_hash": new_hash, "rework_cycle": revision_count})
        return self.get_record(record_id)

    def pause_state(self) -> tuple[bool, str]:
        with self.read() as conn:
            row = conn.execute("SELECT paused,reason FROM system_state WHERE singleton=1").fetchone()
        return bool(row["paused"]), row["reason"]

    def set_paused(self, paused: bool, reason: str) -> None:
        with self.tx() as conn:
            conn.execute("UPDATE system_state SET paused=?,reason=?,updated_at=? WHERE singleton=1",
                         (int(paused), reason, iso_now()))
            self.append_event(conn, "system.paused" if paused else "system.resumed",
                              payload={"reason": reason})

    def active_wip(self) -> int:
        placeholders = ",".join("?" for _ in ACTIVE_WIP_STATES)
        with self.read() as conn:
            return int(conn.execute(f"SELECT COUNT(*) FROM records WHERE workflow_state IN ({placeholders})",
                                    ACTIVE_WIP_STATES).fetchone()[0])

    def open_blockers(self, record_id: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM blockers WHERE status='OPEN'"
        args: tuple[Any, ...] = ()
        if record_id:
            sql += " AND record_id=?"
            args = (record_id,)
        sql += " ORDER BY due_at,created_at"
        with self.read() as conn:
            return [dict(r) for r in conn.execute(sql, args).fetchall()]

    def latest_plan(self, record_id: str, version: int, content_hash: str) -> dict[str, Any] | None:
        with self.read() as conn:
            row = conn.execute("SELECT * FROM plans WHERE record_id=? AND version=? AND content_hash=? ORDER BY revision DESC LIMIT 1",
                               (record_id, version, content_hash)).fetchone()
        return dict(row) if row else None

    def approval_roles(self, record_id: str, version: int, content_hash: str,
                       revision: int, plan_hash: str) -> list[str]:
        with self.read() as conn:
            rows = conn.execute("SELECT a.approver_role,d.decision FROM approvals a JOIN approval_decisions d USING(approval_key) WHERE a.record_id=? AND a.version=? AND a.content_hash=? AND a.revision=? AND a.plan_hash=? ORDER BY d.decision_id",
                                (record_id, version, content_hash, revision, plan_hash)).fetchall()
        latest: dict[str, str] = {}
        for row in rows:
            latest[row["approver_role"]] = row["decision"]
        return [role for role, decision in latest.items() if decision == "approve"]

    def latest_approval(self, record_id: str, version: int, content_hash: str,
                        revision: int, plan_hash: str) -> dict[str, Any] | None:
        with self.read() as conn:
            row = conn.execute("SELECT a.*,d.decision AS latest_decision FROM approvals a JOIN approval_decisions d USING(approval_key) WHERE a.record_id=? AND a.version=? AND a.content_hash=? AND a.revision=? AND a.plan_hash=? ORDER BY d.decision_id DESC LIMIT 1",
                               (record_id, version, content_hash, revision, plan_hash)).fetchone()
        return dict(row) if row else None
