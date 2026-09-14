from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import resources

SOURCE = "kilo"
KILO_STATE_PATH = resources.data_path("kilo_sync_state.json")
DEFAULT_KILO_DB = None

logger = logging.getLogger("agentledger.kilo")


class KiloSchemaError(RuntimeError):
    pass


def default_db_path() -> str:
    override = os.environ.get("KILO_DB")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    data_dir = os.environ.get("KILO_DATA_DIR")
    if data_dir:
        candidates = [p.strip() for p in data_dir.split(",") if p.strip()]
        for candidate in candidates:
            path = os.path.join(os.path.abspath(os.path.expanduser(candidate)), "kilo.db")
            if os.path.exists(path):
                return path
        return os.path.join(os.path.abspath(os.path.expanduser(candidates[0])), "kilo.db") if candidates else ""
    if os.name == "nt":
        profile = os.environ.get("USERPROFILE") or os.path.expanduser("~")
        local = os.environ.get("LOCALAPPDATA") or os.path.join(profile, "AppData", "Local")
        candidates = [
            os.path.join(profile, ".local", "share", "kilo", "kilo.db"),
            os.path.join(local, "kilo", "kilo.db"),
        ]
    else:
        home = os.path.expanduser("~")
        data_home = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
        candidates = [os.path.join(data_home, "kilo", "kilo.db")]
        if os.name == "darwin":
            candidates.insert(0, os.path.join(home, "Library", "Application Support", "kilo", "kilo.db"))
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return candidates[0]


def _uri(db_path: str) -> str:
    return Path(os.path.abspath(os.path.expanduser(db_path))).as_uri() + "?mode=ro"


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(_uri(db_path), uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> list[str] | None:
    found = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    if not found:
        return None
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def inspect_schema(db_path: str) -> dict[str, Any]:
    conn = connect(db_path)
    try:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
        session_columns = _columns(conn, "session")
        if not session_columns:
            raise KiloSchemaError("table 'session' not found")
        message_table = "session_message" if "session_message" in tables else "message" if "message" in tables else None
        message_columns = _columns(conn, message_table) if message_table else None
        part_columns = _columns(conn, "part")
        project_columns = _columns(conn, "project")
        user_version = 0
        try:
            row = conn.execute("PRAGMA user_version").fetchone()
            user_version = int(row[0]) if row else 0
        except sqlite3.Error:
            pass
        journal_mode = ""
        try:
            row = conn.execute("PRAGMA journal_mode").fetchone()
            journal_mode = str(row[0]) if row else ""
        except sqlite3.Error:
            pass
        return {
            "source": SOURCE,
            "tables": tables,
            "session_columns": session_columns,
            "message_table": message_table,
            "message_columns": message_columns,
            "part_columns": part_columns,
            "project_columns": project_columns,
            "user_version": user_version,
            "journal_mode": journal_mode,
        }
    finally:
        conn.close()


def _json(value: Any, default: Any = None) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError, ValueError):
        return default


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _seconds(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value) / 1000)
    except (TypeError, ValueError):
        return None


def _parse_model(raw: Any) -> tuple[str, str]:
    value = _json(raw)
    if isinstance(value, dict):
        provider = value.get("providerID") or value.get("provider") or "?"
        model = value.get("id") or value.get("modelID") or value.get("model") or "?"
        return str(provider), str(model)
    if isinstance(raw, str) and "/" in raw:
        provider, model = raw.split("/", 1)
        return provider or "?", model or "?"
    return "?", "?"


def _tokens(value: Any) -> dict[str, int]:
    value = value if isinstance(value, dict) else {}
    cache = value.get("cache") if isinstance(value.get("cache"), dict) else {}
    return {
        "tokens_input": _integer(value.get("input")),
        "tokens_output": _integer(value.get("output")),
        "tokens_reasoning": _integer(value.get("reasoning")),
        "tokens_cache_read": _integer(cache.get("read")),
        "tokens_cache_write": _integer(cache.get("write")),
    }


