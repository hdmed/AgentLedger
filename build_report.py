#!/usr/bin/env python3
"""Genere dist/report.html : rapport visuel 100%% hors-ligne.

Lit data/dataset.json (produit par extract.py), inline Chart.js et le
dataset, puis ecrit un fichier HTML unique, consultable sans reseau.

Usage : python build_report.py [--dataset data/dataset.json] [--out dist/report.html]
"""

import argparse
import json
import os
import logging

import resources

BASE_DIR = resources.app_root()
DEFAULT_DATASET = resources.dataset_path()
CHART_JS = resources.resource_path("assets", "chart.umd.min.js")
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


def generate_report(dataset_path=DEFAULT_DATASET, out_path=DEFAULT_OUT, strict=False, external=False):
    try:
        with open(dataset_path, "r", encoding="utf-8") as f:
            dataset = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error("impossible de lire {}: {}".format(dataset_path, e))
        print("Lancer d'abord : python extract.py --full")
        raise SystemExit(1)

    chartjs = read_asset(CHART_JS)
    if not TEMPLATE:
        msg = "AVERTISSEMENT: {} introuvable, rapport impossible".format(TEMPLATE_PATH)
        logger.warning(msg)
        if strict:
            raise SystemExit(1)
    if not chartjs:
        msg = "AVERTISSEMENT: {} introuvable, graphes desactives".format(CHART_JS)
        logger.warning(msg)
        if strict:
            raise SystemExit(1)

    # securite inline : neutralise les tags dans les contenus injectes uniquement
    def sanitize(content):
        return (content.replace("</script", "<\\/script")
                .replace("<!--", "<\\!--")
                .replace("//# sourceMappingURL=chart.umd.js.map", ""))

    chartjs = sanitize(chartjs)
    if external:
        dataset_json = "{}"
        html = TEMPLATE.replace("/*__DATASET__*/", dataset_json)
        loader = """
<div id="loading" style="text-align:center;padding:20px;color:var(--mut)">Chargement donnees...</div>
<script>
(function(){
  const ds = document.currentScript.dataset.src || "data/dataset.json";
  fetch(ds).then(r=>r.json()).then(j=>{
    DATA=j; SESSIONS=j.sessions||[]; PRICING=(j.pricing_config||{}).models||{};
    const el=document.getElementById('loading'); if(el) el.remove();
    if(typeof initApp==='function') initApp();
  }).catch(e=>{
    const el=document.getElementById('loading');
    if(el) el.textContent='Erreur chargement '+ds+': '+e;
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

    out_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info("[build] OK -> {} ({:.2f} MB)".format(out_path, os.path.getsize(out_path) / 1e6))
    logger.info("[build] {} sessions, {} modeles{}".format(len(dataset.get("sessions", [])), len(dataset.get("models", [])), " (external)" if external else ""))
    return out_path


def main():
    ap = argparse.ArgumentParser(description="Generation rapport HTML hors-ligne")
    ap.add_argument("--dataset", default=DEFAULT_DATASET)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--strict", action="store_true", help="echoue si Chart.js manquant")
    ap.add_argument("--external", action="store_true", help="dataset externe (fetch) au lieu d'inline, pour gros volumes")
    args = ap.parse_args()
    generate_report(args.dataset, args.out, args.strict, args.external)



if __name__ == "__main__":
    main()
