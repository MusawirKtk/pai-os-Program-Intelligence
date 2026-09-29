"""The migration runner reads only the plugin's own database setting."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

import smoke_m4


class SmokeM4Tests(unittest.TestCase):
    def test_no_database_action_without_apply_flag(self):
        with patch("sys.argv", ["smoke_m4.py"]), patch.object(smoke_m4, "connect_database") as connect:
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                smoke_m4.main()
            connect.assert_not_called()

    def test_reads_plugin_repo_env_without_using_generic_database_url(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("PROGRAM_INTELLIGENCE_DATABASE_URL=postgresql://plugin-only\n", encoding="utf-8")
            with patch.object(smoke_m4, "REPO_ROOT", root), patch.dict(os.environ, {"DATABASE_URL": "postgresql://host-only"}, clear=True):
                self.assertEqual(smoke_m4._local_database_url(), "postgresql://plugin-only")

    def test_process_setting_takes_precedence(self):
        with patch.dict(os.environ, {"PROGRAM_INTELLIGENCE_DATABASE_URL": "postgresql://process-only"}, clear=True):
            self.assertEqual(smoke_m4._local_database_url(), "postgresql://process-only")


if __name__ == "__main__":
    unittest.main()
