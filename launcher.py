from __future__ import annotations

import argparse
import logging
import os
import sys
import webbrowser
from pathlib import Path

import build_report
import extract
import extract_autoclaw
import extract_kilo
import extract_workbuddy
import resources

VERSION = "1.0.0"
logger = logging.getLogger("agentledger")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Standalone AgentLedger dashboard")
    parser.add_argument("--db", help="path to opencode.db")
    parser.add_argument("--full", action="store_true", help="rebuild the full dataset")
    parser.add_argument("--since", help="extract from a YYYY-MM-DD date")
    parser.add_argument("--watch", action="store_true", help="watch the database after the first report")
    parser.add_argument("--reset", action="store_true", help="delete dataset, state and report before extracting")
    parser.add_argument("--open-only", action="store_true", help="open the existing report without extracting")
    parser.add_argument("--no-open", action="store_true", help="do not open the browser")
    parser.add_argument("--no-strict", action="store_true", help="tolerate a missing Chart.js asset")
    parser.add_argument("--diagnose", action="store_true", help="print paths and resource status")
    parser.add_argument("--version", action="store_true", help="print the version")
    parser.add_argument("--kilo-db", default=None, help="path to kilo.db (default: auto-detect)")
    parser.add_argument("--kilo-full", action="store_true", help="full Kilo re-extraction")
    parser.add_argument("--kilo-since", default=None, help="extract Kilo from a YYYY-MM-DD date")
    parser.add_argument("--no-kilo", action="store_true", help="disable the Kilo connector")
    parser.add_argument("--autoclaw-dir", default=None, help="AutoClaw telemetry/ folder (default: auto-detect, see Docs/AutCLW.md)")
    parser.add_argument("--autoclaw-full", action="store_true", help="full AutoClaw re-extraction")
    parser.add_argument("--autoclaw-since", default=None, help="extract AutoClaw from a YYYY-MM-DD date")
    parser.add_argument("--no-autoclaw", action="store_true", help="disable the AutoClaw connector")
    parser.add_argument("--workbuddy-db", default=None, help="path to workbuddy.db (default: auto-detect)")
    parser.add_argument("--workbuddy-full", action="store_true", help="full WorkBuddy re-extraction")
    parser.add_argument("--workbuddy-since", default=None, help="extract WorkBuddy from a YYYY-MM-DD date")
    parser.add_argument("--no-workbuddy", action="store_true", help="disable the WorkBuddy connector")
    return parser.parse_args(argv)


def remove_if_exists(path):
    try:
        if os.path.isfile(path) or os.path.islink(path):
            os.remove(path)
        elif os.path.isdir(path):
            os.rmdir(path)
    except OSError:
        pass


def reset_user_data():
    for path in (resources.dataset_path(), resources.state_path(), resources.report_path()):
        remove_if_exists(path)
    remove_if_exists(extract_kilo.KILO_STATE_PATH)
    remove_if_exists(extract_autoclaw.AUTOCLAW_STATE_PATH)
    remove_if_exists(extract_workbuddy.WORKBUDDY_STATE_PATH)


def merge_kilo_result(dataset_path, pricing_path, kilo_result):
    """Backward compatibility: merge one source through the generic path."""
    return merge_source_result(dataset_path, pricing_path, kilo_result)


