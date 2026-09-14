import argparse
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import launcher


def _opencode_session(sid="s-op", cost=1.0):
    return {
        "id": sid, "source": "opencode", "source_session_id": sid,
        "project_id": "p1", "project_name": "P", "directory": "",
        "title": "T", "agent": "a",
        "model": json.dumps({"providerID": "x", "id": "y"}),
        "model_label": "x/y", "provider_id": "x", "model_id": "y",
        "cost": cost, "cost_source": "opencode",
        "tokens_input": 10, "tokens_output": 5, "tokens_reasoning": 0,
        "tokens_cache_read": 0, "tokens_cache_write": 0,
        "time_created": 1700000000, "time_updated": 1700000000,
    }


def _kilo_session(sid="s-kilo", cost=2.0):    return {
        "id": "kilo:" + sid, "source": "kilo", "source_session_id": sid,
        "project_id": "p1", "project_name": "K", "directory": "",
        "title": "KT", "agent": "a",
        "model": "x/y", "model_label": "x/y",
        "provider_id": "x", "model_id": "y",
        "cost": cost, "cost_source": "kilo",
        "tokens_input": 20, "tokens_output": 10, "tokens_reasoning": 0,
        "tokens_cache_read": 0, "tokens_cache_write": 0,
        "time_created": 1700000100, "time_updated": 1700000100,
    }


def _autoclaw_session(sid="journal:s1", cost=0.0):
    return {
        "id": "autoclaw:" + sid, "source": "autoclaw", "source_session_id": sid,
        "project_id": None, "project_name": "main", "directory": None,
        "title": "T", "agent": "main",
        "model": "zai/zai_auto", "model_label": "zai/zai_auto",
        "provider_id": "zai", "model_id": "zai_auto",
        "cost": cost, "cost_source": "autoclaw",
        "tokens_input": 100, "tokens_output": 20, "tokens_reasoning": 0,
        "tokens_cache_read": 5, "tokens_cache_write": 0,
        "time_created": 1700000200, "time_updated": 1700000200,
    }


def _write_dataset(path, sessions):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"sessions": sessions, "models": [], "totals": {},
                   "pricing_config": {"models": {}}, "budgets": {},
                   "generated_at": "", "db_path": ""}, f)


def _write_pricing(path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"models": {}}, f)


