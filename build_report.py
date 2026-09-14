#!/usr/bin/env python3
"""Generate dist/report.html: a 100%% offline visual report.

Reads data/dataset.json (produced by extract.py), inlines Chart.js, the
locales/*.json UI strings and the dataset, then writes a single HTML file
viewable without network.

Usage: python build_report.py [--dataset data/dataset.json] [--out dist/report.html]
"""

import argparse
import json
import os
import logging

import resources

BASE_DIR = resources.app_root()
DEFAULT_DATASET = resources.dataset_path()
CHART_JS = resources.resource_path("assets", "chart.umd.min.js")
LOCALES_DIR = resources.resource_path("locales")
DEFAULT_OUT = resources.report_path()
TEMPLATE_PATH = resources.resource_path("templates", "report_template.html")

logging.basicConfig(level=logging.INFO, format='[build] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def read_asset(path, fallback=""):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return fallback


# Template is now loaded from TEMPLATE_PATH
TEMPLATE = read_asset(TEMPLATE_PATH)


def load_locales(locales_dir):
    """Load locales/*.json into {lang: {key: text}}. Skips invalid files."""
    locales = {}
    try:
        names = sorted(os.listdir(locales_dir))
    except OSError:
        return locales
    for name in names:
        if not name.endswith(".json"):
            continue
        lang = name[:-5]
        try:
            with open(os.path.join(locales_dir, name), "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            logger.warning("ignoring invalid locale {}: {}".format(name, e))
            continue
        if isinstance(data, dict) and data:
            locales[lang] = data
    return locales


def generate_report(dataset_path=DEFAULT_DATASET, out_path=DEFAULT_OUT, strict=False, external=False):
    try:
        with open(dataset_path, "r", encoding="utf-8") as f:
            dataset = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error("cannot read {}: {}".format(dataset_path, e))
        print("Run first: python extract.py --full")
        raise SystemExit(1)

    chartjs = read_asset(CHART_JS)
    if not TEMPLATE:
        msg = "WARNING: {} not found, report impossible".format(TEMPLATE_PATH)
        logger.warning(msg)
        if strict:
            raise SystemExit(1)
    if not chartjs:
        msg = "WARNING: {} not found, charts disabled".format(CHART_JS)
        logger.warning(msg)
        if strict:
            raise SystemExit(1)

    # inline safety: neutralize tags in injected content only
    def sanitize(content):
        return (content.replace("</script", "<\\/script")
                .replace("<!--", "<\\!--")
                .replace("//# sourceMappingURL=chart.umd.js.map", ""))

    chartjs = sanitize(chartjs)
    locales = load_locales(LOCALES_DIR)
    if not locales:
        msg = "WARNING: {} has no locales/*.json, UI strings missing".format(LOCALES_DIR)
        logger.warning(msg)
        if strict:
            raise SystemExit(1)
    if external:
        dataset_json = "{}"
        html = TEMPLATE.replace("/*__DATASET__*/", dataset_json)
        loader = """
<div id="loading" style="text-align:center;padding:20px;color:var(--mut)">Loading data...</div>
<script>
(function(){
  const ds = document.currentScript.dataset.src || "data/dataset.json";
  fetch(ds).then(r=>r.json()).then(j=>{
    DATA=j; SESSIONS=j.sessions||[]; PRICING=(j.pricing_config||{}).models||{};
    const el=document.getElementById('loading'); if(el) el.remove();
    if(typeof initApp==='function') initApp();
  }).catch(e=>{
    const el=document.getElementById('loading');
    if(el) el.textContent='Error loading '+ds+': '+e;
  });
})();
</script>
"""
        html = html.replace("if (document.readyState === 'loading'){", "if(false && document.readyState === 'loading'){")
        html = html.replace("</body>", loader + "</body>")
        ext_path = os.path.join(os.path.dirname(os.path.abspath(out_path)), "dataset.json")
        os.makedirs(os.path.dirname(ext_path), exist_ok=True)
        with open(ext_path, "w", encoding="utf-8") as ef:
            json.dump(dataset, ef, ensure_ascii=False)
        logger.info("[build] external -> {}".format(ext_path))
    else:
        dataset_json = sanitize(json.dumps(dataset, ensure_ascii=False, separators=(",", ":")))
        html = TEMPLATE.replace("/*__DATASET__*/", dataset_json)
    html = html.replace("/*__CHARTJS__*/", chartjs)
    html = html.replace("/*__LOCALES__*/", sanitize(json.dumps(locales, ensure_ascii=False, separators=(",", ":"))))

    out_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info("[build] OK -> {} ({:.2f} MB)".format(out_path, os.path.getsize(out_path) / 1e6))
    logger.info("[build] {} sessions, {} models{}".format(len(dataset.get("sessions", [])), len(dataset.get("models", [])), " (external)" if external else ""))
    return out_path


def main():
    ap = argparse.ArgumentParser(description="Offline HTML report generation")
    ap.add_argument("--dataset", default=DEFAULT_DATASET)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--strict", action="store_true", help="fail when Chart.js is missing")
    ap.add_argument("--external", action="store_true", help="external dataset (fetch) instead of inline, for large volumes")
    args = ap.parse_args()
    generate_report(args.dataset, args.out, args.strict, args.external)



if __name__ == "__main__":
    main()
