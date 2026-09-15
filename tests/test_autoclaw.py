import argparse
import calendar
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from extract_autoclaw import (
    AutoclawSchemaError,
    _load_js_value,
    _parse_ts,
    _split_model,
    default_dir,
    extract,
    fetch_sessions,
    max_time,
    read_journal,
    read_snapshot,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE_DIR = os.path.join(REPO_ROOT, "Docs", "AutCLW", "TDB", "openclaw-tdb", "sample-data")

# 2026-09-05T02:05:00+01:00 == 2026-09-05T01:05:00Z, calcul indépendant du parseur.
TS_0205 = calendar.timegm((2026, 9, 5, 1, 5, 0))
TS_0305 = calendar.timegm((2026, 9, 5, 2, 5, 0))


def _write(path, var, payload):
    with open(path, "w", encoding="utf-8") as f:
        f.write("window.{}={};".format(var, json.dumps(payload)))


def _journal_entry(ts, session, agent="main", provider="zai", model="zai_auto",
                   tokens=100, in_tok=80, out_tok=20, cache=5, status="reported",
                   task="Tâche"):
    e = {"ts": ts, "agent": agent, "session": session, "task": task,
         "action": "réponse", "provider": provider, "model": model,
         "durationMs": 1000, "state": "ok", "tokenStatus": status}
    if tokens is not None:
        e["tokens"] = tokens
    if in_tok is not None:
        e["inputTokens"] = in_tok
    if out_tok is not None:
        e["outputTokens"] = out_tok
    if cache is not None:
        e["cacheReadTokens"] = cache
    return e


def _args(telemetry_dir, full=False, since=None):
    return argparse.Namespace(autoclaw_dir=telemetry_dir, autoclaw_full=full,
                              autoclaw_since=since, full=False, since=None)


class TestHelpers(unittest.TestCase):
    def test_parse_ts_utc(self):
        # 2026-09-05T02:05:00+01:00 == 2026-09-05T01:05:00Z
        self.assertEqual(_parse_ts("2026-09-05T02:05:00+01:00"), TS_0205)
        self.assertEqual(_parse_ts("2026-09-05T01:05:00Z"), TS_0205)
        self.assertIsNone(_parse_ts(None))
        self.assertIsNone(_parse_ts("nonsense"))
        self.assertEqual(_parse_ts(1700000000), 1700000000)

    def test_split_model(self):
        self.assertEqual(_split_model("zai", "zai/zai_auto"), ("zai", "zai_auto"))
        self.assertEqual(_split_model("zai", "zai_auto"), ("zai", "zai_auto"))
        self.assertEqual(_split_model(None, None), ("?", "?"))

    def test_load_js_bad_prefix(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "journal.js")
            with open(p, "w", encoding="utf-8") as f:
                f.write("var x = [];")
            with self.assertRaises(AutoclawSchemaError):
                _load_js_value(p, "TDB_JOURNAL")

    def test_default_dir_env(self):
        with patch.dict(os.environ, {"AUTOCLAW_TELEMETRY_DIR": "/tmp/tel"}):
            self.assertTrue(default_dir().endswith("tel"))

    def test_candidats_exe_prioritaires(self):
        from extract_autoclaw import candidate_dirs
        with tempfile.TemporaryDirectory() as d:
            exe_tel = os.path.join(d, "telemetry")
            os.makedirs(exe_tel)
            env = dict(os.environ)
            env.pop("AUTOCLAW_TELEMETRY_DIR", None)
            with patch.dict(os.environ, env, clear=True), \
                 patch("resources.is_frozen", return_value=True), \
                 patch.object(sys, "executable", os.path.join(d, "AgentLedger.exe")), \
                 patch("resources.user_root", return_value=os.path.join(d, "user")):
                self.assertEqual(default_dir(), os.path.normpath(exe_tel))
                cands = candidate_dirs()
                self.assertTrue(cands[0].endswith("telemetry"))

    def test_candidat_user_root_repli(self):
        with tempfile.TemporaryDirectory() as d:
            user_tel = os.path.join(d, "user", "telemetry")
            os.makedirs(user_tel)
            env = dict(os.environ)
            env.pop("AUTOCLAW_TELEMETRY_DIR", None)
            with patch.dict(os.environ, env, clear=True), \
                 patch("resources.is_frozen", return_value=True), \
                 patch.object(sys, "executable", os.path.join(d, "AgentLedger.exe")), \
                 patch("resources.user_root", return_value=os.path.join(d, "user")):
                self.assertEqual(default_dir(), os.path.normpath(user_tel))


class TestJournal(unittest.TestCase):
    def test_grouping_nominal(self):
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "journal.js"), "TDB_JOURNAL", [
                _journal_entry("2026-09-05T02:05:00+01:00", "s1", task="Première"),
                _journal_entry("2026-09-05T03:05:00+01:00", "s1", task="Deuxième"),
                _journal_entry("2026-09-05T04:05:00+01:00", "s2", agent="auto-coder",
                               provider="ollama", model="qwen:0.8b"),
            ])
            rows = fetch_sessions(d, 0, full=True)
            self.assertEqual(len(rows), 2)
            s1 = next(r for r in rows if r["source_session_id"] == "journal:s1")
            self.assertEqual(s1["source"], "autoclaw")
            self.assertEqual(s1["id"], "autoclaw:journal:s1")
            self.assertEqual(s1["agent"], "main")
            self.assertEqual(s1["project_name"], "main")
            self.assertEqual(s1["tokens_input"], 160)
            self.assertEqual(s1["tokens_output"], 40)
            self.assertEqual(s1["tokens_cache_read"], 10)
            self.assertEqual(s1["cost"], 0.0)
            self.assertEqual(s1["time_created"], TS_0205)
            self.assertEqual(s1["time_updated"], TS_0305)
            self.assertEqual(s1["provenance"]["actions"], 2)
            s2 = next(r for r in rows if r["source_session_id"] == "journal:s2")
            self.assertEqual(s2["model"], "ollama/qwen:0.8b")

    def test_tokens_fallback_total(self):
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "journal.js"), "TDB_JOURNAL", [
                _journal_entry("2026-09-05T02:05:00+01:00", "s1",
                               tokens=500, in_tok=None, out_tok=None),
            ])
            rows = fetch_sessions(d, 0, full=True)
            self.assertEqual(rows[0]["tokens_input"], 500)
            self.assertEqual(rows[0]["tokens_output"], 0)

    def test_watermark(self):
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "journal.js"), "TDB_JOURNAL", [
                _journal_entry("2026-09-05T02:05:00+01:00", "old"),
                _journal_entry("2026-09-06T02:05:00+01:00", "new"),
            ])
            delta = fetch_sessions(d, TS_0205, full=False)
            self.assertEqual([r["source_session_id"] for r in delta], ["journal:new"])
            self.assertEqual(len(fetch_sessions(d, 0, full=True)), 2)

    def test_snapshot_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "latest.js"), "TDB_REMOTE", {
                "ts": "2026-09-05T06:25:00+01:00", "provider": "zai",
                "sessions": [{"key": "agent:main:x", "channel": "webchat",
                              "model": "zai_auto", "tokens": 100, "cost": None}],
            })
            rows = fetch_sessions(d, 0, full=True)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source_session_id"], "snapshot:agent:main:x")
            self.assertEqual(rows[0]["schema_version"], "snapshot-v1")
            self.assertEqual(rows[0]["cost"], 0.0)

    def test_vide_total(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(fetch_sessions(d, 0, full=True), [])

    def test_readonly(self):
        with tempfile.TemporaryDirectory() as d:
            jp = os.path.join(d, "journal.js")
            _write(jp, "TDB_JOURNAL", [_journal_entry("2026-09-05T02:05:00+01:00", "s1")])
            with open(jp, encoding="utf-8") as f:
                before = (os.path.getmtime(jp), f.read())
            fetch_sessions(d, 0, full=True)
            with open(jp, encoding="utf-8") as f:
                self.assertEqual((os.path.getmtime(jp), f.read()), before)
            self.assertEqual(sorted(os.listdir(d)), ["journal.js"])


class TestExtract(unittest.TestCase):
    def test_dedup_et_watermark(self):
        with tempfile.TemporaryDirectory() as d:
            tel = os.path.join(d, "tel")
            os.makedirs(tel)
            _write(os.path.join(tel, "journal.js"), "TDB_JOURNAL", [
                _journal_entry("2026-09-05T02:05:00+01:00", "s1"),
            ])
            ds = os.path.join(d, "dataset.json")
            st = os.path.join(d, "state.json")
            with open(ds, "w", encoding="utf-8") as f:
                json.dump({"sessions": [{"id": "s-op", "source": "opencode"}]}, f)
            r1 = extract(_args(tel), ds, st)
            self.assertEqual(r1["status"], "ok")
            self.assertEqual(r1["new_sessions"], 1)
            r2 = extract(_args(tel), ds, st)
            self.assertEqual(r2["status"], "ok")
            self.assertEqual(r2["new_sessions"], 0)
            self.assertIn("journal:s1",
                          [s["source_session_id"] for s in r2["sessions"]])
            with open(ds, encoding="utf-8") as f:
                self.assertIn("s-op", [s["id"] for s in json.load(f)["sessions"]])

    def test_missing(self):
        with tempfile.TemporaryDirectory() as d:
            r = extract(_args(os.path.join(d, "absent")),
                        os.path.join(d, "ds.json"), os.path.join(d, "st.json"))
            self.assertEqual(r["status"], "missing")

    def test_corrupt(self):
        with tempfile.TemporaryDirectory() as d:
            tel = os.path.join(d, "tel")
            os.makedirs(tel)
            with open(os.path.join(tel, "journal.js"), "w", encoding="utf-8") as f:
                f.write("window.TDB_JOURNAL=[{bad];")
            r = extract(_args(tel), os.path.join(d, "ds.json"), os.path.join(d, "st.json"))
            self.assertEqual(r["status"], "error")

    def test_since_invalide(self):
        with tempfile.TemporaryDirectory() as d:
            tel = os.path.join(d, "tel")
            os.makedirs(tel)
            r = extract(_args(tel, since="bad"),
                        os.path.join(d, "ds.json"), os.path.join(d, "st.json"))
            self.assertEqual(r["status"], "error")

    def test_no_save_when_nothing_new(self):
        import extract_autoclaw
        with tempfile.TemporaryDirectory() as d:
            tel = os.path.join(d, "tel")
            os.makedirs(tel)
            _write(os.path.join(tel, "journal.js"), "TDB_JOURNAL", [
                _journal_entry("2026-09-05T02:05:00+01:00", "s1"),
            ])
            ds = os.path.join(d, "dataset.json")
            st = os.path.join(d, "state.json")
            with open(ds, "w", encoding="utf-8") as f:
                json.dump({"sessions": []}, f)
            extract(_args(tel), ds, st)
            calls = []
            with patch.object(extract_autoclaw, "_save_json",
                              side_effect=lambda p, v: calls.append(p)):
                r = extract(_args(tel), ds, st)
            self.assertEqual(r["new_sessions"], 0)
            self.assertEqual(calls, [])
            self.assertEqual(r["sessions"][0]["source_session_id"], "journal:s1")

    def test_max_time(self):
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, "journal.js"), "TDB_JOURNAL", [
                _journal_entry("2026-09-05T02:05:00+01:00", "s1"),
            ])
            self.assertEqual(max_time(d), TS_0205)
            self.assertEqual(max_time(os.path.join(d, "absent")), 0)


class TestSampleData(unittest.TestCase):
    def test_fixtures_documentees(self):
        if not os.path.isdir(SAMPLE_DIR):
            self.skipTest("sample-data fixtures not versioned (local Docs/ only)")
        journal = read_journal(SAMPLE_DIR)
        snap = read_snapshot(SAMPLE_DIR)
        self.assertEqual(len(journal), 8)
        rows = fetch_sessions(SAMPLE_DIR, 0, full=True)
        ids = sorted(r["source_session_id"] for r in rows)
        self.assertEqual(ids, ["journal:demo0001", "journal:demo0002"])
        demo2 = next(r for r in rows if r["source_session_id"] == "journal:demo0002")
        self.assertEqual(demo2["agent"], "auto-coder")
        self.assertIn("qwen", demo2["model"])
        self.assertTrue(all(r["time_created"] > 0 for r in rows))
        self.assertEqual(snap["sessionsTotal"], 2)


if __name__ == "__main__":
    unittest.main()
