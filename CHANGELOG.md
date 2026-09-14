# Changelog

All notable changes to AgentLedger are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- WorkBuddy connector (`extract_workbuddy.py`): read-only `workbuddy.db`
  sessions + plan credits, launcher flags, `Docs/WorkBuddy.md`.
- Tabbed dashboard (Overview / Models / Projects / Sessions), sticky
  compact filter bar, session detail drawer (`Docs/dashboard.md`).
- AutoClaw telemetry auto-detection for frozen EXE (`candidate_dirs()`).
- Windows CI: compile, tests, `--strict` report, EXE build + smoke test.
- `resources.basename_crossplatform()` shared by all connectors.

### Fixed
- OpenCode millisecond timestamps normalized to seconds (`to_seconds()`,
  adaptive `db_threshold()`); fixes budgets, `--since`, sorting.
- `dayFrom()` handles seconds and milliseconds datasets.
- `renderBudgets()` 30-day window compared in matching units.
- `parse_model()` accepts connector `provider/model` strings and dicts
  (was clobbering labels to `unknown`).

### Changed
- **Renamed OpenCost → AgentLedger** (SEO collision with CNCF OpenCost).
  User folder moved to `%LOCALAPPDATA%\AgentLedger`; rename the old
  `%LOCALAPPDATA%\OpenCost` folder to migrate (or set `OPENCOST_USER_DIR`,
  still honored). Env override is now `AGENTLEDGER_USER_DIR`.
- English as the primary language: CLI, logs, docs and report UI.
- Full-width rows for the 3 bottom Overview charts.

## [1.0.0] — OpenCode-only offline report

- Incremental `opencode.db` extraction with pricing overrides and budgets.
- Single-file offline HTML report (vendored Chart.js).
- PyInstaller one-file Windows executable.