def merge_source_result(dataset_path, pricing_path, source_result):
    """Additively merge one source's sessions into the shared dataset.

    Dedup key is (source, source_session_id). A missing or failing
    source never deletes other sources' sessions.
    Returns (source_count, total).
    """
    import json

    try:
        with open(dataset_path, "r", encoding="utf-8") as f:
            dataset = json.load(f)
    except (OSError, ValueError):
        dataset = {"sessions": [], "models": [], "totals": {}, "pricing_config": {},
                   "budgets": {}, "generated_at": "", "db_path": ""}
    sessions = dataset.get("sessions", [])
    for s in sessions:
        s.setdefault("source", "opencode")
        s.setdefault("source_session_id", s.get("id"))
        # heal labels clobbered to "unknown" by older merges
        if s.get("source") != "opencode" and s.get("model_label") in (None, "unknown", "?/?"):
            mid = extract.parse_model(s.get("model"))
            if mid:
                s["provider_id"], s["model_id"] = mid
                s["model_label"] = "{}/{}".format(*mid)
    incoming = list(source_result.get("sessions", []))
    incoming_source = source_result.get("source", "?")
    if incoming:
        pricing = {}
        try:
            with open(pricing_path, "r", encoding="utf-8") as f:
                pricing = json.load(f)
        except (OSError, ValueError):
            pricing = {"models": {}}
        extract.apply_pricing(incoming, pricing)
        priced_models = (pricing.get("models") or {})
        for s in incoming:
            if s.get("model_label") not in priced_models and s.get("cost_source") == "opencode":
                s["cost_source"] = s.get("source", incoming_source)
    by_key = {}
    for s in sessions:
        if s.get("source", "opencode") != incoming_source:
            by_key[(s.get("source", "opencode"), s.get("source_session_id", s.get("id")))] = s
    for s in incoming:
        by_key[(s.get("source", incoming_source), s.get("source_session_id", s.get("id")))] = s
    combined = sorted(by_key.values(), key=lambda s: int(s.get("time_created") or 0))
    model_ids = {}
    for s in combined:
        key = s.get("model_label") or "unknown"
        model_ids[key] = {
            "id": key,
            "provider": s.get("provider_id", "?"),
            "model": s.get("model_id", "?"),
            "override": False,
        }
    for m in dataset.get("models", []):
        if m.get("id") in model_ids:
            model_ids[m["id"]] = m
    dataset["sessions"] = combined
    dataset["models"] = sorted(model_ids.values(), key=lambda m: m["id"])
    dataset["totals"] = {
        "cost": round(sum(float(s.get("cost") or 0) for s in combined), 6),
        "sessions": len(combined),
        "tokens_input": sum(int(s.get("tokens_input") or 0) for s in combined),
        "tokens_output": sum(int(s.get("tokens_output") or 0) for s in combined),
        "tokens_reasoning": sum(int(s.get("tokens_reasoning") or 0) for s in combined),
        "tokens_cache_read": sum(int(s.get("tokens_cache_read") or 0) for s in combined),
        "tokens_cache_write": sum(int(s.get("tokens_cache_write") or 0) for s in combined),
    }
    from datetime import datetime, timezone
    dataset["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    os.makedirs(os.path.dirname(os.path.abspath(dataset_path)) or ".", exist_ok=True)
    import json as _json
    with open(dataset_path, "w", encoding="utf-8") as f:
        _json.dump(dataset, f, ensure_ascii=False, indent=1)
    return len(incoming), len(combined)


def run_kilo_sync(args, dataset_path, pricing_path):
    """Run the Kilo connector and merge. Never blocks other sources."""
    if getattr(args, "no_kilo", False):
        return None
    kilo_args = argparse.Namespace(
        kilo_db=getattr(args, "kilo_db", None) or extract_kilo.default_db_path(),
        kilo_full=bool(getattr(args, "kilo_full", False) or getattr(args, "full", False)),
        kilo_since=getattr(args, "kilo_since", None) or getattr(args, "since", None),
        full=bool(getattr(args, "full", False)),
        since=getattr(args, "since", None),
    )
    result = extract_kilo.extract(kilo_args, dataset_path, extract_kilo.KILO_STATE_PATH)
    status = result.get("status")
    if status == "missing":
        logger.info("Kilo missing (%s): keeping the OpenCode dataset", result.get("db_path"))
        return result
    if status == "error":
        logger.warning("Kilo unavailable (%s): keeping the OpenCode dataset",
                       result.get("error") or result.get("db_path"))
        return result
    n_kilo, n_total = merge_kilo_result(dataset_path, pricing_path, result)
    logger.info("Kilo merged: %d kilo session(s), %d total", n_kilo, n_total)
    return result


def run_autoclaw_sync(args, dataset_path, pricing_path):
    """Run the AutoClaw connector and merge. Never blocks other sources."""
    if getattr(args, "no_autoclaw", False):
        return None
    autoclaw_args = argparse.Namespace(
        autoclaw_dir=getattr(args, "autoclaw_dir", None) or extract_autoclaw.default_dir(),
        autoclaw_full=bool(getattr(args, "autoclaw_full", False) or getattr(args, "full", False)),
        autoclaw_since=getattr(args, "autoclaw_since", None) or getattr(args, "since", None),
        full=bool(getattr(args, "full", False)),
        since=getattr(args, "since", None),
    )
    result = extract_autoclaw.extract(autoclaw_args, dataset_path, extract_autoclaw.AUTOCLAW_STATE_PATH)
    status = result.get("status")
    if status == "missing":
        logger.info("AutoClaw missing (%s): keeping other sources", result.get("telemetry_dir"))
        return result
    if status == "error":
        logger.warning("AutoClaw unavailable (%s): keeping other sources",
                       result.get("error") or result.get("telemetry_dir"))
        return result
    n_auto, n_total = merge_source_result(dataset_path, pricing_path, result)
    logger.info("AutoClaw merged: %d autoclaw session(s), %d total", n_auto, n_total)
    return result


def run_workbuddy_sync(args, dataset_path, pricing_path):
    """Run the WorkBuddy connector and merge. Never blocks other sources."""
    if getattr(args, "no_workbuddy", False):
        return None
    wb_args = argparse.Namespace(
        workbuddy_db=getattr(args, "workbuddy_db", None) or extract_workbuddy.default_db_path(),
        workbuddy_full=bool(getattr(args, "workbuddy_full", False) or getattr(args, "full", False)),
        workbuddy_since=getattr(args, "workbuddy_since", None) or getattr(args, "since", None),
        full=bool(getattr(args, "full", False)),
        since=getattr(args, "since", None),
    )
    result = extract_workbuddy.extract(wb_args, dataset_path, extract_workbuddy.WORKBUDDY_STATE_PATH)
    status = result.get("status")
    if status == "missing":
        logger.info("WorkBuddy missing (%s): keeping other sources", result.get("db_path"))
        return result
    if status == "error":
        logger.warning("WorkBuddy unavailable (%s): keeping other sources",
                       result.get("error") or result.get("db_path"))
        return result
    n_wb, n_total = merge_source_result(dataset_path, pricing_path, result)
    logger.info("WorkBuddy merged: %d workbuddy session(s), %d total", n_wb, n_total)
    return result


def open_report(path):
    uri = Path(os.path.abspath(path)).as_uri()
    if not webbrowser.open(uri):
        logger.warning("could not open the browser; report available at: %s", path)


def diagnose():
    paths = {
        "app": resources.app_root(),
        "user": resources.user_root(),
        "database": resources.default_db_path(),
        "dataset": resources.dataset_path(),
        "state": resources.state_path(),
        "kilo_database": extract_kilo.default_db_path(),
        "kilo_state": extract_kilo.KILO_STATE_PATH,
        "autoclaw_dir": extract_autoclaw.default_dir(),
        "autoclaw_state": extract_autoclaw.AUTOCLAW_STATE_PATH,
        "workbuddy_database": extract_workbuddy.default_db_path(),
        "workbuddy_state": extract_workbuddy.WORKBUDDY_STATE_PATH,
        "report": resources.report_path(),
        "pricing": resources.pricing_path(),
        "budgets": resources.budgets_path(),
        "template": resources.resource_path("templates", "report_template.html"),
        "chart": resources.resource_path("assets", "chart.umd.min.js"),
    }
    for name, path in paths.items():
        print("{}: {}".format(name, path))
    print("frozen: {}".format(resources.is_frozen()))
    print("database_exists: {}".format(os.path.exists(paths["database"])))
    print("kilo_database_exists: {}".format(os.path.exists(paths["kilo_database"])))
    print("autoclaw_dir_exists: {}".format(os.path.isdir(paths["autoclaw_dir"])))
    print("workbuddy_database_exists: {}".format(os.path.exists(paths["workbuddy_database"])))
    for cand in extract_autoclaw.candidate_dirs():
        print("autoclaw_candidat: {} ({})".format(
            cand, "OK" if os.path.isdir(cand) else "-"))
    print("template_exists: {}".format(os.path.exists(paths["template"])))
    print("chart_exists: {}".format(os.path.exists(paths["chart"])))


def run(argv=None):
    args = parse_args(argv)
    if args.version:
        print("AgentLedger {}".format(VERSION))
        return 0

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if args.diagnose:
        diagnose()
        return 0

    if args.reset:
        reset_user_data()

    if args.open_only:
        report_path = resources.report_path()
        if not os.path.exists(report_path):
            logger.error("report not found: %s", report_path)
            return 1
        if not args.no_open:
            open_report(report_path)
        return 0

    db_path = os.path.expanduser(args.db) if args.db else resources.default_db_path()
    dataset_path = resources.dataset_path()
    state_path = resources.state_path()
    pricing_path = resources.pricing_path()
    budgets_path = resources.budgets_path()
    report_path = resources.report_path()

    if not os.path.exists(db_path):
        if os.path.exists(dataset_path) and not args.watch:
            logger.warning("OpenCode database not found; using the existing dataset: %s", db_path)
            run_kilo_sync(args, dataset_path, pricing_path)
            run_autoclaw_sync(args, dataset_path, pricing_path)
            run_workbuddy_sync(args, dataset_path, pricing_path)
            build_report.generate_report(dataset_path, report_path, strict=not args.no_strict)
            if not args.no_open:
                open_report(report_path)
            return 0
        logger.error("OpenCode database not found: %s", db_path)
        logger.error("use --db <path> or launch OpenCode before AgentLedger")
        return 1

    extract_args = argparse.Namespace(db=db_path, full=args.full, since=args.since, build=False)
    watch_args = argparse.Namespace(db=db_path, full=args.full, since=args.since, build=True)

    if args.watch:
        extract.extract(extract_args, dataset_path, state_path, pricing_path, budgets_path)
        run_kilo_sync(args, dataset_path, pricing_path)
        run_autoclaw_sync(args, dataset_path, pricing_path)
        run_workbuddy_sync(args, dataset_path, pricing_path)
        build_report.generate_report(dataset_path, report_path, strict=not args.no_strict)
        if not args.no_open:
            open_report(report_path)
        extract.watch(watch_args, dataset_path, state_path, pricing_path, budgets_path, report_path, run_initial=False)
        return 0

    extract.extract(extract_args, dataset_path, state_path, pricing_path, budgets_path)
    run_kilo_sync(args, dataset_path, pricing_path)
    run_autoclaw_sync(args, dataset_path, pricing_path)
    run_workbuddy_sync(args, dataset_path, pricing_path)
    build_report.generate_report(dataset_path, report_path, strict=not args.no_strict)
    if not args.no_open:
        open_report(report_path)
    return 0


def main():
    try:
        raise SystemExit(run())
    except KeyboardInterrupt:
        print("Stopping.")
        raise SystemExit(130)


if __name__ == "__main__":
    main()
