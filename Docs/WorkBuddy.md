# WorkBuddy connector

WorkBuddy AI (desktop app, found under
`%LOCALAPPDATA%\Programs\WorkBuddyAI`) is integrated via
`extract_workbuddy.py`: **read-only** SQLite reads (`mode=ro`) of
`~\.workbuddy-ai\workbuddy.db`, without writing or locking the database
(which stays usable by the running application).

## Observed schema (non-destructive inventory)

- `sessions`: `id`, `cwd`, `title`/`custom_title`, `status`, `created_at`,
  `updated_at`, `last_activity_at`, `deleted_at` (**milliseconds**),
  `mode` (e.g. `craft`), `model` (**bare name**, e.g. `deepseek-v4.1-flash`),
  `project_id` (often `NULL`).
- `session_usage`: `session_id`, `used`/`size` (context-window fill),
  `updated_at`, `credit_json` (`{uuid: amount}`).
- Ignored tables: `workspaces` (empty), `automations`, `buddy_snapshots`,
  `*_outbox`, migrations.

## Mapping onto the common model

| Common model | WorkBuddy field | Note |
|---|---|---|
| `source` | `workbuddy` | constant |
| `source_session_id` | `sessions.id` | stable |
| `project` | basename of `cwd` | `project_id` is `NULL`, `?` fallback |
| `agent` | `mode` | e.g. `craft` |
| `model_provider` | `?` | model names are unqualified |
| `model_id` | `sessions.model` | raw value kept |
| `time_created` / `time_updated` | `created_at` / `max(updated_at, last_activity_at)` | ms → s UTC |
| `tokens_input` | `session_usage.used` | **controlled fallback**: context fill, not billed tokens |
| `tokens_output` / others | `0` | unavailable in the source |
| `cost` | sum of `credit_json` | **WorkBuddy plan credits, NOT USD** (see below) |
| `cost_source` | `pricing` on override, else `workbuddy` | resolved at merge |
| `archived` | `deleted_at IS NOT NULL` | deleted sessions kept with flag |

## Cost-unit warning

WorkBuddy bills via a **Token Plan** (credit quota), not per token:
imported amounts are **credits**, mixed with USD in dataset totals.
`cost_source="workbuddy"` and the report's Cost column tell them apart;
do not compare them head-on with other sources' USD costs. A creditless
session imports at an explicit `0.0`.

## Behavior

- Independent watermark on `updated_at` (seconds), separate state
  `data/workbuddy_sync_state.json` (sessions cached, no rewrite when
  nothing is new).
- Missing `session_usage` → zero tokens and cost, import preserved.
- Missing, locked, corrupt database or unknown schema → explicit
  `missing`/`error` status, other sources preserved.
- Options: `--workbuddy-db`, `--workbuddy-full`, `--workbuddy-since`,
  `--no-workbuddy` (`WORKBUDDY_DB` env). Default Windows path:
  `%USERPROFILE%\.workbuddy-ai\workbuddy.db` (also works frozen).
- `launcher --diagnose` shows `workbuddy_database(_exists)` and
  `workbuddy_state`.

## Related files

- Connector: `extract_workbuddy.py`
- Tests: `tests/test_workbuddy.py` (fixtures faithful to the observed schema)
- Merge: `launcher.merge_source_result` (`(source, source_session_id)` key)
