# OpenCost

## Documentation
- Start with `Docs/README.md`; use `Docs/architecture.md` for the target architecture and `Docs/plan.md` for the implementation roadmap.

## System
- stdlib-only Python 3.10+; there is no package manager or dependency installation step.
- `extract.py` reads the OpenCode SQLite database in read-only mode and writes `data/dataset.json` plus `data/sync_state.json`.
- `build_report.py` turns the dataset, `templates/report_template.html`, and vendored `assets/chart.umd.min.js` into the standalone `dist/report.html`.
- `launcher.py` runs extraction, report generation, diagnostics, and browser opening for the source tree or frozen executable.
- `build_exe.py` builds the Windows executable with PyInstaller; the frozen app stores generated data and user configuration under `%LOCALAPPDATA%\OpenCost`.
- Generated `data/dataset.json`, `data/sync_state.json`, and `dist/report.html` are ignored; do not treat them as source files.
- `--external` writes an adjacent `dataset.json` and makes the report fetch it, so the result is not fully standalone.

## Commands
- `make test` — compile all Python entrypoints, then run `unittest discover -s tests -v`.
- `make report` — incremental extraction followed by report generation.
- `make all` — full extraction followed by `make report`.
- `make watch` — watch the database and regenerate the report; optional `watchdog` falls back to polling.
- `make open` — open the generated report.
- `make open-app` — run the source-tree launcher.
- `make exe` — build the one-file Windows executable.
- `make exe-debug` — build the one-folder executable for diagnosis.
- `make clean` — remove generated dataset, sync state, and report.
- Focused tests: `python -m unittest tests/test_extract.py`, `tests/test_build.py`, `tests/test_resources.py`, `tests/test_launcher.py`, or `tests/test_integration.py`.

## Data and configuration
- Set `OPENCODE_DB` or pass `--db <path>`; the Windows default is `%USERPROFILE%\.local\share\opencode\opencode.db`.
- In the frozen app, generated data, sync state, report, and editable configuration live under `%LOCALAPPDATA%\OpenCost`; source-tree runs use the repository paths unless `OPENCOST_USER_DIR` is set.
- `config/pricing.json` uses `providerID/modelID` keys and USD prices per 1 million tokens. After changing it, run `python extract.py --full && python build_report.py` (or `make all`). Models without an override retain OpenCode's cost.
- `config/budgets.json` contains global, project, and model limits evaluated over a rolling 30-day window.

## Verification
- CI uses Python 3.11: `py_compile`, all `unittest` tests, then `python build_report.py --strict` (creating a dummy dataset only when the ignored dataset is absent).
- Use `--strict` when verifying that the vendored Chart.js asset is present.
