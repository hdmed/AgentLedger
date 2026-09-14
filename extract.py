#!/usr/bin/env python3
"""Extract AI model usage from the local OpenCode database.

100%% READ-ONLY reads of opencode.db (SQLite, python stdlib).
Produces data/dataset.json (source of the offline visual report).
Costs: OpenCode's computed value by default; overridden when the
model is present in config/pricing.json.

Usage:
  python extract.py                # incremental extraction (delta since last sync)
  python extract.py --full         # full re-extraction of all sessions
  python extract.py --db <path>    # custom OpenCode database
  python extract.py --watch        # loop: watch opencode.db and re-extract
  python extract.py --watch --build # also regenerate dist/report.html
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
import logging
from datetime import datetime, timezone
from typing import Any

import resources

BASE_DIR = resources.app_root()
DEFAULT_DB = resources.default_db_path()
DATASET_PATH = resources.dataset_path()
STATE_PATH = resources.state_path()
PRICING_PATH = resources.pricing_path()
BUDGETS_PATH = resources.budgets_path()
REPORT_PATH = resources.report_path()

logging.basicConfig(level=logging.INFO, format='[extract] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


SESSION_FIELDS = (
    "id", "project_id", "directory", "title", "agent", "model",
    "cost", "tokens_input", "tokens_output", "tokens_reasoning",
    "tokens_cache_read", "tokens_cache_write", "time_created", "time_updated",
)


def load_json(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.warning("corrupt JSON ({}), using default".format(path, e))
        try:
            os.replace(path, path + ".corrupt." + str(int(time.time())))
            # rotation: keep the last 3 .corrupt files
            d, b = os.path.dirname(path) or ".", os.path.basename(path)
            olds = sorted([os.path.join(d, f) for f in os.listdir(d) if f.startswith(b + ".corrupt.")])
            for old in olds[:-3]:
                try: os.remove(old)
                except OSError: pass
        except OSError:
            pass
        return default
    except OSError:
        return default


def save_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def load_state(path: str | None = None) -> dict[str, Any]:
    return load_json(path or STATE_PATH, {"last_time_updated": 0})


def validate_pricing_config(models_cfg: dict[str, Any]) -> dict[str, Any]:
    """Validate the pricing configuration and drop invalid entries."""
    valid_cfg = models_cfg.copy()
    for k, cfg in list(valid_cfg.items()):
        if not isinstance(cfg, dict):
            logger.warning("pricing '{}' ignored (not an object)".format(k))
            valid_cfg.pop(k, None)
            continue
        for field in ("input_per_1M", "output_per_1M", "cache_read_per_1M", "cache_write_per_1M", "reasoning_per_1M"):
            if field in cfg:
                try:
                    v = float(cfg[field])
                    if v < 0:
                        logger.warning("pricing '{}' {} negative, forcing 0".format(k, field))
                        valid_cfg[k][field] = 0.0
                except (TypeError, ValueError):
                    logger.warning("pricing '{}' {}='{}' invalid, ignored".format(k, field, cfg[field]))
                    valid_cfg[k].pop(field, None)
    return valid_cfg


def parse_model(raw: Any) -> tuple[str, str] | None:
    """Normalize a raw model field -> (provider_id, model_id).

    Accepts OpenCode JSON (providerID/id), connector dicts
    (provider/model) and "provider/model" or bare-model strings.
    """
    if not raw:
        return None
    if isinstance(raw, str):
        try:
            m = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            m = None
        if isinstance(m, dict):
            raw = m
        else:
            if "/" in raw:
                prov, mid = raw.split("/", 1)
                return (prov.strip() or "?", mid.strip() or "?")
            return ("?", raw.strip() or "?")
    if isinstance(raw, dict):
        return (raw.get("providerID") or raw.get("provider") or "?",
                raw.get("id") or raw.get("modelID") or raw.get("model") or "?")
    return None


def apply_pricing(sessions: list[dict[str, Any]], pricing: dict[str, Any] | None) -> tuple[float, list[dict[str, Any]]]:
    """Override session costs when a price is declared for the model.

    pricing = {"models": {"provider/model": {"input_per_1M":.., "output_per_1M":..,
              "cache_read_per_1M":.., "cache_write_per_1M":.., "reasoning_per_1M":..}}}
    """
    models_cfg = (pricing or {}).get("models") or {}
    models_cfg = validate_pricing_config(models_cfg)

    total_cost = 0.0
    models_seen = {}
    for s in sessions:
        mid = parse_model(s.get("model"))
        key = "{}/{}".format(*mid) if mid else "unknown"
        provider_id, model_id = (mid if mid else ("unknown", "unknown"))
        original = float(s.get("cost") or 0.0)
        s["cost_original"] = round(original, 6)
        cfg = models_cfg.get(key)
        if cfg:
            ti = float(s.get("tokens_input") or 0)
            to = float(s.get("tokens_output") or 0)
            tcr = float(s.get("tokens_cache_read") or 0)
            tcw = float(s.get("tokens_cache_write") or 0)
            tr = float(s.get("tokens_reasoning") or 0)
            cost = (
                ti / 1e6 * float(cfg.get("input_per_1M", 0))
                + to / 1e6 * float(cfg.get("output_per_1M", 0))
                + tcr / 1e6 * float(cfg.get("cache_read_per_1M", 0))
                + tcw / 1e6 * float(cfg.get("cache_write_per_1M", 0))
                + tr / 1e6 * float(cfg.get("reasoning_per_1M", 0))
            )
            s["cost"] = round(cost, 6)
            s["cost_source"] = "pricing"
        else:
            s["cost"] = round(original, 6)
            s["cost_source"] = "opencode"
        s["model_id"] = model_id
        s["provider_id"] = provider_id
        s["model_label"] = key
        total_cost += s["cost"]
        models_seen[key] = {
            "id": key,
            "provider": provider_id,
            "model": model_id,
            "override": key in models_cfg,
        }
    return total_cost, sorted(models_seen.values(), key=lambda m: m["id"])


def to_seconds(ts: Any) -> Any:
    """Normalize an OpenCode timestamp to UTC seconds.

    Recent databases store milliseconds (13 digits); older ones store
    seconds. Heuristic: > 1e11 means milliseconds.
    Returns the original value when it is not numeric.
    """
    try:
        v = int(float(ts))
    except (TypeError, ValueError):
        return ts
    if v > 100_000_000_000:
        return v // 1000
    return v


def db_threshold(watermark: int, raw_max: int = 0) -> int:
    """Threshold comparable to a database's raw values (ms or s).

    The watermark is stored in seconds; recent databases use
    milliseconds, older ones seconds. `raw_max` (the database's raw MAX)
    determines the real unit to avoid false positives/negatives.
    """
    try:
        w = int(watermark)
    except (TypeError, ValueError):
        return 0
    try:
        m = int(float(raw_max or 0))
    except (TypeError, ValueError):
        m = 0
    if m > 100_000_000_000:
        return w * 1000 if 0 < w < 100_000_000_000 else w
    return w // 1000 if w > 100_000_000_000 else w


def fetch_sessions(db_path: str, watermark: int, full: bool) -> list[dict[str, Any]]:
    """Return sessions (delta unless full). Read-only."""
    uri = "file:{}?mode=ro".format(db_path.replace("\\", "/"))
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        fields = ", ".join(SESSION_FIELDS)
        if full:
            rows = conn.execute(
                "SELECT {} FROM session".format(fields)
            ).fetchall()
        else:
            raw_max = conn.execute(
                "SELECT MAX(COALESCE(time_updated, time_created, 0)) FROM session"
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT {} FROM session WHERE COALESCE(time_updated, time_created, 0) > ?"
                .format(fields),
                (db_threshold(watermark, raw_max),),
            ).fetchall()
        projects = {
            r["id"]: dict(r)
            for r in conn.execute("SELECT id, name, worktree FROM project").fetchall()
        }
        sessions = []
        for r in rows:
            d = dict(r)
            d["source"] = "opencode"
            d["source_session_id"] = d.get("id")
            d["time_created"] = to_seconds(d.get("time_created"))
            d["time_updated"] = to_seconds(d.get("time_updated"))
            proj = projects.get(d.get("project_id"))
            if proj:
                d["project_name"] = proj.get("name") or resources.basename_crossplatform(proj.get("worktree")) or d.get("project_id")
            else:
                d["project_name"] = d.get("project_id")
            sessions.append(d)
        return sessions
    finally:
        conn.close()


def extract(
    args: argparse.Namespace,
    dataset_path: str | None = None,
    state_path: str | None = None,
    pricing_path: str | None = None,
    budgets_path: str | None = None,
) -> bool:
    dataset_path = dataset_path or DATASET_PATH
    state_path = state_path or STATE_PATH
    pricing_path = pricing_path or PRICING_PATH
    budgets_path = budgets_path or BUDGETS_PATH
    db_path = os.path.expanduser(args.db)
    if not os.path.exists(db_path):
        logger.error("OpenCode database not found: {}".format(db_path))
        print("Pass --db <path> (default ~/.local/share/opencode/opencode.db)")
        sys.exit(1)

    pricing = load_json(pricing_path, {"models": {}})
    full = getattr(args, "full", False)
    since = getattr(args, "since", None)

    if full:
        watermark = 0
    elif since:
        try:
            dt = datetime.strptime(since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            watermark = int(dt.timestamp())
        except ValueError:
            logger.error("Invalid date for --since: {}. Expected format: YYYY-MM-DD".format(since))
            sys.exit(1)
    else:
        state = load_state(state_path)
        watermark = int(state.get("last_time_updated", 0))

    # Foreign-source sessions (kilo/autoclaw/workbuddy, merged by the
    # launcher) are owned by their connectors: the OpenCode extractor
    # carries them over untouched instead of dropping them.
    prev = load_json(dataset_path, {"sessions": []})
    foreign_by_key = {}
    for s in prev.get("sessions", []):
        if s.get("source", "opencode") != "opencode":
            foreign_by_key[(s.get("source"), s.get("source_session_id", s.get("id")))] = s
    merged = {s["id"]: s for s in prev.get("sessions", [])
              if s.get("source", "opencode") == "opencode"}
    if full or since:
        merged = {}

    logger.info("source: {}".format(db_path))
    started = time.time()
    new_rows = fetch_sessions(db_path, watermark, full)
    if not full and not since:
        # cleanup: drop deleted/archived sessions (lightweight SELECT id)
        uri = "file:{}?mode=ro".format(db_path.replace("\\", "/"))
        conn = sqlite3.connect(uri, uri=True, timeout=5)
        try:
            alive = {r[0] for r in conn.execute("SELECT id FROM session").fetchall()}
        finally:
            conn.close()
        merged = {k: v for k, v in merged.items() if k in alive}

    for r in new_rows:
        merged[r["id"]] = r

    sessions = list(merged.values()) + list(foreign_by_key.values())
    for s in sessions:
        s.setdefault("source", "opencode")
        s.setdefault("source_session_id", s.get("id"))
        # heal: legacy datasets stored in milliseconds
        s["time_created"] = to_seconds(s.get("time_created"))
        s["time_updated"] = to_seconds(s.get("time_updated"))
    logger.info(" {} new/updated session(s) ({} total)".format(
        len(new_rows), len(sessions)))

    total_cost, models = apply_pricing(sessions, pricing)

    # Budget Alerts
    budgets = load_json(budgets_path, {})
    if budgets:
        month_ago = int(time.time()) - 30*24*3600
        month_cost = sum(float(s.get("cost", 0)) for s in sessions if int(s.get("time_created", 0)) >= month_ago)

        g_limit = budgets.get("global", {}).get("monthly")
        if g_limit and month_cost > g_limit:
            logger.warning("GLOBAL budget exceeded: {:.2f} / {:.2f} $ (30d)".format(month_cost, g_limit))

        by_proj_limits = budgets.get("by_project", {})
        for proj, cfg in by_proj_limits.items():
            p_limit = cfg.get("monthly")
            if p_limit:
                p_cost = sum(float(s.get("cost", 0)) for s in sessions if s.get("project_name") == proj and int(s.get("time_created", 0)) >= month_ago)
                if p_cost > p_limit:
                    logger.warning("PROJECT budget '{}' exceeded: {:.2f} / {:.2f} $ (30d)".format(proj, p_cost, p_limit))

        by_mod_limits = budgets.get("by_model", {})
        for mod, cfg in by_mod_limits.items():
            m_limit = cfg.get("monthly")
            if m_limit:
                m_cost = sum(float(s.get("cost", 0)) for s in sessions if s.get("model_label") == mod and int(s.get("time_created", 0)) >= month_ago)
                if m_cost > m_limit:
                    logger.warning("MODEL budget '{}' exceeded: {:.2f} / {:.2f} $ (30d)".format(mod, m_cost, m_limit))

    # next watermark = max COALESCE(time_updated, time_created) of the rows read
    next_wm = watermark
    for r in new_rows:
        ts = r.get("time_updated") or r.get("time_created")
        if ts:
            next_wm = max(next_wm, int(ts))
    if full or since:
        next_wm = max((int(r.get("time_updated") or r.get("time_created") or 0) for r in sessions), default=0)

    sessions.sort(key=lambda s: int(s.get("time_created") or 0))
    dataset = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "db_path": db_path,
        "pricing_config": pricing,
        "budgets": budgets,
        "models": models,
        "totals": {
            "cost": round(total_cost, 6),
            "sessions": len(sessions),
            "tokens_input": sum(int(s.get("tokens_input") or 0) for s in sessions),
            "tokens_output": sum(int(s.get("tokens_output") or 0) for s in sessions),
            "tokens_reasoning": sum(int(s.get("tokens_reasoning") or 0) for s in sessions),
            "tokens_cache_read": sum(int(s.get("tokens_cache_read") or 0) for s in sessions),
            "tokens_cache_write": sum(int(s.get("tokens_cache_write") or 0) for s in sessions),
        },
        "sessions": sessions,
    }
    save_json(dataset_path, dataset)
    save_json(state_path, {"last_time_updated": next_wm})
    logger.info("OK -> {}".format(dataset_path))
    logger.info("{} sessions, total cost {:.4f}, {}s".format(
        len(sessions), total_cost, round(time.time() - started, 2)))
    return True


def build_report(dataset_path: str | None = None, out_path: str | None = None) -> int:
    from build_report import generate_report
    return 0 if generate_report(dataset_path or DATASET_PATH, out_path or REPORT_PATH) else 1


def _db_max_time(db_path: str) -> int:
    try:
        uri = "file:{}?mode=ro".format(db_path.replace("\\", "/"))
        conn = sqlite3.connect(uri, uri=True, timeout=5)
        try:
            row = conn.execute("SELECT MAX(COALESCE(time_updated, time_created, 0)) FROM session").fetchone()
            return int(row[0] or 0) if row and row[0] is not None else 0
        finally:
            conn.close()
    except Exception:
        try:
            return int(os.path.getmtime(db_path))
        except OSError:
            return 0

def watch(
    args: argparse.Namespace,
    dataset_path: str | None = None,
    state_path: str | None = None,
    pricing_path: str | None = None,
    budgets_path: str | None = None,
    report_path: str | None = None,
    run_initial: bool = True,
) -> None:
    db_path = os.path.expanduser(args.db)
    dataset_path = dataset_path or DATASET_PATH
    state_path = state_path or STATE_PATH
    pricing_path = pricing_path or PRICING_PATH
    budgets_path = budgets_path or BUDGETS_PATH
    report_path = report_path or REPORT_PATH
    # try watchdog (optional, otherwise poll)
    try:
        from watchdog.observers import Observer  # type: ignore
        from watchdog.events import FileSystemEventHandler  # type: ignore
        has_watchdog = True
    except ImportError:
        has_watchdog = False
    if has_watchdog:
        logger.info("watchdog active on {}".format(os.path.dirname(db_path)))
        last_max = _db_max_time(db_path)
        if run_initial:
            extract(args, dataset_path, state_path, pricing_path, budgets_path)
            if args.build:
                build_report(dataset_path, report_path)
        class H(FileSystemEventHandler):
            def on_modified(self, event):
                if os.path.abspath(event.src_path) == os.path.abspath(db_path):
                    logger.info("change detected -> re-extracting")
                    extract(args, dataset_path, state_path, pricing_path, budgets_path)
                    if args.build:
                        build_report(dataset_path, report_path)
            on_created = on_modified
        obs = Observer(); obs.schedule(H(), os.path.dirname(os.path.abspath(db_path)) or ".", recursive=False); obs.start()
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt:
            obs.stop(); obs.join(); return
    logger.info("watching {} every 15s (Ctrl+C to stop)".format(db_path))
    last_max = _db_max_time(db_path)
    last_mtime = 0
    try:
        last_mtime = os.path.getmtime(db_path)
    except OSError:
        pass
    if run_initial:
        extract(args, dataset_path, state_path, pricing_path, budgets_path)
        if args.build:
            build_report(dataset_path, report_path)
    while True:
        time.sleep(15)
        cur_max = _db_max_time(db_path)
        try:
            mtime = os.path.getmtime(db_path)
        except OSError:
            mtime = last_mtime
        if cur_max != last_max or mtime != last_mtime:
            logger.info("change detected -> re-extracting")
            last_max, last_mtime = cur_max, mtime
            extract(args, dataset_path, state_path, pricing_path, budgets_path)
            if args.build:
                build_report(dataset_path, report_path)


def main():
    ap = argparse.ArgumentParser(description="AI usage extraction from opencode.db")
    ap.add_argument("--db", default=os.environ.get("OPENCODE_DB") or DEFAULT_DB,
                    help="path to opencode.db")
    ap.add_argument("--full", action="store_true",
                    help="full re-extraction (ignore the incremental cache)")
    ap.add_argument("--since", type=str,
                    help="extract from an ISO date (YYYY-MM-DD), ignore the watermark")
    ap.add_argument("--sync-now", action="store_true",
                    help="force immediate extraction")
    ap.add_argument("--watch", action="store_true",
                    help="watch the database and re-extract on change")
    ap.add_argument("--build", action="store_true",
                    help="with --watch: also regenerate dist/report.html")
    ap.add_argument("--out-dataset", default=DATASET_PATH,
                    help="path to the output dataset.json file")
    args = ap.parse_args()

    if args.watch:
        watch(args, dataset_path=args.out_dataset, report_path=REPORT_PATH)
    else:
        extract(args, dataset_path=args.out_dataset)
        if args.build:
            build_report(args.out_dataset, REPORT_PATH)


if __name__ == "__main__":
    main()