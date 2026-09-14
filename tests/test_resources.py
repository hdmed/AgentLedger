import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import resources


class TestResources(unittest.TestCase):
    def test_default_database_honors_environment(self):
        expected = os.path.join(tempfile.gettempdir(), "custom.db")
        with patch.dict(os.environ, {"OPENCODE_DB": expected}, clear=False):
            self.assertEqual(resources.default_db_path(), os.path.abspath(expected))

    def test_user_override_uses_persistent_paths(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.dict(os.environ, {"AGENTLEDGER_USER_DIR": root}, clear=False):
                self.assertTrue(resources.dataset_path().startswith(root))
                self.assertTrue(resources.state_path().startswith(root))
                self.assertTrue(resources.report_path().startswith(root))
                self.assertTrue(resources.pricing_path().startswith(root))

    def test_legacy_env_still_honored(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.dict(os.environ, {"OPENCOST_USER_DIR": root}, clear=False):
                self.assertTrue(resources.dataset_path().startswith(root))

    def test_frozen_resources_use_meipass(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.object(sys, "frozen", True, create=True), patch.object(sys, "_MEIPASS", root, create=True):
                self.assertEqual(resources.app_root(), root)
                self.assertEqual(resources.resource_path("templates", "report_template.html"), os.path.join(root, "templates", "report_template.html"))

    def test_basename_crossplatform(self):
        self.assertEqual(resources.basename_crossplatform("C:\\Users\\DII\\proj"), "proj")
        self.assertEqual(resources.basename_crossplatform("/tmp/kilo"), "kilo")
        self.assertEqual(resources.basename_crossplatform("prox/"), "prox")
        self.assertEqual(resources.basename_crossplatform(None), "")
        self.assertEqual(resources.basename_crossplatform("D:\\CD\\Models\\AI-Directory"), "AI-Directory")


if __name__ == "__main__":
    unittest.main()