def _fallback_metrics(conn: sqlite3.Connection, session_id: str, schema: dict[str, Any]) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "cost": 0.0,
        "tokens_input": 0,
        "tokens_output": 0,
        "tokens_reasoning": 0,
        "tokens_cache_read": 0,
        "tokens_cache_write": 0,
    }
    model_raw = None
    message_table = schema.get("message_table")
    if message_table and schema.get("message_columns"):
        try:
            rows = conn.execute(
                f"SELECT data FROM {message_table} WHERE session_id = ? ORDER BY time_created, id",
                (session_id,),
            ).fetchall()
            for row in rows:
                data = _json(row[0], {})
                if not isinstance(data, dict):
                    continue
                candidate = data.get("model")
                if candidate and not model_raw:
                    model_raw = candidate
                if data.get("role") == "assistant" or data.get("type") == "assistant":
                    tokens = _tokens(data.get("tokens"))
                    for key, value in tokens.items():
                        metrics[key] = metrics.get(key, 0) + value
                    if data.get("cost") is not None:
                        metrics["cost"] = _number(data.get("cost"))
        except sqlite3.Error:
            pass
    if schema.get("part_columns"):
        try:
            rows = conn.execute(
                "SELECT data FROM part WHERE session_id = ? ORDER BY time_created, id",
                (session_id,),
            ).fetchall()
            step_metrics: dict[str, Any] | None = None
            for row in rows:
                data = _json(row[0], {})
                if not isinstance(data, dict):
                    continue
                if data.get("type") != "step-finish":
                    continue
                tokens = _tokens(data.get("tokens"))
                if step_metrics is None:
                    step_metrics = {"cost": 0.0, **tokens}
                else:
                    step_metrics["cost"] = _number(step_metrics.get("cost")) + _number(data.get("cost"))
                    for key, value in tokens.items():
                        step_metrics[key] = _integer(step_metrics.get(key)) + value
            if step_metrics is not None:
                metrics = step_metrics
        except sqlite3.Error:
            pass
    if model_raw is not None:
        metrics["model"] = model_raw
    return metrics


def _project_name(conn: sqlite3.Connection, project_id: Any, columns: list[str] | None) -> str:
    if not project_id or not columns or "id" not in columns:
        return str(project_id or "?")
    try:
        row = conn.execute("SELECT name, worktree FROM project WHERE id = ?", (str(project_id),)).fetchone()
    except sqlite3.Error:
        row = None
    if not row:
        return str(project_id)
    name, worktree = row[0], row[1]
    return str(name or (resources.basename_crossplatform(worktree) if worktree else "") or project_id)


def fetch_sessions(db_path: str, watermark: int = 0, full: bool = False) -> list[dict[str, Any]]:
    schema = inspect_schema(db_path)
    columns = set(schema["session_columns"])
    required = {"id", "time_created"}
    missing = sorted(required - columns)
    if missing:
        raise KiloSchemaError("missing session columns: " + ", ".join(missing))
    selected = [
        "id", "project_id", "directory", "title", "agent", "model", "cost",
        "tokens_input", "tokens_output", "tokens_reasoning", "tokens_cache_read",
        "tokens_cache_write", "time_created", "time_updated", "version",
        "parent_id", "workspace_id", "slug", "time_archived",
    ]
    selected = [column for column in selected if column in columns]
    where = ""
    params: tuple[Any, ...] = ()
    if not full and "time_updated" in columns:
        where = " WHERE COALESCE(time_updated, time_created, 0) > ?"
        params = (int(watermark) * 1000,)
    elif not full:
        where = " WHERE COALESCE(time_updated, time_created, 0) > ?"
        params = (int(watermark) * 1000,)
    conn = connect(db_path)
    try:
        rows = conn.execute("SELECT {} FROM session{}".format(", ".join(selected), where), params).fetchall()
        sessions: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            session_id = str(item.get("id") or "")
            fallback = _fallback_metrics(conn, session_id, schema) if any(
                key not in columns or item.get(key) is None
                for key in ("cost", "tokens_input", "tokens_output", "tokens_reasoning", "tokens_cache_read", "tokens_cache_write", "model")
            ) else {}
            created = _seconds(item.get("time_created"))
            updated = _seconds(item.get("time_updated"))
            if created is None and fallback.get("time_created") is not None:
                created = _seconds(fallback["time_created"])
            if updated is None and fallback.get("time_updated") is not None:
                updated = _seconds(fallback["time_updated"])
            model_raw = item.get("model") if item.get("model") is not None else fallback.get("model")
            provider, model = _parse_model(model_raw)
            cost = _number(item.get("cost")) if "cost" in columns and item.get("cost") is not None else _number(fallback.get("cost"))
            tokens_input = _integer(item.get("tokens_input")) if "tokens_input" in columns and item.get("tokens_input") is not None else _integer(fallback.get("tokens_input"))
            tokens_output = _integer(item.get("tokens_output")) if "tokens_output" in columns and item.get("tokens_output") is not None else _integer(fallback.get("tokens_output"))
            tokens_reasoning = _integer(item.get("tokens_reasoning")) if "tokens_reasoning" in columns and item.get("tokens_reasoning") is not None else _integer(fallback.get("tokens_reasoning"))
            tokens_cache_read = _integer(item.get("tokens_cache_read")) if "tokens_cache_read" in columns and item.get("tokens_cache_read") is not None else _integer(fallback.get("tokens_cache_read"))
            tokens_cache_write = _integer(item.get("tokens_cache_write")) if "tokens_cache_write" in columns and item.get("tokens_cache_write") is not None else _integer(fallback.get("tokens_cache_write"))
            sessions.append({
                "source": SOURCE,
                "source_session_id": session_id,
                "id": f"{SOURCE}:{session_id}",
                "project_id": item.get("project_id"),
                "project_name": _project_name(conn, item.get("project_id"), schema.get("project_columns")),
                "directory": item.get("directory"),
                "title": item.get("title"),
                "agent": item.get("agent"),
                "model": model_raw,
                "cost": _number(item.get("cost") if "cost" in columns and item.get("cost") is not None else fallback.get("cost")),
                "tokens_input": _integer(item.get("tokens_input")) if "tokens_input" in columns and item.get("tokens_input") is not None else _integer(fallback.get("tokens_input")),
                "tokens_output": _integer(item.get("tokens_output")) if "tokens_output" in columns and item.get("tokens_output") is not None else _integer(fallback.get("tokens_output")),
                "tokens_reasoning": _integer(item.get("tokens_reasoning")) if "tokens_reasoning" in columns and item.get("tokens_reasoning") is not None else _integer(fallback.get("tokens_reasoning")),
                "tokens_cache_read": _integer(item.get("tokens_cache_read")) if "tokens_cache_read" in columns and item.get("tokens_cache_read") is not None else _integer(fallback.get("tokens_cache_read")),
                "tokens_cache_write": _integer(item.get("tokens_cache_write")) if "tokens_cache_write" in columns and item.get("tokens_cache_write") is not None else _integer(fallback.get("tokens_cache_write")),
                "time_created": created or 0,
                "time_updated": updated or created or 0,
                "version": item.get("version"),
                "parent_id": item.get("parent_id"),
                "workspace_id": item.get("workspace_id"),
                "slug": item.get("slug"),
                "archived": bool(item.get("time_archived")),
                "schema_version": schema.get("user_version") or "unknown",
            })
        return sessions
    finally:
        conn.close()


