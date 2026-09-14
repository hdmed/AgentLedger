from __future__ import annotations

import argparse
import json
import logging
import os
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import resources

SOURCE = "autoclaw"
AUTOCLAW_STATE_PATH = resources.data_path("autoclaw_sync_state.json")
SCHEMA_JOURNAL = "journal-v1"
SCHEMA_SNAPSHOT = "snapshot-v1"

logger = logging.getLogger("agentledger.autoclaw")


class AutoclawSchemaError(RuntimeError):
    pass


def canonical_dir() -> str:
    """Canonical per-user telemetry folder (first choice when it exists).

    Copy `journal.js` / `latest.js` (as produced by the TDB collector)
    into this folder, or point `AUTOCLAW_TELEMETRY_DIR` / `--autoclaw-dir`
    at your own location.
    """
    return os.path.join(resources.user_root(), "telemetry")


def legacy_dir() -> str:
    """Historical vendored location (kept as a last-resort fallback)."""
    return resources.resource_path(
        "Docs", "AutCLW", "TDB", "openclaw-tdb", "telemetry"
    )


def candidate_dirs() -> list[str]:
    """telemetry/ locations searched in order (first existing one wins)."""
    candidates: list[str] = []
    override = os.environ.get("AUTOCLAW_TELEMETRY_DIR")
    if override:
        candidates.append(os.path.abspath(os.path.expanduser(override)))
    candidates.append(canonical_dir())
    if resources.is_frozen():
        import sys as _sys
        exe_dir = os.path.dirname(os.path.abspath(_sys.executable))
        candidates.append(os.path.join(exe_dir, "telemetry"))
    candidates.append(legacy_dir())
    seen: list[str] = []
    for path in candidates:
        norm = os.path.normpath(path)
        if norm not in seen:
            seen.append(norm)
    return seen


def default_dir() -> str:
    override = os.environ.get("AUTOCLAW_TELEMETRY_DIR")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    for path in candidate_dirs():
        if os.path.isdir(path):
            return path
    return canonical_dir()


