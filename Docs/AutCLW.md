# AutoClaw / OpenClaw connector

## Location and status

The AutoClaw project is vendored under [`Docs/AutCLW/`](AutCLW/). Its
standalone dashboard lives in [`Docs/AutCLW/TDB/`](AutCLW/TDB/) and collects
OpenClaw metrics without modifying source databases or transcripts.

AgentLedger reuses this project as a local source. The connector is
implemented in `extract_autoclaw.py`: read-only reads of
`telemetry/journal.js` (aggregated per session) with a `telemetry/latest.js`
fallback when the journal is missing or empty — never launching or modifying
`collect.ps1`. Additive merge into the dataset via
`(source, source_session_id)` with `source="autoclaw"`.

Decisions made during implementation:

- `source` = `autoclaw`; `source_session_id` = `journal:<session>` (primary)
  or `snapshot:<key>` (fallback, never combined with the journal to avoid
  double counting).
- `project` = AutoClaw `agent` (no workspace in the journal);
  `agent` = `journal.agent`.
- `model` = `provider/model` (`provider` from the journal when the model is
  unqualified); `time_created`/`time_updated` = min/max of `ts` in UTC.
- `tokens_input`/`tokens_output`/`tokens_cache_read` summed; unventilated
  `tokens` counted as input (controlled fallback); zero journal cost with
  `cost_source` resolved at merge time (`pricing` on override, else
  `autoclaw`).
- Separate state `data/autoclaw_sync_state.json`, independent watermark,
  `--autoclaw-dir`, `--autoclaw-full`, `--autoclaw-since`, `--no-autoclaw`
  options (`AUTOCLAW_TELEMETRY_DIR` env).
- In frozen EXE mode the folder is auto-detected in order:
  `AUTOCLAW_TELEMETRY_DIR`, `telemetry/` next to the EXE,
  `%LOCALAPPDATA%\AgentLedger\telemetry`,
  `..\Docs\AutCLW\TDB\openclaw-tdb\telemetry` (`dist/` layout), bundled
  telemetry. `launcher --diagnose` lists candidates and their status
  (`autoclaw_candidat`).

## Sources read

The existing collector
[`Docs/AutCLW/TDB/openclaw-tdb/collect.ps1`](AutCLW/TDB/openclaw-tdb/collect.ps1)
uses:

- the OpenClaw CLI, by default `C:\Program Files\AutoClaw\resources\gateway\openclaw\openclaw.mjs`
  or `~\.openclaw\openclaw.mjs`;
- `status --json` for the gateway snapshot;
- transcripts `~\.openclaw-autoclaw\agents\*\sessions\*.jsonl` for the action journal;
- output files in `openclaw-tdb\telemetry\` for the dashboard.

Collection is read-only for OpenClaw. Writes are limited to the AutoClaw
telemetry folder.

## Observed data contract

### Snapshot

`telemetry\latest.js` exposes `window.TDB_REMOTE` with:

- `ts`, `model`, `provider`, `runtimeVersion`;
- `runIn`, `runOut`, `totalTokens`, `costUsd`;
- `cacheHitPct`, `cachedTokens`, `contextTokens`, `contextLimit`;
- `sessionsActive`, `sessionsTotal`, `agentsTotal`, `cronsTotal`, `channels`;
- `sessions[]` with `key`, `channel`, `model`, `tokens`, `cost`, `status`;
- `agents[]` with `id`, `name`, `model`, `active`.

`telemetry\history.jsonl` keeps snapshots over time. `costUsd` and
`sessions[].cost` are currently optional and often `null`.

### Action journal

`telemetry\journal.js` exposes `window.TDB_JOURNAL` with:

- `ts`, `agent`, `session`, `task`, `action`;
- `provider`, `model`, `durationMs`;
- `tokens`, `inputTokens`, `outputTokens`, `cacheReadTokens`;
- `tokenStatus` (`reported`, `estimated` or `unknown`);
- `state`.

`telemetry\stats-aggregates.json` keeps cumulative totals, per-model split
and event counters. These aggregates must not be confused with the detailed
sessions AgentLedger uses.

## Mapping onto the common model

| Common model | AutoClaw candidate | Note |
|---|---|---|
| `source` | connector name | `autoclaw` |
| `source_session_id` | `sessions[].key` or `journal.session` | prefixed `journal:` / `snapshot:` |
| `project` | AutoClaw `agent` | no workspace in the journal |
| `agent` | `journal.agent` | AutoClaw agent id |
| `model_provider` | part before `/` of `model` | optional when unqualified |
| `model_id` | part after `/` of `model` | raw value kept |
| `time_created` / `time_updated` | `ts` | UTC normalized |
| `tokens_input` / `tokens_output` | `inputTokens` / `outputTokens` | `tokens` as controlled fallback |
| `tokens_cache_read` | `cacheReadTokens` | optional |
| `cost` | `costUsd` or `sessions[].cost` | pricing rule when source is null |
| `cost_source` | `source` or `pricing` | computation provenance kept |

Missing fields stay optional. A costless session or action must not block
other sources' imports.

## Acceptance criteria

- Missing OpenClaw, empty transcripts or partial schema: explicit diagnosis,
  other sources' imports preserved.
- Two collections of the same session create no duplicate.
- No writes to `C:\Program Files\AutoClaw`, `~\.openclaw` or
  `~\.openclaw-autoclaw`.
- The AgentLedger report stays fully offline after merging.
- Optional fields and zero costs display without breaking the build.

## Existing AutoClaw documentation

- [Project overview](AutCLW/README.md)
- [TDB installation](AutCLW/TDB/docs/INSTALL.md)
- [TDB usage](AutCLW/TDB/docs/USAGE.md)
