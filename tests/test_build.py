import unittest, json, sys, os, tempfile, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from extract import load_json, fetch_sessions, to_seconds, db_threshold

class TestLoadJson(unittest.TestCase):
    def test_corrupt_backup(self):
        with tempfile.TemporaryDirectory() as d:
            p=os.path.join(d,"a.json")
            with open(p, "w", encoding="utf-8") as f:
                f.write("{bad")
            v=load_json(p, {"x":1})
            self.assertEqual(v, {"x":1})
            self.assertTrue(any(f.startswith("a.json.corrupt.") for f in os.listdir(d)))

    def test_missing_returns_default(self):
        self.assertEqual(load_json("/no/such/file.json", 42), 42)

class TestTimestamps(unittest.TestCase):
    def test_to_seconds(self):
        self.assertEqual(to_seconds(1769817200248), 1769817200)
        self.assertEqual(to_seconds(1700000000), 1700000000)
        self.assertIsNone(to_seconds(None))
        self.assertEqual(to_seconds("bad"), "bad")

    def test_db_threshold(self):
        # base en ms : watermark s converti, watermark ms legacy tel quel
        self.assertEqual(db_threshold(1700000000, 1769817200248), 1700000000000)
        self.assertEqual(db_threshold(1769817200248, 1769817200248), 1769817200248)
        # base en s : watermark ms legacy reconverti, watermark s tel quel
        self.assertEqual(db_threshold(2000000000000, 2000), 2000000000)
        self.assertEqual(db_threshold(1500, 2000), 1500)
        self.assertEqual(db_threshold(0, 0), 0)

    def test_fetch_ms_normalized(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "t.db")
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE session (id TEXT PRIMARY KEY, project_id TEXT, directory TEXT, title TEXT, agent TEXT, model TEXT, cost REAL, tokens_input INT, tokens_output INT, tokens_reasoning INT, tokens_cache_read INT, tokens_cache_write INT, time_created INT, time_updated INT)")
            conn.execute("CREATE TABLE project (id TEXT PRIMARY KEY, name TEXT, worktree TEXT)")
            conn.execute("INSERT INTO session VALUES ('a','p1','','t','ag','{}',1,0,0,0,0,0,1769817200248,1769817200248)".replace("{}", json.dumps({"providerID": "opencode", "id": "m"})))
            conn.commit(); conn.close()
            # watermark en secondes filtre correctement une base en ms ;
            # même seconde => refetch dédupliqué par id (reste 248 ms)
            rows = fetch_sessions(db, 1769817201, False)
            self.assertEqual(rows, [])
            rows = fetch_sessions(db, 1769817200, False)
            self.assertEqual(len(rows), 1)
            rows = fetch_sessions(db, 1769817199, False)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["time_created"], 1769817200)
            self.assertEqual(rows[0]["source"], "opencode")

    def test_incremental_ne_refetch_pas_tout(self):
        """Garde-fou : le watermark avance, la 2e passe ne reprend pas tout (ms)."""
        import argparse
        import extract as _ex
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "t.db")
            ds = os.path.join(d, "dataset.json")
            st = os.path.join(d, "state.json")
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE session (id TEXT PRIMARY KEY, project_id TEXT, directory TEXT, title TEXT, agent TEXT, model TEXT, cost REAL, tokens_input INT, tokens_output INT, tokens_reasoning INT, tokens_cache_read INT, tokens_cache_write INT, time_created INT, time_updated INT)")
            conn.execute("CREATE TABLE project (id TEXT PRIMARY KEY, name TEXT, worktree TEXT)")
            for i in range(5):
                conn.execute("INSERT INTO session VALUES ('s%d','p1','','t','ag','{}',1,0,0,0,0,0,%d,%d)".replace("{}", json.dumps({"providerID": "opencode", "id": "m"})) % (i, 1769817200000 + i * 1000, 1769817200000 + i * 1000))
            conn.commit(); conn.close()
            args = argparse.Namespace(db=db, full=True, since=None, build=False)
            self.assertTrue(_ex.extract(args, ds, st, os.path.join(d, "p.json"), os.path.join(d, "b.json")))
            with open(st, encoding="utf-8") as f:
                wm1 = json.load(f)["last_time_updated"]
            self.assertLess(wm1, 100_000_000_000)  # watermark stocké en secondes
            args2 = argparse.Namespace(db=db, full=False, since=None, build=False)
            self.assertTrue(_ex.extract(args2, ds, st, os.path.join(d, "p.json"), os.path.join(d, "b.json")))
            with open(ds, encoding="utf-8") as f:
                sessions = json.load(f)["sessions"]
            self.assertEqual(len(sessions), 5)  # aucun doublon
            with open(st, encoding="utf-8") as f:
                wm2 = json.load(f)["last_time_updated"]
            self.assertGreaterEqual(wm2, wm1)  # le watermark avance, jamais de recul

class TestFetch(unittest.TestCase):
    def test_fetch_coalesce(self):
        with tempfile.TemporaryDirectory() as d:
            db=os.path.join(d,"t.db")
            conn=sqlite3.connect(db)
            conn.execute("CREATE TABLE session (id TEXT PRIMARY KEY, project_id TEXT, directory TEXT, title TEXT, agent TEXT, model TEXT, cost REAL, tokens_input INT, tokens_output INT, tokens_reasoning INT, tokens_cache_read INT, tokens_cache_write INT, time_created INT, time_updated INT)")
            conn.execute("CREATE TABLE project (id TEXT PRIMARY KEY, name TEXT, worktree TEXT)")
            conn.execute("INSERT INTO session VALUES ('a','p1','','t','ag','{}',1,0,0,0,0,0,1000,NULL)".replace("{}", json.dumps({"providerID":"opencode","id":"m"})))
            conn.execute("INSERT INTO session VALUES ('b','p1','','t','ag','{}',1,0,0,0,0,0,2000,2000)".replace("{}", json.dumps({"providerID":"opencode","id":"m"})))
            conn.commit(); conn.close()
            rows=fetch_sessions(db, 1500, False)
            ids={r["id"] for r in rows}
            self.assertIn("b", ids)  # time_updated 2000 > 1500
            # a has NULL time_updated -> COALESCE uses time_created 1000 -> 1000 >1500 false, not fetched (fix)
            self.assertNotIn("a", ids)

if __name__=="__main__":
    unittest.main()