def _parse_ts(value: Any) -> int | None:
    """ISO timestamp (with offset) -> UTC epoch seconds. None when missing/invalid."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _split_model(provider: Any, model: Any) -> tuple[str, str]:
    """Normalise (provider, model) -> (provider_id, model_id)."""
    model = str(model or "").strip()
    if "/" in model:
        prov, mid = model.split("/", 1)
        return prov.strip() or "?", mid.strip() or "?"
    return str(provider or "?").strip() or "?", model or "?"


def _load_js_value(path: str, var: str) -> Any:
    """Read a `window.VAR = <json>;` file without executing it. Raises on invalid content."""
    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read().strip()
    prefix = "window.{}=".format(var)
    if not text.startswith(prefix):
        raise AutoclawSchemaError("{}: '{}' prefix not found".format(path, prefix))
    payload = text[len(prefix):].strip()
    try:
        # raw_decode: ignore a trailing `;` and any following variables
        # (ex. journal.js contient aussi window.TDB_HOURLY).
        value, _ = json.JSONDecoder().raw_decode(payload)
        return value
    except json.JSONDecodeError as exc:
        raise AutoclawSchemaError("{}: invalid JSON ({})".format(path, exc))


def read_journal(telemetry_dir: str) -> list[dict[str, Any]]:
    path = os.path.join(telemetry_dir, "journal.js")
    if not os.path.exists(path):
        return []
    data = _load_js_value(path, "TDB_JOURNAL")
    if not isinstance(data, list):
        raise AutoclawSchemaError("journal.js: TDB_JOURNAL array expected")
    return [e for e in data if isinstance(e, dict)]


def read_snapshot(telemetry_dir: str) -> dict[str, Any]:
    path = os.path.join(telemetry_dir, "latest.js")
    if not os.path.exists(path):
        return {}
    data = _load_js_value(path, "TDB_REMOTE")
    if not isinstance(data, dict):
        raise AutoclawSchemaError("latest.js: TDB_REMOTE object expected")
    return data


def _group_from_journal(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        sid = str(entry.get("session") or "unknown")
        groups.setdefault(sid, []).append(entry)
    sessions: list[dict[str, Any]] = []
    for sid, actions in groups.items():
        actions.sort(key=lambda e: _parse_ts(e.get("ts")) or 0)
        stamps = [_parse_ts(e.get("ts")) for e in actions]
        stamps = [t for t in stamps if t is not None]
        created = min(stamps) if stamps else 0
        updated = max(stamps) if stamps else 0
        tokens_input = tokens_output = cache_read = 0
        for entry in actions:
            if entry.get("inputTokens") is not None or entry.get("outputTokens") is not None:
                tokens_input += _integer(entry.get("inputTokens"))
                tokens_output += _integer(entry.get("outputTokens"))
            elif entry.get("tokens") is not None:
                # controlled fallback: undifferentiated total counted as input.
                tokens_input += _integer(entry.get("tokens"))
            cache_read += _integer(entry.get("cacheReadTokens"))
        labels = Counter(
            "{}/{}".format(*_split_model(e.get("provider"), e.get("model")))
            for e in actions
        )
        model_label = labels.most_common(1)[0][0] if labels else "?/?"
        provider_id, model_id = model_label.split("/", 1)
        agent = str(actions[-1].get("agent") or "?")
        title = str(actions[-1].get("task") or actions[0].get("task") or "")[:120]
        statuses = sorted({str(e.get("tokenStatus") or "unknown") for e in actions})
        sessions.append({
            "source": SOURCE,
            "source_session_id": "journal:" + sid,
            "id": "{}:journal:{}".format(SOURCE, sid),
            "project_id": None,
            "project_name": agent,
            "directory": None,
            "title": title,
            "agent": agent,
            "model": model_label,
            "cost": 0.0,
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "tokens_reasoning": 0,
            "tokens_cache_read": cache_read,
            "tokens_cache_write": 0,
            "time_created": created,
            "time_updated": updated or created,
            "archived": False,
            "schema_version": SCHEMA_JOURNAL,
            "provenance": {
                "file": "journal.js",
                "actions": len(actions),
                "token_status": ",".join(statuses),
            },
        })
    return sessions


def _sessions_from_snapshot(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    entries = snapshot.get("sessions") or []
    if not isinstance(entries, list):
        return []
    stamp = _parse_ts(snapshot.get("ts")) or 0
    sessions: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key") or "unknown")
        provider_id, model_id = _split_model(snapshot.get("provider"), entry.get("model"))
        model_label = "{}/{}".format(provider_id, model_id)
        sessions.append({
            "source": SOURCE,
            "source_session_id": "snapshot:" + key,
            "id": "{}:snapshot:{}".format(SOURCE, key),
            "project_id": None,
            "project_name": str(entry.get("channel") or "?"),
            "directory": None,
            "title": key,
            "agent": "?",
            "model": model_label,
            "cost": _number(entry.get("cost"), 0.0),
            "tokens_input": _integer(entry.get("tokens")),
            "tokens_output": 0,
            "tokens_reasoning": 0,
            "tokens_cache_read": 0,
            "tokens_cache_write": 0,
            "time_created": stamp,
            "time_updated": stamp,
            "archived": False,
            "schema_version": SCHEMA_SNAPSHOT,
            "provenance": {"file": "latest.js", "actions": 0, "token_status": "unknown"},
        })
    return sessions


def fetch_sessions(telemetry_dir: str, watermark: int = 0, full: bool = False) -> list[dict[str, Any]]:
    """Read telemetry read-only and map it onto the common model.

    Primary source: journal.js aggregated by session. Fallback: the
    latest.js snapshot sessions when the journal is missing or empty
    (never both at once, to avoid any double counting).
    """
    if not os.path.isdir(telemetry_dir):
        raise AutoclawSchemaError("telemetry folder not found: {}".format(telemetry_dir))
    entries = read_journal(telemetry_dir)
    if entries:
        if not full:
            entries = [e for e in entries if (_parse_ts(e.get("ts")) or 0) > int(watermark)]
            if not entries:
                return []
        sessions = _group_from_journal(entries)
    else:
        snapshot = read_snapshot(telemetry_dir)
        sessions = _sessions_from_snapshot(snapshot)
        if not full:
            sessions = [s for s in sessions if int(s.get("time_updated") or 0) > int(watermark)]
    if not full:
        return sessions
    if entries:
        return _group_from_journal(read_journal(telemetry_dir))
    return _sessions_from_snapshot(read_snapshot(telemetry_dir))


def extract(
    args: argparse.Namespace,
    dataset_path: str | None = None,
    state_path: str | None = None,
) -> dict[str, Any]:
    dataset_path = dataset_path or resources.dataset_path()
    state_path = state_path or AUTOCLAW_STATE_PATH
    telemetry_dir = os.path.expanduser(
        getattr(args, "autoclaw_dir", "") or default_dir()
    )
    if not os.path.isdir(telemetry_dir):
        return {"status": "missing", "source": SOURCE,
                "telemetry_dir": telemetry_dir, "sessions": []}
    try:
        full = bool(getattr(args, "autoclaw_full", False) or getattr(args, "full", False))
        since = getattr(args, "autoclaw_since", None) or getattr(args, "since", None)
        if since:
            try:
                watermark = int(datetime.strptime(since, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc).timestamp())
            except ValueError:
                raise ValueError("invalid AutoClaw date; expected format: YYYY-MM-DD")
            merged: dict[str, dict[str, Any]] = {}
        else:
            state = _load_json(state_path, {"last_time_updated": 0})
            watermark = int(state.get("last_time_updated", 0))
            merged = {
                s.get("source_session_id", s.get("id")): s
                for s in state.get("sessions", [])
            }
            previous = _load_json(dataset_path, {"sessions": []})
            for s in previous.get("sessions", []):
                if s.get("source", "opencode") == SOURCE:
                    merged.setdefault(s.get("source_session_id", s.get("id")), s)
        new_rows = fetch_sessions(telemetry_dir, watermark, full)
        for row in new_rows:
            merged[row["source_session_id"]] = row
        sessions = sorted(merged.values(), key=lambda s: int(s.get("time_created") or 0))
        next_wm = max((int(s.get("time_updated") or s.get("time_created") or 0)
                       for s in sessions), default=watermark)
        if full or since or new_rows:
            _save_json(state_path, {"last_time_updated": next_wm, "sessions": sessions})
        return {
            "status": "ok",
            "source": SOURCE,
            "telemetry_dir": telemetry_dir,
            "sessions": sessions,
            "watermark": next_wm,
            "new_sessions": len(new_rows),
        }
    except (AutoclawSchemaError, OSError, ValueError) as exc:
        logger.error("AutoClaw unavailable: %s", exc)
        return {"status": "error", "source": SOURCE,
                "telemetry_dir": telemetry_dir, "error": str(exc), "sessions": []}


def max_time(telemetry_dir: str) -> int:
    try:
        sessions = fetch_sessions(telemetry_dir, 0, full=True)
    except (AutoclawSchemaError, OSError):
        return 0
    return max((int(s.get("time_updated") or 0) for s in sessions), default=0)


def _load_json(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default


def _save_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only AutoClaw connector for AgentLedger")
    parser.add_argument("--dir", default=default_dir(), help="AutoClaw telemetry/ folder")
    parser.add_argument("--full", action="store_true", help="full re-extraction")
    parser.add_argument("--since", help="extract from a YYYY-MM-DD date")
    parser.add_argument("--out-dataset", default=resources.dataset_path(), help="output dataset file")
    parser.add_argument("--state", default=AUTOCLAW_STATE_PATH, help="sync state file")
    args = parser.parse_args()
    result = extract(args, args.out_dataset, args.state)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