def extract(
    args: argparse.Namespace,
    dataset_path: str | None = None,
    state_path: str | None = None,
    pricing_path: str | None = None,
) -> dict[str, Any]:
    del pricing_path
    dataset_path = dataset_path or resources.dataset_path()
    state_path = state_path or KILO_STATE_PATH
    db_path = os.path.expanduser(getattr(args, "kilo_db", "") or default_db_path())
    if not os.path.exists(db_path):
        return {"status": "missing", "source": SOURCE, "db_path": db_path, "sessions": [], "schema": {}}
    try:
        schema = inspect_schema(db_path)
        full = bool(getattr(args, "kilo_full", False) or getattr(args, "full", False))
        since = getattr(args, "kilo_since", None) or getattr(args, "since", None)
        if since:
            try:
                watermark = int(datetime.strptime(since, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
            except ValueError:
                raise ValueError("invalid Kilo date; expected format: YYYY-MM-DD")
            merged = {}
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
        new_rows = fetch_sessions(db_path, watermark, full)
        if not full and not since:
            conn = connect(db_path)
            try:
                alive = {str(row[0]) for row in conn.execute("SELECT id FROM session")}
            finally:
                conn.close()
            merged = {key: value for key, value in merged.items() if key in alive}
        for row in new_rows:
            merged[row["source_session_id"]] = row
        sessions = sorted(merged.values(), key=lambda s: int(s.get("time_created") or 0))
        next_wm = max((int(s.get("time_updated") or s.get("time_created") or 0) for s in sessions), default=watermark)
        if full or since or new_rows:
            _save_json(state_path, {"last_time_updated": next_wm, "sessions": sessions})
        return {
            "status": "ok",
            "source": SOURCE,
            "db_path": db_path,
            "schema": schema,
            "sessions": sessions,
            "watermark": next_wm,
            "new_sessions": len(new_rows),
        }
    except (KiloSchemaError, sqlite3.Error, OSError, ValueError) as exc:
        logger.error("Kilo unavailable: %s", exc)
        return {"status": "error", "source": SOURCE, "db_path": db_path, "error": str(exc), "sessions": [], "schema": {}}


def max_time(db_path: str) -> int:
    try:
        schema = inspect_schema(db_path)
        columns = set(schema.get("session_columns", []))
        if "time_updated" not in columns and "time_created" not in columns:
            return 0
        field = "time_updated" if "time_updated" in columns else "time_created"
        conn = connect(db_path)
        try:
            row = conn.execute(f"SELECT MAX({field}) FROM session").fetchone()
            value = _seconds(row[0] if row else 0)
            return value or 0
        finally:
            conn.close()
    except (KiloSchemaError, sqlite3.Error, OSError):
        try:
            return int(os.path.getmtime(db_path))
        except OSError:
            return 0


def _load_json(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default


def _save_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Kilo/KiloCode extraction for AgentLedger")
    parser.add_argument("--db", default=default_db_path(), help="path to kilo.db")
    parser.add_argument("--full", action="store_true", help="full re-extraction")
    parser.add_argument("--since", help="extract from a YYYY-MM-DD date")
    parser.add_argument("--out-dataset", default=resources.dataset_path(), help="output dataset file")
    parser.add_argument("--state", default=KILO_STATE_PATH, help="sync state file")
    args = parser.parse_args()
    result = extract(args, args.out_dataset, args.state)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