class TestLauncher(unittest.TestCase):
    def test_version(self):
        self.assertEqual(launcher.run(["--version"]), 0)

    def test_version_single_source(self):
        import resources
        self.assertEqual(launcher.VERSION, resources.__version__)

    def test_parse_kilo_args(self):
        args = launcher.parse_args(["--no-open"])
        self.assertFalse(args.no_kilo)
        self.assertIsNone(args.kilo_db)
        args2 = launcher.parse_args(["--no-kilo", "--kilo-db", "x.db"])
        self.assertTrue(args2.no_kilo)
        self.assertEqual(args2.kilo_db, "x.db")

    def test_merge_additive(self):
        with tempfile.TemporaryDirectory() as d:
            ds = os.path.join(d, "dataset.json")
            pp = os.path.join(d, "pricing.json")
            _write_dataset(ds, [_opencode_session()])
            _write_pricing(pp)
            n_kilo, n_total = launcher.merge_kilo_result(
                ds, pp, {"sessions": [_kilo_session()]})
            self.assertEqual((n_kilo, n_total), (1, 2))
            with open(ds, encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["totals"]["sessions"], 2)
            self.assertAlmostEqual(data["totals"]["cost"], 3.0)
            self.assertEqual(data["totals"]["tokens_input"], 30)
            srcs = sorted(s["source"] for s in data["sessions"])
            self.assertEqual(srcs, ["kilo", "opencode"])

    def test_merge_dedup(self):
        with tempfile.TemporaryDirectory() as d:
            ds = os.path.join(d, "dataset.json")
            pp = os.path.join(d, "pricing.json")
            _write_dataset(ds, [_opencode_session()])
            _write_pricing(pp)
            res = {"sessions": [_kilo_session()]}
            launcher.merge_kilo_result(ds, pp, res)
            n_kilo, n_total = launcher.merge_kilo_result(ds, pp, res)
            self.assertEqual((n_kilo, n_total), (1, 2))

    def test_merge_kilo_vide_preserve_opencode(self):
        with tempfile.TemporaryDirectory() as d:
            ds = os.path.join(d, "dataset.json")
            pp = os.path.join(d, "pricing.json")
            _write_dataset(ds, [_opencode_session()])
            _write_pricing(pp)
            n_kilo, n_total = launcher.merge_kilo_result(ds, pp, {"sessions": []})
            self.assertEqual((n_kilo, n_total), (0, 1))

    def test_run_kilo_missing(self):
        with tempfile.TemporaryDirectory() as d:
            ds = os.path.join(d, "dataset.json")
            pp = os.path.join(d, "pricing.json")
            _write_dataset(ds, [_opencode_session()])
            _write_pricing(pp)
            args = argparse.Namespace(no_kilo=False, kilo_db=os.path.join(d, "absent.db"),
                                      kilo_full=False, kilo_since=None,
                                      full=False, since=None)
            result = launcher.run_kilo_sync(args, ds, pp)
            self.assertEqual(result["status"], "missing")
            with open(ds, encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(len(data["sessions"]), 1)

    def test_run_kilo_disabled(self):
        args = argparse.Namespace(no_kilo=True)
        self.assertIsNone(launcher.run_kilo_sync(args, "x", "y"))

    def test_parse_autoclaw_args(self):
        args = launcher.parse_args(["--no-open"])
        self.assertFalse(args.no_autoclaw)
        self.assertIsNone(args.autoclaw_dir)
        args2 = launcher.parse_args(["--no-autoclaw", "--autoclaw-dir", "tel"])
        self.assertTrue(args2.no_autoclaw)
        self.assertEqual(args2.autoclaw_dir, "tel")

    def test_merge_autoclaw_additive(self):
        with tempfile.TemporaryDirectory() as d:
            ds = os.path.join(d, "dataset.json")
            pp = os.path.join(d, "pricing.json")
            _write_dataset(ds, [_opencode_session(), _kilo_session()])
            _write_pricing(pp)
            n_auto, n_total = launcher.merge_source_result(
                ds, pp, {"source": "autoclaw", "sessions": [_autoclaw_session()]})
            self.assertEqual((n_auto, n_total), (1, 3))
            with open(ds, encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(sorted(s["source"] for s in data["sessions"]),
                             ["autoclaw", "kilo", "opencode"])

    def test_run_autoclaw_missing(self):
        with tempfile.TemporaryDirectory() as d:
            ds = os.path.join(d, "dataset.json")
            pp = os.path.join(d, "pricing.json")
            _write_dataset(ds, [_opencode_session()])
            _write_pricing(pp)
            args = argparse.Namespace(no_autoclaw=False,
                                      autoclaw_dir=os.path.join(d, "absent"),
                                      autoclaw_full=False, autoclaw_since=None,
                                      full=False, since=None)
            result = launcher.run_autoclaw_sync(args, ds, pp)
            self.assertEqual(result["status"], "missing")
            with open(ds, encoding="utf-8") as f:
                self.assertEqual(len(json.load(f)["sessions"]), 1)

    def test_run_autoclaw_disabled(self):
        args = argparse.Namespace(no_autoclaw=True)
        self.assertIsNone(launcher.run_autoclaw_sync(args, "x", "y"))

    def _workbuddy_session(self, sid="s-wb"):
        return {
            "id": "workbuddy:" + sid, "source": "workbuddy", "source_session_id": sid,
            "project_id": None, "project_name": "demo", "directory": "C:\\demo",
            "title": "T", "agent": "craft",
            "model": "?/deepseek-v4.1-flash", "model_label": "?/deepseek-v4.1-flash",
            "provider_id": "?", "model_id": "deepseek-v4.1-flash",
            "cost": 15.74, "cost_source": "workbuddy",
            "tokens_input": 100, "tokens_output": 0, "tokens_reasoning": 0,
            "tokens_cache_read": 0, "tokens_cache_write": 0,
            "time_created": 1789340117, "time_updated": 1789340117,
        }

    def test_parse_workbuddy_args(self):
        args = launcher.parse_args(["--no-open"])
        self.assertFalse(args.no_workbuddy)
        self.assertIsNone(args.workbuddy_db)
        args2 = launcher.parse_args(["--no-workbuddy", "--workbuddy-db", "w.db"])
        self.assertTrue(args2.no_workbuddy)
        self.assertEqual(args2.workbuddy_db, "w.db")

    def test_merge_workbuddy_additive(self):
        with tempfile.TemporaryDirectory() as d:
            ds = os.path.join(d, "dataset.json")
            pp = os.path.join(d, "pricing.json")
            _write_dataset(ds, [_opencode_session()])
            _write_pricing(pp)
            n_wb, n_total = launcher.merge_source_result(
                ds, pp, {"source": "workbuddy", "sessions": [self._workbuddy_session()]})
            self.assertEqual((n_wb, n_total), (1, 2))
            with open(ds, encoding="utf-8") as f:
                data = json.load(f)
            self.assertIn("workbuddy", [s["source"] for s in data["sessions"]])

    def test_run_workbuddy_missing(self):
        with tempfile.TemporaryDirectory() as d:
            ds = os.path.join(d, "dataset.json")
            pp = os.path.join(d, "pricing.json")
            _write_dataset(ds, [_opencode_session()])
            _write_pricing(pp)
            args = argparse.Namespace(no_workbuddy=False,
                                      workbuddy_db=os.path.join(d, "absent.db"),
                                      workbuddy_full=False, workbuddy_since=None,
                                      full=False, since=None)
            result = launcher.run_workbuddy_sync(args, ds, pp)
            self.assertEqual(result["status"], "missing")

    def test_run_workbuddy_disabled(self):
        args = argparse.Namespace(no_workbuddy=True)
        self.assertIsNone(launcher.run_workbuddy_sync(args, "x", "y"))
    def test_report_contient_filtre_source(self):
        import build_report
        with tempfile.TemporaryDirectory() as d:
            ds = os.path.join(d, "dataset.json")
            out = os.path.join(d, "report.html")
            _write_dataset(ds, [_opencode_session(), _kilo_session()])
            build_report.generate_report(ds, out)
            with open(out, encoding="utf-8") as f:
                html = f.read()
            self.assertIn('id="f-source"', html)
            self.assertIn("kilo:s-kilo", html)

    def test_report_structure_onglets(self):
        import re
        import build_report
        with tempfile.TemporaryDirectory() as d:
            ds = os.path.join(d, "dataset.json")
            out = os.path.join(d, "report.html")
            _write_dataset(ds, [_opencode_session(), _kilo_session()])
            build_report.generate_report(ds, out)
            with open(out, encoding="utf-8") as f:
                html = f.read()
            # 4 onglets + 4 vues + drawer + barre filtres
            for vid in ("view-overview", "view-modeles", "view-projets", "view-sessions"):
                self.assertIn('id="%s"' % vid, html)
            self.assertEqual(len(re.findall(r'class="tab-btn', html)), 4)
            for eid in ("drawer", "drawer-overlay", "drawer-close", "drawer-body",
                        "filterbar", "filters-panel", "filters-toggle", "nlq"):
                self.assertIn('id="%s"' % eid, html)
            # ancienne sidebar supprimée, plus de doublons de canvas
            self.assertNotIn("nav-export-csv", html)
            self.assertNotIn('class="sidebar"', html)
            for cid in ("c-cost-day", "c-tok-day", "c-cost-model", "c-cost-agent",
                        "c-cost-hist", "c-cache", "c-forecast", "c-cost-team"):
                self.assertEqual(html.count('id="%s"' % cid), 1)
            # répartition : graphes d'abord en overview, table en sessions
            overview = html.split('id="view-overview"')[1].split("</section>")[0]
            self.assertIn("c-cost-day", overview)
            sessions = html.split('id="view-sessions"')[1].split("</section>")[0]
            self.assertIn('id="table-card"', sessions)

    def test_dayfrom_mixtes_secondes_ms(self):
        import re
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "templates", "report_template.html"),
                  encoding="utf-8") as f:
            tpl = f.read()
        # dayFrom adaptatif : secondes (dataset normalisé) et ms (legacy)
        m = re.search(r"function dayFrom\(ts\)\{.*?\}", tpl)
        self.assertIsNotNone(m)
        self.assertIn("100000000000", m.group(0))
        # graphes par jour en bas de la vue d'ensemble
        overview = tpl.split('id="view-overview"')[1].split("</section>")[0]
        self.assertLess(overview.index("c-forecast"), overview.index("c-cost-day"))
        self.assertLess(overview.index("c-cost-day"), overview.index("c-tok-day"))
        # les 3 derniers graphes occupent chacun une ligne entière
        for cid in ("c-forecast", "c-cost-day", "c-tok-day"):
            div = overview.split('data-chart="%s"' % cid)[0].rsplit("<div", 1)[1]
            self.assertIn("chart-full", div)


if __name__ == "__main__":
    unittest.main()
