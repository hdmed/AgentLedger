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
logger = logging.getLogger("opencost")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Tableau de bord OpenCost autonome")
    parser.add_argument("--db", help="chemin vers opencode.db")
    parser.add_argument("--full", action="store_true", help="reconstruire le dataset complet")
    parser.add_argument("--since", help="extraire depuis une date AAAA-MM-JJ")
    parser.add_argument("--watch", action="store_true", help="surveiller la base après le premier rapport")
    parser.add_argument("--reset", action="store_true", help="supprimer dataset, état et rapport avant extraction")
    parser.add_argument("--open-only", action="store_true", help="ouvrir le rapport existant sans extraction")
    parser.add_argument("--no-open", action="store_true", help="ne pas ouvrir le navigateur")
    parser.add_argument("--no-strict", action="store_true", help="tolérer un asset Chart.js manquant")
    parser.add_argument("--diagnose", action="store_true", help="afficher les chemins et l'état des ressources")
    parser.add_argument("--version", action="store_true", help="afficher la version")
    parser.add_argument("--kilo-db", default=None, help="chemin vers kilo.db (défaut: détection auto)")
    parser.add_argument("--kilo-full", action="store_true", help="re-extraction complète Kilo")
    parser.add_argument("--kilo-since", default=None, help="extraire Kilo depuis une date AAAA-MM-JJ")
    parser.add_argument("--no-kilo", action="store_true", help="désactiver le connecteur Kilo")
    parser.add_argument("--autoclaw-dir", default=None, help="dossier telemetry/ AutoClaw (défaut: Docs/AutCLW/...)")
    parser.add_argument("--autoclaw-full", action="store_true", help="re-extraction complète AutoClaw")
    parser.add_argument("--autoclaw-since", default=None, help="extraire AutoClaw depuis une date AAAA-MM-JJ")
    parser.add_argument("--no-autoclaw", action="store_true", help="désactiver le connecteur AutoClaw")
    parser.add_argument("--workbuddy-db", default=None, help="chemin vers workbuddy.db (défaut: détection auto)")
    parser.add_argument("--workbuddy-full", action="store_true", help="re-extraction complète WorkBuddy")
    parser.add_argument("--workbuddy-since", default=None, help="extraire WorkBuddy depuis une date AAAA-MM-JJ")
    parser.add_argument("--no-workbuddy", action="store_true", help="désactiver le connecteur WorkBuddy")
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
    """Compatibilité ascendante : fusion d'une source via le chemin générique."""
    return merge_source_result(dataset_path, pricing_path, kilo_result)


def merge_source_result(dataset_path, pricing_path, source_result):
    """Fusion additive des sessions d'une source dans le dataset partagé.

    Clé de dédup (source, source_session_id). L'absence ou l'échec
    d'une source ne supprime jamais les sessions des autres sources.
    Retourne (nb_source, total).
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
        # guérison : labels écrasés en "unknown" par les anciennes fusions
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
    """Exécute le connecteur Kilo et fusionne. Ne bloque jamais les autres sources."""
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
        logger.info("Kilo absent (%s) : dataset OpenCode conservé", result.get("db_path"))
        return result
    if status == "error":
        logger.warning("Kilo indisponible (%s) : dataset OpenCode conservé",
                       result.get("error") or result.get("db_path"))
        return result
    n_kilo, n_total = merge_kilo_result(dataset_path, pricing_path, result)
    logger.info("Kilo fusionné : %d session(s) kilo, %d au total", n_kilo, n_total)
    return result


def run_autoclaw_sync(args, dataset_path, pricing_path):
    """Exécute le connecteur AutoClaw et fusionne. Ne bloque jamais les autres sources."""
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
        logger.info("AutoClaw absent (%s) : autres sources conservées", result.get("telemetry_dir"))
        return result
    if status == "error":
        logger.warning("AutoClaw indisponible (%s) : autres sources conservées",
                       result.get("error") or result.get("telemetry_dir"))
        return result
    n_auto, n_total = merge_source_result(dataset_path, pricing_path, result)
    logger.info("AutoClaw fusionné : %d session(s) autoclaw, %d au total", n_auto, n_total)
    return result


def run_workbuddy_sync(args, dataset_path, pricing_path):
    """Exécute le connecteur WorkBuddy et fusionne. Ne bloque jamais les autres sources."""
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
        logger.info("WorkBuddy absent (%s) : autres sources conservées", result.get("db_path"))
        return result
    if status == "error":
        logger.warning("WorkBuddy indisponible (%s) : autres sources conservées",
                       result.get("error") or result.get("db_path"))
        return result
    n_wb, n_total = merge_source_result(dataset_path, pricing_path, result)
    logger.info("WorkBuddy fusionné : %d session(s) workbuddy, %d au total", n_wb, n_total)
    return result


def open_report(path):
    uri = Path(os.path.abspath(path)).as_uri()
    if not webbrowser.open(uri):
        logger.warning("impossible d'ouvrir le navigateur; rapport disponible : %s", path)


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
        print("OpenCost {}".format(VERSION))
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
            logger.error("rapport introuvable: %s", report_path)
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
            logger.warning("base OpenCode introuvable; utilisation du dataset existant: %s", db_path)
            run_kilo_sync(args, dataset_path, pricing_path)
            run_autoclaw_sync(args, dataset_path, pricing_path)
            run_workbuddy_sync(args, dataset_path, pricing_path)
            build_report.generate_report(dataset_path, report_path, strict=not args.no_strict)
            if not args.no_open:
                open_report(report_path)
            return 0
        logger.error("base OpenCode introuvable: %s", db_path)
        logger.error("utilisez --db <chemin> ou lancez OpenCode avant OpenCost")
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
        print("Arret.")
        raise SystemExit(130)


if __name__ == "__main__":
    main()
