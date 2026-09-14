import argparse
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from extract_workbuddy import (
    WorkbuddySchemaError,
    _credits,
    _project_name,
    _seconds,
    _split_model,
    connect,
    default_db_path,
    extract,
    fetch_sessions,
    inspect_schema,
    max_time,
)


def _make_db(path, with_usage=True, with_sessions=True):
    conn = sqlite3.connect(path)
    if with_sessions:
        conn.execute(
            "CREATE TABLE sessions (id TEXT PRIMARY KEY, cwd TEXT, title TEXT,"
            " custom_title TEXT, status TEXT, created_at INT, updated_at INT,"
            " last_activity_at INT, deleted_at INT, mode TEXT, model TEXT,"
            " project_id TEXT)"
        )
    if with_usage:
        conn.execute(
            "CREATE TABLE session_usage (session_id TEXT PRIMARY KEY, used INT,"
            " size INT, updated_at INT, credit_json TEXT)"
        )
    conn.commit()
    conn.close()


def _args(db_path, full=False, since=None):
    return argparse.Namespace(workbuddy_db=db_path, workbuddy_full=full,
                              workbuddy_since=since, full=False, since=None)


class TestHelpers(unittest.TestCase):
    def test_seconds(self):
        self.assertEqual(_seconds(1789340117826), 1789340117)
        self.assertEqual(_seconds(1700000000), 1700000000)
        self.assertEqual(_seconds(None), 0)

    def test_credits(self):
        self.assertAlmostEqual(_credits(json.dumps({"a": 15.74, "b": 2.0})), 17.74)
        self.assertEqual(_credits(None), 0.0)
        self.assertEqual(_credits("n'importe quoi"), 0.0)
        self.assertEqual(_credits(json.dumps({"a": "x"})), 0.0)

    def test_split_model(self):
        self.assertEqual(_split_model("deepseek-v4.1-flash"), ("?", "deepseek-v4.1-flash"))
        self.assertEqual(_split_model("prov/mod"), ("prov", "mod"))
        self.assertEqual(_split_model(None), ("?", "?"))

    def test_project_name(self):
        self.assertEqual(_project_name("C:\\Users\\DII\\proj", None), "proj")
        self.assertEqual(_project_name("/tmp/x", None), "x")
        self.assertEqual(_project_name(None, "p9"), "p9")
        self.assertEqual(_project_name(None, None), "?")

    def test_default_db_path_env(self):
        with patch.dict(os.environ, {"WORKBUDDY_DB": "/tmp/wb.db"}):
            self.assertTrue(default_db_path().endswith("wb.db"))


class TestSchema(unittest.TestCase):
    def test_inspect_nominal(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "w.db")
            _make_db(db)
            schema = inspect_schema(db)
            self.assertIn("sessions", schema["tables"])
            self.assertIn("id", schema["session_columns"])
            self.assertIsNotNone(schema["usage_columns"])

    def test_inspect_missing_table(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "w.db")
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE autre (id TEXT)")
            conn.commit(); conn.close()
            with self.assertRaises(WorkbuddySchemaError):
                inspect_schema(db)

    def test_connect_readonly(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "w.db")
            _make_db(db)
            conn = connect(db)
            try:
                with self.assertRaises(sqlite3.OperationalError):
                    conn.execute("CREATE TABLE hack (id TEXT)")
            finally:
                conn.close()


