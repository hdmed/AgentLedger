import argparse
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from extract_kilo import (
    KiloSchemaError,
    _fallback_metrics,
    _integer,
    _json,
    _number,
    _parse_model,
    _project_name,
    _seconds,
    _tokens,
    connect,
    default_db_path,
    extract,
    fetch_sessions,
    inspect_schema,
    max_time,
)


def _make_db(path, session_columns="full", with_project=True, with_messages=False):
    """Fixture SQLite Kilo. session_columns: full | minimal | no_time."""
    conn = sqlite3.connect(path)
    if session_columns == "full":
        conn.execute(
            "CREATE TABLE session (id TEXT PRIMARY KEY, project_id TEXT, directory TEXT,"
            " title TEXT, agent TEXT, model TEXT, cost REAL, tokens_input INT,"
            " tokens_output INT, tokens_reasoning INT, tokens_cache_read INT,"
            " tokens_cache_write INT, time_created INT, time_updated INT,"
            " version INT, parent_id TEXT, workspace_id TEXT, slug TEXT, time_archived INT)"
        )
    elif session_columns == "minimal":
        conn.execute(
            "CREATE TABLE session (id TEXT PRIMARY KEY, title TEXT,"
            " time_created INT, time_updated INT)"
        )
    elif session_columns == "no_time":
        conn.execute("CREATE TABLE session (id TEXT PRIMARY KEY, title TEXT)")
    if with_project:
        conn.execute("CREATE TABLE project (id TEXT PRIMARY KEY, name TEXT, worktree TEXT)")
        conn.execute("INSERT INTO project VALUES ('p1', 'KiloProj', '/tmp/kilo')")
    if with_messages:
        conn.execute(
            "CREATE TABLE session_message (id TEXT PRIMARY KEY, session_id TEXT,"
            " data TEXT, time_created INT)"
        )
        conn.execute(
            "CREATE TABLE part (id TEXT PRIMARY KEY, session_id TEXT,"
            " data TEXT, time_created INT)"
        )
    conn.commit()
    conn.close()


def _args(db_path, full=False, since=None):
    return argparse.Namespace(
        kilo_db=db_path, kilo_full=full, kilo_since=since, full=False, since=None
    )


class TestHelpers(unittest.TestCase):
    def test_parse_model(self):
        self.assertEqual(
            _parse_model({"providerID": "anthropic", "id": "claude"}),
            ("anthropic", "claude"),
        )
        self.assertEqual(_parse_model("openai/gpt"), ("openai", "gpt"))
        self.assertEqual(_parse_model("nonsense"), ("?", "?"))
        self.assertEqual(_parse_model(None), ("?", "?"))

    def test_numbers(self):
        self.assertEqual(_json('{"a":1}'), {"a": 1})
        self.assertEqual(_json("bad", "d"), "d")
        self.assertEqual(_number("1.5"), 1.5)
        self.assertEqual(_number("bad"), 0.0)
        self.assertEqual(_integer("3.9"), 3)
        self.assertEqual(_integer(None), 0)
        self.assertEqual(_seconds(1700000000000), 1700000000)
        self.assertIsNone(_seconds(None))

    def test_tokens(self):
        t = _tokens({"input": 10, "output": 5, "reasoning": 2,
                     "cache": {"read": 3, "write": 4}})
        self.assertEqual(t, {"tokens_input": 10, "tokens_output": 5,
                             "tokens_reasoning": 2, "tokens_cache_read": 3,
                             "tokens_cache_write": 4})
        self.assertEqual(_tokens(None)["tokens_input"], 0)

    def test_project_name(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "k.db")
            _make_db(db)
            conn = connect(db)
            try:
                self.assertEqual(_project_name(conn, "p1", ["id", "name"]), "KiloProj")
                self.assertEqual(_project_name(conn, "unknown", ["id", "name"]), "unknown")
                self.assertEqual(_project_name(conn, "p1", None), "p1")
            finally:
                conn.close()

    def test_default_db_path_env(self):
        with patch.dict(os.environ, {"KILO_DB": "/tmp/custom.db"}):
            self.assertTrue(default_db_path().endswith("custom.db"))


class TestSchema(unittest.TestCase):
    def test_inspect_nominal(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "k.db")
            _make_db(db, with_messages=True)
            schema = inspect_schema(db)
            self.assertIn("session", schema["tables"])
            self.assertIn("id", schema["session_columns"])
            self.assertEqual(schema["message_table"], "session_message")

    def test_inspect_missing_session(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "k.db")
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE other (id TEXT)")
            conn.commit(); conn.close()
            with self.assertRaises(KiloSchemaError):
                inspect_schema(db)

    def test_connect_readonly(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "k.db")
            _make_db(db)
            conn = connect(db)
            try:
                with self.assertRaises(sqlite3.OperationalError):
                    conn.execute("CREATE TABLE hack (id TEXT)")
            finally:
                conn.close()


