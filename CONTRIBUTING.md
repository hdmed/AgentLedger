# Contributing to AgentLedger

## Ground rules

- **Python 3.10+ stdlib only.** No new runtime dependencies — the frozen
  EXE must work on a machine without Python or packages.
- **Read-only sources.** Connectors open databases with `mode=ro` and never
  write to source folders (SQLite, transcripts, telemetry).
- **Additive merge.** A missing or failing source must never delete other
  sources' sessions. Dedup key: `(source, source_session_id)`.
- **Fixtures first.** Every connector ships dummy-database fixtures covering
  nominal, empty, deleted, corrupt and unknown-schema cases
  (`tests/test_<source>.py`).
- **English first.** User-facing strings, docs and report UI in English.

## Workflow

1. `python -m unittest discover -s tests -v` — all green before pushing.
2. `python build_report.py --strict` — report builds offline.
3. New connector? Follow `extract_workbuddy.py` (smallest full example):
   `default_db_path()` (+ env override), `inspect_schema()`,
   `fetch_sessions()`, `extract()`, `max_time()`, separate
   `data/<source>_sync_state.json`, `--no-<source>` launcher flag,
   `Docs/<Source>.md` with the observed schema and fallbacks.
4. Template change? Run `node --check` on the extracted `<script>` and keep
   canvas `id`s unique across views.

## Bug reports

Open a GitHub issue with: what you ran, `python launcher.py --diagnose`
output, and the relevant log lines. Never paste API keys, tokens, database
contents or conversation text — describe the schema, not the data.
