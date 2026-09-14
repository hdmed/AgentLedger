# Roadmap

## Goal

Ship a standalone Windows executable that locally consolidates activity and
cost for OpenCode, AutoClaw/OpenClaw, Kilo/KiloCode, WorkBuddy and then other
agents, in a single dashboard.

## Current state

Done: OpenCode + Kilo/KiloCode + AutoClaw/OpenClaw + WorkBuddy flow into one
offline report with a shared activity model, additive merge, per-source
watermarks, source filter, and a PyInstaller one-file EXE with user folder,
diagnostics and smoke tests. CI runs on Linux and Windows.

## Phase 0 — Stabilize the base ✅

- Green compile + test suite on Python 3.11, green `--strict` build.
- Dummy-database fixtures per connector; no generated artifact versioned.

## Phase 1 — Common model and connector contract ✅

- Common activity model + connector interface.
- Provenance, stable ids, UTC normalization (seconds), USD costs.
- Nominal, empty, deleted and unknown-schema fixtures.

## Phase 2 — AutoClaw / OpenClaw connector ✅

- Read-only reads of `telemetry/` snapshots, journal and aggregates.
- Mapping with documented optional fields; fixtures from `sample-data/`.
- Incremental import without touching OpenClaw; snapshot/session dedup.

## Phase 3 — Kilo / KiloCode connector ✅

- `KILO_DB` detection, `mode=ro` opening, non-destructive schema inventory.
- Stable identity `source="kilo"`, ms→UTC dates, message/part metric
  fallback, source cost preferred else `pricing.json`.
- Dedicated CLI flags, separate sync state, full fixtures (nominal, empty,
  updated, unknown schema, locked/corrupt).
- `(source, source_session_id)` dedup merge, `source` filter in the report.

## Phase 3b — WorkBuddy connector ✅

- `WORKBUDDY_DB` detection, `mode=ro` opening of a live database.
- Context-fill tokens as controlled input fallback, **plan credits**
  imported as cost with `cost_source="workbuddy"` (explicitly not USD).

## Phase 4 — Unified dashboard ✅

- Merged view, source filter, KPIs, charts, budgets, table, exports.
- Tabbed navigation (Overview / Models / Projects / Sessions), sticky
  filter bar, session detail drawer, fully offline rendering.

## Phase 5 — Multi-source standalone executable ✅

- Reproducible PyInstaller one-file (and one-folder debug) builds.
- Frozen user folder for config, dataset, watermarks and reports.
- Launcher with diagnostics, report opening and extraction modes.
- Smoke-tested frozen runs for all four sources.

## Phase 6 — Unified connectors and robustness ✅ (ongoing)

- Multi-thousand-session performance tests (separate timings).
- Locked bases, corrupt JSON rotation, per-source failure isolation.
- Diagnostics without sensitive data.
- Windows CI for compile, tests, report build and EXE build.

## Open decisions

1. WorkBuddy credits vs USD totals: currently mixed with origin labels;
   decide whether to exclude non-USD costs from USD totals.
2. Data retention policy and maximum merged dataset size.
3. EXE size, startup and multi-source update strategy.
4. Next connectors (Claude Code, Copilot, …): inventory first, no assumed schema.