class TestFetch(unittest.TestCase):
    def test_fetch_nominal_direct_columns(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "k.db")
            _make_db(db)
            conn = sqlite3.connect(db)
            conn.execute(
                "INSERT INTO session VALUES ('s1','p1','/tmp','T','agent',"
                " 'anthropic/claude', 0.5, 100, 200, 10, 5, 2,"
                " 1700000000000, 1700000100000, 1, NULL, NULL, NULL, NULL)"
            )
            conn.commit(); conn.close()
            rows = fetch_sessions(db, 0, full=True)
            self.assertEqual(len(rows), 1)
            s = rows[0]
            self.assertEqual(s["source"], "kilo")
            self.assertEqual(s["source_session_id"], "s1")
            self.assertEqual(s["id"], "kilo:s1")
            self.assertEqual(s["project_name"], "KiloProj")
            self.assertEqual(s["time_created"], 1700000000)
            self.assertEqual(s["time_updated"], 1700000100)
            self.assertEqual(s["tokens_input"], 100)
            self.assertAlmostEqual(s["cost"], 0.5)
            self.assertFalse(s["archived"])

    def test_fetch_sans_usage(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "k.db")
            _make_db(db, session_columns="minimal")
            conn = sqlite3.connect(db)
            conn.execute("INSERT INTO session VALUES ('s9', 'titre', 1700000000000, NULL)")
            conn.commit(); conn.close()
            rows = fetch_sessions(db, 0, full=True)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["tokens_input"], 0)
            self.assertEqual(rows[0]["cost"], 0.0)
            self.assertEqual(rows[0]["time_updated"], 1700000000)

    def test_fetch_fallback_messages(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "k.db")
            _make_db(db, session_columns="minimal", with_project=False,
                     with_messages=True)
            conn = sqlite3.connect(db)
            conn.execute("INSERT INTO session VALUES ('s2', 't', 1700000000000, 1700000100000)")
            payload = json.dumps({"role": "assistant",
                                  "tokens": {"input": 1000, "output": 500},
                                  "cost": 0.02,
                                  "model": {"providerID": "x", "id": "y"}})
            conn.execute("INSERT INTO session_message VALUES ('m1', 's2', ?, 1700000000000)",
                         (payload,))
            conn.commit(); conn.close()
            conn2 = connect(db)
            try:
                schema = inspect_schema(db)
                fb = _fallback_metrics(conn2, "s2", schema)
            finally:
                conn2.close()
            self.assertEqual(fb["tokens_input"], 1000)
            self.assertAlmostEqual(fb["cost"], 0.02)
            rows = fetch_sessions(db, 0, full=True)
            self.assertEqual(rows[0]["tokens_input"], 1000)

    def test_fetch_base_vide(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "k.db")
            _make_db(db)
            self.assertEqual(fetch_sessions(db, 0, full=True), [])

    def test_fetch_schema_inconnu(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "k.db")
            _make_db(db, session_columns="no_time", with_project=False)
            with self.assertRaises(KiloSchemaError):
                fetch_sessions(db, 0, full=True)

    def test_fetch_watermark(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "k.db")
            _make_db(db, with_project=False)
            conn = sqlite3.connect(db)
            conn.execute(
                "INSERT INTO session VALUES ('old',NULL,NULL,NULL,NULL,NULL,0,0,0,0,0,0,"
                " 1700000000000, 1700000000000, NULL,NULL,NULL,NULL,NULL)")
            conn.execute(
                "INSERT INTO session VALUES ('new',NULL,NULL,NULL,NULL,NULL,0,0,0,0,0,0,"
                " 1700000900000, 1700000900000, NULL,NULL,NULL,NULL,NULL)")
            conn.commit(); conn.close()
            delta = fetch_sessions(db, 1700000500, full=False)
            self.assertEqual({r["source_session_id"] for r in delta}, {"new"})
            all_rows = fetch_sessions(db, 9999999999, full=True)
            self.assertEqual(len(all_rows), 2)


