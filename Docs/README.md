# AgentLedger — documentation

## Positioning

AgentLedger extracts local AI agent sessions from on-disk databases and
builds a standalone offline HTML dashboard — no network calls.

The goal is a single local executable tracking activity and cost for
OpenCode, AutoClaw/OpenClaw, Kilo/KiloCode, WorkBuddy and other agents,
with no cloud sync.

## Current architecture

- `extract.py` reads `opencode.db` in read-only SQLite mode, applies pricing
  and budgets, then writes the generated data.
- `extract_kilo.py`, `extract_autoclaw.py`, `extract_workbuddy.py` are
  read-only connectors for their respective sources, each with its own
  watermark state file.
- `launcher.py` merges all sources additively (dedup key
  `(source, source_session_id)`), then builds the report.
- `build_report.py` assembles the dataset, `templates/report_template.html`
  and vendored `assets/chart.umd.min.js` into `dist/report.html`.
- `resources.py` resolves source/frozen paths and the user folder.
- `build_exe.py` produces a one-file Windows PyInstaller executable;
  `--onedir` builds a debug-friendly folder.
- `config/pricing.json` holds USD prices per million tokens, keyed
  `providerID/modelID`.
- `config/budgets.json` holds global, per-project and per-model caps over a
  rolling 30-day window.
- `data/dataset.json`, `data/*_sync_state.json` and `dist/report.html` are
  generated artifacts ignored by Git.

Current flow:

```text
Local SQLite / telemetry -> read-only connectors -> additive merge -> dataset -> offline HTML report
```

## Target architecture

```text
Local bases / sources
  OpenCode | AutoClaw/OpenClaw | Kilo/KiloCode | WorkBuddy | other agents
               |
         read-only connectors
               |
        common activity model
               |
        sync + dedup
               |
        unified local dataset
               |
        offline dashboard
               |
        standalone executable
```

## Invariants

- Read source databases read-only; never modify them to build the report.
- Keep each session's origin and a stable id for dedup.
- Normalize dates to UTC and costs to USD (WorkBuddy plan credits excepted
  and labeled — see `WorkBuddy.md`).
- Keep offline as the default mode.
- Separate configuration, user data and generated artifacts.
- Add dummy-database fixtures for each connector before packaging.

## Common commands

```powershell
python -m py_compile extract.py extract_kilo.py extract_autoclaw.py extract_workbuddy.py build_report.py resources.py launcher.py build_exe.py notification.py
python -m unittest discover -s tests -v
python build_report.py --strict
python launcher.py --diagnose
python launcher.py --no-open --full
python build_exe.py --confirm
```

`make test`, `make report`, `make all`, `make watch`, `make open` and
`make clean` remain available when `make` is installed. On Windows, the
direct Python commands are the verifiable fallback.

## Verification

CI runs on Python 3.11 (Linux + Windows): compile entrypoints, run tests,
then `build_report.py --strict`. `--strict` verifies the Chart.js asset.
`--external` creates an adjacent dataset and needs an HTTP server: it is not
fully standalone. The EXE keeps data and user configuration under
`%LOCALAPPDATA%\AgentLedger` and keeps source databases read-only.

## Index

- [Target architecture and data model](architecture.md)
- [Dashboard — structure and navigation](dashboard.md)
- [AutoClaw / OpenClaw connector](AutCLW.md)
- [WorkBuddy connector](WorkBuddy.md)
- [Roadmap](plan.md)
