# Verification record — CIA Control Plane Starter v2

- Python runtime: 3.12; standard-library runtime.
- `python -m compileall -q src tests`: passed.
- `PYTHONPATH=src python -m unittest discover -s tests -v`: **48 tests passed, 0 failures/errors**. Includes a legacy v1 SQLite migration fixture proving old plan/approval/outbox payloads are quarantined, old model responses are not replayable, and prior call counts still consume the per-record budget.
- `PYTHONPATH=src python -m cia_control_plane.cli --db /tmp/cia-v2-release-demo.sqlite3 demo`: completed all nine stages at pinned 2026-11-03T12:00Z; it opened two role-owned blockers, resolved both with synthetic evidence, re-triaged and re-reviewed, obtained version-bound demo approval, passed deterministic preflight, and produced a simulated receipt.
- Fresh demo DB inspection: 1 record at `PUBLISHED` workflow state, 2 resolved blockers with evidence, 6 simulated model calls (2 semantic triage, 2 planner, 2 critic), 1 simulated outbox receipt with `public_url: null`, and 2 `SIMULATED_DEMO` metric rows. Audit chain valid (see demo output).
- Architecture exports were copied unchanged from parent source; all three SHA-256 checksums match. The PDF is one page.

These checks verify local simulation only. No live LLM, ClickUp, social publisher, analytics source, IAM, due-time background worker, or message service is connected. The acceptance target “one blocked brief → verified live receipt without manual chasing” remains NOT MET. This package is reviewer-ready, not production-ready.
