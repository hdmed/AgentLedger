"""extract.py must never drop foreign-source sessions (kilo/autoclaw/workbuddy).

Regression test: a direct extract.py run (incremental or --full) used to
wipe sessions merged by the launcher because the cleanup only knew OpenCode
ids. Foreign sessions are owned by their connectors and carried over.
"""
import argparse
import json
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import extract


def _make_db(path):
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE project (id TEXT PRIMARY KEY, name TEXT, worktree TEXT)")
    cur.execute("CREATE TABLE session (id TEXT PRIMARY KEY, project_id TEXT, directory TEXT, title TEXT, agent TEXT, model TEXT, cost REAL, tokens_input INTEGER, tokens_output INTEGER, tokens_reasoning INTEGER, tokens_cache_read INTEGER, tokens_cache_write INTEGER, time_created INTEGER, time_updated INTEGER)")
    cur.execute("INSERT INTO project VALUES ('p1', 'P1', '/tmp/p1')")
    cur.execute("INSERT INTO session VALUES ('s1', 'p1', '/tmp/p1', 'S1', 'A', 'prov/mod', 0.5, 10, 20, 0, 0, 0, 1700000000, 1700000000)")
    conn.commit()
    conn.close()


def _foreign():
    return {"id": "k9", "source": "kilo", "source_session_id": "k9",
            "model_label": "k/m", "provider_id": "k", "model_id": "m",
            "title": "K", "agent": "A", "project_name": "P",
            "cost": 1.0, "cost_source": "kilo",
            "tokens_input": 1, "tokens_output": 2, "tokens_reasoning": 0,
            "tokens_cache_read": 0, "tokens_cache_write": 0,
            "time_created": 1700000000, "time_updated": 1700000000}


class TestForeignPreserved(unittest.TestCase):
    def _setup(self, d):
        db = os.path.join(d, "t.db")
        _make_db(db)
        ds = os.path.join(d, "dataset.json")
        st = os.path.join(d, "state.json")
        pp = os.path.join(d, "pricing.json")
        bp = os.path.join(d, "budgets.json")
        with open(ds, "w", encoding="utf-8") as f:
            json.dump({"sessions": [
                {"id": "s1", "source": "opencode", "source_session_id": "s1",
                 "time_created": 1700000000, "time_updated": 1700000000},
                _foreign(),
            ]}, f)
        with open(pp, "w", encoding="utf-8") as f:
            json.dump({"models": {}}, f)
        with open(bp, "w", encoding="utf-8") as f:
            json.dump({}, f)
        return db, ds, st, pp, bp

    def _sources(self, ds):
        with open(ds, encoding="utf-8") as f:
            data = json.load(f)
        return {s.get("source", "opencode") for s in data["sessions"]}, len(data["sessions"])

    def test_incremental_keeps_foreign(self):
        with tempfile.TemporaryDirectory() as d:
            db, ds, st, pp, bp = self._setup(d)
            args = argparse.Namespace(db=db, full=False, since=None)
            self.assertTrue(extract.extract(args, ds, st, pp, bp))
            sources, n = self._sources(ds)
            self.assertEqual({"opencode", "kilo"}, sources)
            self.assertEqual(2, n)

    def test_full_keeps_foreign(self):
        with tempfile.TemporaryDirectory() as d:
            db, ds, st, pp, bp = self._setup(d)
            args = argparse.Namespace(db=db, full=True, since=None)
            self.assertTrue(extract.extract(args, ds, st, pp, bp))
            sources, n = self._sources(ds)
            self.assertEqual({"opencode", "kilo"}, sources)
            self.assertEqual(2, n)


if __name__ == "__main__":
    unittest.main()
