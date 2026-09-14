import unittest
import os
import sqlite3
import json
import shutil
import tempfile
import subprocess
import sys
from datetime import datetime, timezone

class TestIntegration(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_opencode.db")
        self.dataset_path = os.path.join(self.test_dir, "test_dataset.json")
        self.report_path = os.path.join(self.test_dir, "test_report.html")

        # Create dummy database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE project (id TEXT PRIMARY KEY, name TEXT, worktree TEXT)")
        cursor.execute("CREATE TABLE session (id TEXT PRIMARY KEY, project_id TEXT, directory TEXT, title TEXT, agent TEXT, model TEXT, cost REAL, tokens_input INTEGER, tokens_output INTEGER, tokens_reasoning INTEGER, tokens_cache_read INTEGER, tokens_cache_write INTEGER, time_created INTEGER, time_updated INTEGER)")

        cursor.execute("INSERT INTO project VALUES ('p1', 'Test Project', '/tmp/test')")
        cursor.execute("INSERT INTO session VALUES ('s1', 'p1', '/tmp/test', 'Test Session', 'Claude', 'provider/model', 0.1, 100, 200, 50, 10, 5, 1700000000, 1700000000)")

        conn.commit()
        conn.close()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_full_pipeline(self):
        # 1. Run extract.py
        extract_cmd = [
            sys.executable, "extract.py",
            "--db", self.db_path,
            "--full",
            "--out-dataset", self.dataset_path
        ]
        result = subprocess.run(extract_cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"extract.py failed: {result.stderr}")
        self.assertTrue(os.path.exists(self.dataset_path), "dataset.json was not created")

        with open(self.dataset_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertTrue(len(data["sessions"]) > 0, "No sessions extracted")
            self.assertEqual(data["sessions"][0]["id"], "s1")
            self.assertEqual(data["sessions"][0]["project_name"], "Test Project")

        # 2. Run build_report.py
        build_cmd = [
            sys.executable, "build_report.py",
            "--dataset", self.dataset_path,
            "--out", self.report_path
        ]
        result = subprocess.run(build_cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"build_report.py failed: {result.stderr}")
        self.assertTrue(os.path.exists(self.report_path), "report.html was not created")

        with open(self.report_path, "r", encoding="utf-8") as f:
            html = f.read()
            self.assertIn("AgentLedger", html)
            self.assertIn("Test Session", html)

if __name__ == "__main__":
    unittest.main()
