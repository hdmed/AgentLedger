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
- Report UI in 10 locales (EN, FR, ES, PT, ZH, HI, AR, BN, RU, ID):
  strings centralized in `locales/*.json`, inlined at build
  (`/*__LOCALES__*/`), header selector, RTL Arabic, per-locale numbers
  (`CONTRIBUTING.md#translating`).
- Luxury "noir champagne" theme: serif gold title, gold tab rule, serif
  tabular KPIs, refined chart palette, bronze light theme.
- Overview models trio row (tokens / requests / cost doughnuts per model)
  and token stats in M/K (`fmtTok`).
- `tests/test_i18n.py` (locale parity/placeholders/coverage) and
  `tests/test_foreign_sources.py` (extract preservation).

### Fixed
- OpenCode millisecond timestamps normalized to seconds (`to_seconds()`,
  adaptive `db_threshold()`); fixes budgets, `--since`, sorting.
- `dayFrom()` handles seconds and milliseconds datasets.
- `renderBudgets()` 30-day window compared in matching units.
- `parse_model()` accepts connector `provider/model` strings and dicts
  (was clobbering labels to `unknown`).
- `extract.py` no longer drops foreign-source sessions on incremental or
  `--full` runs (they are owned by their connectors and carried over).
- Anomaly badge mojibake (`ðŸ“ˆ`/`Ïƒ` → 📈/`σ`).
- Full-page `assets/thumbnail.png` regenerated (1280×2200).

### Changed
- **Renamed OpenCost → AgentLedger** (SEO collision with CNCF OpenCost).
  User folder moved to `%LOCALAPPDATA%\AgentLedger`; rename the old
  `%LOCALAPPDATA%\OpenCost` folder to migrate (or set `OPENCOST_USER_DIR`,
  still honored). Env override is now `AGENTLEDGER_USER_DIR`.
- English default with fallback (was English-only): report UI ships 10
  locales, `en` kept as the fallback language.
- Overview layout: KPI Costs/Tokens groups, trio row, models trio row.

## [1.0.0] — OpenCode-only offline report

- Incremental `opencode.db` extraction with pricing overrides and budgets.
- Single-file offline HTML report (vendored Chart.js).
- PyInstaller one-file Windows executable.