class TestExtract(unittest.TestCase):
    def test_dedup_et_watermark(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "k.db")
            ds = os.path.join(d, "dataset.json")
            st = os.path.join(d, "kilo_state.json")
            _make_db(db, with_project=False)
            conn = sqlite3.connect(db)
            conn.execute(
                "INSERT INTO session VALUES ('s1',NULL,NULL,'T',NULL,NULL,0.1,1,2,0,0,0,"
                " 1700000000000, 1700000000000, NULL,NULL,NULL,NULL,NULL)")
            conn.commit(); conn.close()
            # Dataset partagé préexistant avec une session opencode (fusion additive)
            with open(ds, "w", encoding="utf-8") as f:
                json.dump({"sessions": [{"id": "s-op", "source": "opencode"}]}, f)
            r1 = extract(_args(db), ds, st)
            self.assertEqual(r1["status"], "ok")
            self.assertEqual(r1["new_sessions"], 1)
            r2 = extract(_args(db), ds, st)
            self.assertEqual(r2["status"], "ok")
            self.assertEqual(r2["new_sessions"], 0)
            ids = [s.get("source_session_id", s.get("id")) for s in r2["sessions"]]
            self.assertIn("s1", ids)
            # Le dataset partagé n'est pas écrasé : l'opencode survit
            with open(ds, "r", encoding="utf-8") as f:
                shared = json.load(f)
            self.assertIn("s-op", [s.get("id") for s in shared["sessions"]])
            with open(st, "r", encoding="utf-8") as f:
                state = json.load(f)
            self.assertEqual(state["last_time_updated"], 1700000000)
            self.assertEqual(len(state["sessions"]), 1)

    def test_missing(self):
        with tempfile.TemporaryDirectory() as d:
            r = extract(_args(os.path.join(d, "absent.db")),
                        os.path.join(d, "ds.json"), os.path.join(d, "st.json"))
            self.assertEqual(r["status"], "missing")
            self.assertEqual(r["sessions"], [])

    def test_corrupt(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "k.db")
            with open(db, "w", encoding="utf-8") as f:
                f.write("ceci n'est pas sqlite")
            r = extract(_args(db), os.path.join(d, "ds.json"), os.path.join(d, "st.json"))
            self.assertEqual(r["status"], "error")

    def test_since_invalide(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "k.db")
            _make_db(db, with_project=False)
            r = extract(_args(db, since="bad-date"),
                        os.path.join(d, "ds.json"), os.path.join(d, "st.json"))
            self.assertEqual(r["status"], "error")

    def test_no_save_when_nothing_new(self):
        import extract_kilo
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "k.db")
            ds = os.path.join(d, "dataset.json")
            st = os.path.join(d, "kilo_state.json")
            _make_db(db, with_project=False)
            conn = sqlite3.connect(db)
            conn.execute(
                "INSERT INTO session VALUES ('s1',NULL,NULL,'T',NULL,NULL,0.1,1,2,0,0,0,"
                " 1700000000000, 1700000000000, NULL,NULL,NULL,NULL,NULL)")
            conn.commit(); conn.close()
            with open(ds, "w", encoding="utf-8") as f:
                json.dump({"sessions": []}, f)
            extract(_args(db), ds, st)
            calls = []
            with patch.object(extract_kilo, "_save_json",
                              side_effect=lambda p, v: calls.append(p)):
                r = extract(_args(db), ds, st)
            self.assertEqual(r["new_sessions"], 0)
            self.assertEqual(calls, [])
            self.assertEqual(r["sessions"][0]["source_session_id"], "s1")
            with patch.object(extract_kilo, "_save_json",
                              side_effect=lambda p, v: calls.append(p)):
                conn = sqlite3.connect(db)
                conn.execute(
                    "INSERT INTO session VALUES ('s2',NULL,NULL,'T',NULL,NULL,0.1,1,2,0,0,0,"
                    " 1700000100000, 1700000100000, NULL,NULL,NULL,NULL,NULL)")
                conn.commit(); conn.close()
                r = extract(_args(db), ds, st)
            self.assertEqual(r["new_sessions"], 1)
            self.assertEqual(len(calls), 1)
            # watermark préservé quand tout est supprimé
            extract(_args(db), ds, st)  # persiste réellement l'état (s1, s2)
            conn = sqlite3.connect(db)
            conn.execute("DELETE FROM session")
            conn.commit(); conn.close()
            r = extract(_args(db), ds, st)
            self.assertEqual(r["watermark"], 1700000100)
            self.assertEqual(r["sessions"], [])

    def test_max_time(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "k.db")
            _make_db(db, with_project=False)
            conn = sqlite3.connect(db)
            conn.execute(
                "INSERT INTO session VALUES ('s1',NULL,NULL,NULL,NULL,NULL,0,0,0,0,0,0,"
                " 1700000000000, 1700000200000, NULL,NULL,NULL,NULL,NULL)")
            conn.commit(); conn.close()
            self.assertEqual(max_time(db), 1700000200)
            self.assertEqual(max_time(os.path.join(d, "absent.db")), 0)


if __name__ == "__main__":
    unittest.main()
