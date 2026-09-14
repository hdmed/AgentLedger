# AutoClaw / OpenClaw connector

## Location and status

AgentLedger reads AutoClaw telemetry (`telemetry/journal.js`, aggregated
per session, with a `telemetry/latest.js` fallback when the journal is
missing or empty). The connector is implemented in
`extract_autoclaw.py`: strictly read-only, never launching or modifying
any collector. Additive merge into the dataset via
`(source, source_session_id)` with `source="autoclaw"`.

> Note: the previously vendored copy under `Docs/AutCLW/TDB/` is no
> longer shipped with this repository. Feed the connector through one
> of the locations below.

## Telemetry locations (first existing one wins)

1. `AUTOCLAW_TELEMETRY_DIR` environment variable (explicit override);
2. canonical per-user folder `%LOCALAPPDATA%\AgentLedger\telemetry`
   (`extract_autoclaw.canonical_dir()`) — **put your `journal.js` /
   `latest.js` here**;
3. frozen EXE only: `telemetry/` next to the EXE;
4. legacy fallback: `Docs/AutCLW/TDB/openclaw-tdb/telemetry` next to the
   source tree (no longer vendored; kept for backward compatibility).

`--autoclaw-dir` overrides all of the above. When nothing exists, the
connector reports `missing` and other sources are preserved.
`launcher --diagnose` lists every candidate and its status
(`autoclaw_candidat`).

## Collecting telemetry

Collection itself is outside AgentLedger: run your TDB/OpenClaw
collector (read-only for OpenClaw; it only writes the telemetry
folder), then copy the resulting `journal.js` / `latest.js` (and
optionally `history.jsonl`) into the canonical folder above, or point
`AUTOCLAW_TELEMETRY_DIR` at the collector output. No writes are ever
made to `C:\Program Files\AutoClaw`, `~\.openclaw` or
`~\.openclaw-autoclaw`.

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
- Telemetry lookup order: `AUTOCLAW_TELEMETRY_DIR`, canonical
  `%LOCALAPPDATA%\AgentLedger\telemetry`, frozen-EXE `telemetry/`,
  legacy vendored path. `launcher --diagnose` lists candidates and
  their status (`autoclaw_candidat`).

## Sources read

The external TDB collector produces, from read-only OpenClaw inputs:

- the OpenClaw CLI (gateway install) `status --json` snapshot;
- transcripts `~\.openclaw-autoclaw\agents\*\sessions\*.jsonl` for the action journal;
- output files `telemetry\journal.js`, `telemetry\latest.js`
  (plus `history.jsonl`, `stats-aggregates.json`) for dashboards.

Collection is read-only for OpenClaw. Writes are limited to the
telemetry folder, which AgentLedger then reads.

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
