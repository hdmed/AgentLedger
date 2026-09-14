# Architecture and target data model

## Scope

The target product is a single local dashboard covering multiple agents.
The first versions stay readable, offline and portable; they never replace
the source databases.

## Proposed layers

1. **Connectors**: read-only opening, incremental reads, version detection
   and mapping onto the common model.
2. **Common model**: normalized representation of a session and its metrics.
3. **Sync**: per-source watermark, merge, dedup and local state.
4. **Report**: filters, KPIs, charts, table, exports and cost customization.
5. **Packaging**: bundled resources, user configuration, diagnostics and
   Windows launching.

## Minimal activity contract

Each normalized record carries:

- `source`: connector name, e.g. `opencode`, `autoclaw`, `kilo`, `workbuddy`.
- `source_session_id`: stable id within the source.
- `project`, `agent`, `model_provider`, `model_id`.
- `time_created`, `time_updated`: UTC-normalized timestamps (seconds).
- `tokens_input`, `tokens_output`, `tokens_reasoning`, `tokens_cache_read`,
  `tokens_cache_write`.
- `cost`, currency and cost origin (`source` or `pricing`).
- a provenance reference enabling diagnosis without duplicating raw data.

Fields missing from a source stay optional; they must not block other
sources' imports.

## Connectors

### OpenCode

Reads the `session` table, joins `project`, uses
`time_updated`/`time_created` as watermark and opens SQLite with `mode=ro`.
Recent databases store **milliseconds** — normalized to seconds by
`to_seconds()` (adaptive `db_threshold()` for incremental filtering).

### AutoClaw / OpenClaw

Reads existing `telemetry/journal.js` (aggregated per session) with a
`latest.js` snapshot fallback, strictly read-only — AgentLedger never
runs a collector itself. Details and field mapping:
[AutoClaw / OpenClaw connector](AutCLW.md).

### Kilo / KiloCode

Reads `kilo.db` read-only (`mode=ro`), `session` + `message`/`part`
fallback metrics for tokens, model and cost. Independent watermark in
`data/kilo_sync_state.json`.

### WorkBuddy

Reads `workbuddy.db` read-only: `sessions` + `session_usage` (context fill
and plan **credits, not USD**). Details: [WorkBuddy connector](WorkBuddy.md).

### Other agents

A new agent needs an adapter, fixtures and a dedup strategy. The dashboard
must not know each source's SQL details.

## Data and paths

- Versioned configuration: `config/pricing.json`, `config/budgets.json`.
- State and dataset: local data folder, currently `data/`.
- Report: `dist/report.html`.
- AutoClaw input telemetry: canonical `%LOCALAPPDATA%\AgentLedger\telemetry`
  (plus `AUTOCLAW_TELEMETRY_DIR` / frozen-mode candidates — see `AutCLW.md`).
- For the EXE, resources come from the PyInstaller bundle and data, state,
  reports and user configuration live under `%LOCALAPPDATA%\AgentLedger`
  (or `AGENTLEDGER_USER_DIR`; legacy `OPENCOST_USER_DIR` still honored).

## Security and privacy

- Data stays local.
- Connectors must never send sessions to a remote service.
- Exports and diagnostics must avoid secrets, API tokens or unneeded
  sensitive paths.
- Schema errors must be explicit without exposing raw session content.

## Performance

- Keep incremental reads and per-source watermarks.
- Plan an external/paginated mode if the dataset grows too large to stay
  reasonably inline.
- Test with several thousand sessions before validating packaging.
- Measure extraction, merge and render times separately.
- Measured 2026-09-13 (5200 sessions: 3000 OpenCode, 2000 Kilo,
  200 AutoClaw): extraction 0.4/0.5/0.2 s, merge 1.3 s, render 0.2 s
  (2.9 MB), second incremental pass 0.7 s. Connectors skip state rewrites
  when nothing changed.
