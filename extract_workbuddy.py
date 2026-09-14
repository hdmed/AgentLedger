from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

import resources

SOURCE = "workbuddy"
WORKBUDDY_STATE_PATH = resources.data_path("workbuddy_sync_state.json")
SCHEMA_VERSION = "wb-v1"

logger = logging.getLogger("opencost.workbuddy")


class WorkbuddySchemaError(RuntimeError):
    pass


def default_db_path() -> str:
    override = os.environ.get("WORKBUDDY_DB")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    home = os.path.expanduser("~")
    if os.name == "nt":
        profile = os.environ.get("USERPROFILE") or home
        return os.path.join(profile, ".workbuddy-ai", "workbuddy.db")
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    return os.path.join(data_home, "workbuddy-ai", "workbuddy.db")


def _uri(db_path: str) -> str:
    return "file:{}?mode=ro".format(os.path.abspath(os.path.expanduser(db_path)).replace("\\", "/"))


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
    return [row[1] for row in conn.execute("PRAGMA table_info(%s)" % table)]


def inspect_schema(db_path: str) -> dict[str, Any]:
    conn = connect(db_path)
    try:
        tables = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
        session_columns = _columns(conn, "sessions")
        if not session_columns:
            raise WorkbuddySchemaError("table 'sessions' introuvable")
        return {
            "source": SOURCE,
            "tables": tables,
            "session_columns": session_columns,
            "usage_columns": _columns(conn, "session_usage"),
            "workspace_columns": _columns(conn, "workspaces"),
        }
    finally:
        conn.close()


def _seconds(value: Any) -> int:
    """Horodatages WorkBuddy en millisecondes -> secondes UTC (passe les secondes)."""
    try:
        v = int(float(value))
    except (TypeError, ValueError):
        return 0
    return v // 1000 if v > 100_000_000_000 else v


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _split_model(raw: Any) -> tuple[str, str]:
    model = str(raw or "").strip()
    if "/" in model:
        prov, mid = model.split("/", 1)
        return prov.strip() or "?", mid.strip() or "?"
    return "?", model or "?"


def _credits(raw: Any) -> float:
    """Coût en crédits du plan WorkBuddy (PAS des USD, cf. documentation)."""
    if raw is None:
        return 0.0
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError, ValueError):
        return 0.0
    if isinstance(data, dict):
        total = 0.0
        for value in data.values():
            try:
                total += float(value)
            except (TypeError, ValueError):
                continue
        return total
    try:
        return float(data)
    except (TypeError, ValueError):
        return 0.0


def _project_name(cwd: Any, project_id: Any) -> str:
    if cwd:
        base = os.path.basename(str(cwd).rstrip("/\\")) or str(cwd)
        return base
    return str(project_id or "?")


def fetch_sessions(db_path: str, watermark: int = 0, full: bool = False) -> list[dict[str, Any]]:
    schema = inspect_schema(db_path)
    columns = set(schema["session_columns"])
    missing = sorted({"id", "created_at"} - columns)
    if missing:
        raise WorkbuddySchemaError("colonnes sessions absentes: " + ", ".join(missing))
    where, params = "", ()
    if not full:
        where = " WHERE COALESCE(s.updated_at, s.last_activity_at, s.created_at, 0) > ?"
        wm = int(watermark)
        params = (wm * 1000 if 0 < wm < 100_000_000_000 else wm,)
    conn = connect(db_path)
    try:
        has_usage = schema.get("usage_columns") is not None
        if has_usage:
            rows = conn.execute(
                "SELECT s.*, u.used AS _used, u.size AS _size,"
                " u.credit_json AS _credit_json FROM sessions s"
                " LEFT JOIN session_usage u ON u.session_id = s.id" + where
                + " ORDER BY s.created_at",
                params,
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM sessions" + where.replace("s.", "") + " ORDER BY created_at",
                params,
            ).fetchall()
        sessions: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            sid = str(item.get("id") or "")
            created = _seconds(item.get("created_at"))
            updated = _seconds(item.get("updated_at")) or _seconds(item.get("last_activity_at")) or created
            agent = str(item.get("mode") or "?")
            provider_id, model_id = _split_model(item.get("model"))
            model_label = "{}/{}".format(provider_id, model_id)
            title = str(item.get("custom_title") or item.get("title") or "")[:120]
            sessions.append({
                "source": SOURCE,
                "source_session_id": sid,
                "id": "{}:{}".format(SOURCE, sid),
                "project_id": item.get("project_id"),
                "project_name": _project_name(item.get("cwd"), item.get("project_id")),
                "directory": item.get("cwd"),
                "title": title,
                "agent": agent,
                "model": model_label,
                "cost": _credits(item.get("_credit_json")),
                "tokens_input": _integer(item.get("_used")),
                "tokens_output": 0,
                "tokens_reasoning": 0,
                "tokens_cache_read": 0,
                "tokens_cache_write": 0,
                "time_created": created,
                "time_updated": updated or created,
                "archived": item.get("deleted_at") is not None,
                "schema_version": SCHEMA_VERSION,
                "provenance": {
                    "status": str(item.get("status") or "?"),
                    "context_size": _integer(item.get("_size")),
                },
            })
        return sessions
    finally:
        conn.close()


