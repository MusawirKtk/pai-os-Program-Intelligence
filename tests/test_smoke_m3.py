"""The live runner must resolve credentials only from the plugin setup."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import smoke_m3


class LocalKeyTests(unittest.TestCase):
    def test_reads_only_explicit_plugin_repo_env_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("TAVILY_API_KEY=dummy-plugin-key\n", encoding="utf-8")
            with patch.object(smoke_m3, "REPO_ROOT", root), patch.dict(os.environ, {}, clear=True):
                self.assertEqual(smoke_m3._local_key(), "dummy-plugin-key")

    def test_process_environment_takes_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("TAVILY_API_KEY=dummy-file-key\n", encoding="utf-8")
            with patch.object(smoke_m3, "REPO_ROOT", root), patch.dict(os.environ, {"TAVILY_API_KEY": "dummy-process-key"}, clear=True):
                self.assertEqual(smoke_m3._local_key(), "dummy-process-key")

    def test_expected_name_rejects_wrong_program(self):
        self.assertTrue(smoke_m3._name_matches("MSc Statistics - University of Manchester", "MSc Statistics"))
        self.assertFalse(smoke_m3._name_matches("MSc Statistics", "MSc Artificial Intelligence"))


if __name__ == "__main__":
    unittest.main()