class TestFetch(unittest.TestCase):
    def _seed(self, db):
        conn = sqlite3.connect(db)
        conn.execute(
            "INSERT INTO sessions VALUES ('s1','C:\\Projets\\demo',NULL,'T1','working',"
            " 1789340117826,1789345176986,1789341034881,NULL,'craft','deepseek-v4.1-flash',NULL)")
        conn.execute(
            "INSERT INTO session_usage VALUES (?,?,?,?,?)",
            ('s1', 241922, 300000, 1789345154928, json.dumps({"uuid": 15.74})))
        conn.commit(); conn.close()

    def test_fetch_nominal(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "w.db")
            _make_db(db)
            self._seed(db)
            rows = fetch_sessions(db, 0, full=True)
            self.assertEqual(len(rows), 1)
            s = rows[0]
            self.assertEqual(s["source"], "workbuddy")
            self.assertEqual(s["source_session_id"], "s1")
            self.assertEqual(s["id"], "workbuddy:s1")
            self.assertEqual(s["project_name"], "demo")
            self.assertEqual(s["agent"], "craft")
            self.assertEqual(s["model"], "?/deepseek-v4.1-flash")
            self.assertEqual(s["time_created"], 1789340117)
            self.assertEqual(s["time_updated"], 1789345176)
            self.assertEqual(s["tokens_input"], 241922)
            self.assertAlmostEqual(s["cost"], 15.74)
            self.assertFalse(s["archived"])
            self.assertEqual(s["provenance"]["context_size"], 300000)

    def test_fetch_sans_usage(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "w.db")
            _make_db(db, with_usage=False)
            conn = sqlite3.connect(db)
            conn.execute("INSERT INTO sessions VALUES ('s1',NULL,NULL,NULL,'working',"
                         " 1789340117826,NULL,NULL,NULL,'craft','m',NULL)")
            conn.commit(); conn.close()
            rows = fetch_sessions(db, 0, full=True)
            self.assertEqual(rows[0]["cost"], 0.0)
            self.assertEqual(rows[0]["tokens_input"], 0)

    def test_fetch_archivee(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "w.db")
            _make_db(db, with_usage=False)
            conn = sqlite3.connect(db)
            conn.execute("INSERT INTO sessions VALUES ('s1',NULL,NULL,NULL,'done',"
                         " 1789340117826,1789340117826,NULL,1789340200000,'craft','m',NULL)")
            conn.commit(); conn.close()
            self.assertTrue(fetch_sessions(db, 0, full=True)[0]["archived"])

    def test_fetch_vide(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "w.db")
            _make_db(db)
            self.assertEqual(fetch_sessions(db, 0, full=True), [])

    def test_fetch_watermark(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "w.db")
            _make_db(db, with_usage=False)
            conn = sqlite3.connect(db)
            conn.execute("INSERT INTO sessions VALUES ('old',NULL,NULL,NULL,'done',"
                         " 1700000000000,1700000000000,NULL,NULL,'craft','m',NULL)")
            conn.execute("INSERT INTO sessions VALUES ('new',NULL,NULL,NULL,'working',"
                         " 1789340117826,1789340117826,NULL,NULL,'craft','m',NULL)")
            conn.commit(); conn.close()
            delta = fetch_sessions(db, 1789300000, full=False)
            self.assertEqual([r["source_session_id"] for r in delta], ["new"])


class TestExtract(unittest.TestCase):
    def test_dedup_et_watermark(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "w.db")
            ds = os.path.join(d, "dataset.json")
            st = os.path.join(d, "state.json")
            _make_db(db, with_usage=False)
            conn = sqlite3.connect(db)
            conn.execute("INSERT INTO sessions VALUES ('s1',NULL,'T',NULL,'working',"
                         " 1789340117000,1789340117000,NULL,NULL,'craft','m',NULL)")
            conn.commit(); conn.close()
            with open(ds, "w", encoding="utf-8") as f:
                json.dump({"sessions": [{"id": "s-op", "source": "opencode"}]}, f)
            r1 = extract(_args(db), ds, st)
            self.assertEqual(r1["status"], "ok")
            self.assertEqual(r1["new_sessions"], 1)
            r2 = extract(_args(db), ds, st)
            self.assertEqual(r2["new_sessions"], 0)
            self.assertIn("s1", [s["source_session_id"] for s in r2["sessions"]])
            with open(ds, encoding="utf-8") as f:
                self.assertIn("s-op", [s["id"] for s in json.load(f)["sessions"]])

    def test_missing(self):
        with tempfile.TemporaryDirectory() as d:
            r = extract(_args(os.path.join(d, "absent.db")),
                        os.path.join(d, "ds.json"), os.path.join(d, "st.json"))
            self.assertEqual(r["status"], "missing")

    def test_corrupt(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "w.db")
            with open(db, "w", encoding="utf-8") as f:
                f.write("pas sqlite")
            r = extract(_args(db), os.path.join(d, "ds.json"), os.path.join(d, "st.json"))
            self.assertEqual(r["status"], "error")

    def test_since_invalide(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "w.db")
            _make_db(db)
            r = extract(_args(db, since="bad"),
                        os.path.join(d, "ds.json"), os.path.join(d, "st.json"))
            self.assertEqual(r["status"], "error")

    def test_max_time(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "w.db")
            _make_db(db, with_usage=False)
            conn = sqlite3.connect(db)
            conn.execute("INSERT INTO sessions VALUES ('s1',NULL,NULL,NULL,'working',"
                         " 1789340117826,1789340117826,NULL,NULL,'craft','m',NULL)")
            conn.commit(); conn.close()
            self.assertEqual(max_time(db), 1789340117)
            self.assertEqual(max_time(os.path.join(d, "absent.db")), 0)


if __name__ == "__main__":
    unittest.main()