def extract(
    args: argparse.Namespace,
    dataset_path: str | None = None,
    state_path: str | None = None,
) -> dict[str, Any]:
    dataset_path = dataset_path or resources.dataset_path()
    state_path = state_path or WORKBUDDY_STATE_PATH
    db_path = os.path.expanduser(getattr(args, "workbuddy_db", "") or default_db_path())
    if not os.path.exists(db_path):
        return {"status": "missing", "source": SOURCE, "db_path": db_path, "sessions": []}
    try:
        schema = inspect_schema(db_path)
        full = bool(getattr(args, "workbuddy_full", False) or getattr(args, "full", False))
        since = getattr(args, "workbuddy_since", None) or getattr(args, "since", None)
        if since:
            try:
                watermark = int(datetime.strptime(since, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc).timestamp())
            except ValueError:
                raise ValueError("date WorkBuddy invalide; format attendu: AAAA-MM-JJ")
            merged: dict[str, dict[str, Any]] = {}
        else:
            state = _load_json(state_path, {"last_time_updated": 0})
            watermark = int(state.get("last_time_updated", 0))
            merged = {s.get("source_session_id", s.get("id")): s for s in state.get("sessions", [])}
            previous = _load_json(dataset_path, {"sessions": []})
            for s in previous.get("sessions", []):
                if s.get("source", "opencode") == SOURCE:
                    merged.setdefault(s.get("source_session_id", s.get("id")), s)
        new_rows = fetch_sessions(db_path, watermark, full)
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
            "db_path": db_path,
            "schema": {"tables": schema.get("tables", [])},
            "sessions": sessions,
            "watermark": next_wm,
            "new_sessions": len(new_rows),
        }
    except (WorkbuddySchemaError, sqlite3.Error, OSError, ValueError) as exc:
        logger.error("WorkBuddy indisponible: %s", exc)
        return {"status": "error", "source": SOURCE,
                "db_path": db_path, "error": str(exc), "sessions": []}


def max_time(db_path: str) -> int:
    try:
        sessions = fetch_sessions(db_path, 0, full=True)
    except (WorkbuddySchemaError, sqlite3.Error, OSError):
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
    parser = argparse.ArgumentParser(description="Connecteur WorkBuddy read-only pour OpenCost")
    parser.add_argument("--db", default=default_db_path(), help="chemin vers workbuddy.db")
    parser.add_argument("--full", action="store_true", help="re-extraction complète")
    parser.add_argument("--since", help="extraction depuis une date AAAA-MM-JJ")
    parser.add_argument("--out-dataset", default=resources.dataset_path(), help="dataset de sortie")
    parser.add_argument("--state", default=WORKBUDDY_STATE_PATH, help="état de synchronisation")
    args = parser.parse_args()
    result = extract(args, args.out_dataset, args.state)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
