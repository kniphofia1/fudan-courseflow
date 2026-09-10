import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import config
from src.config import _read_secret


class ConfigSecretTests(unittest.TestCase):
    def test_docker_secret_takes_precedence_over_legacy_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            secret = Path(directory) / "password"
            secret.write_text("current-password\n", encoding="utf-8")
            with patch.dict(
                os.environ,
                {"UISPSW_FILE": str(secret), "UISPsw": "stale-password"},
                clear=False,
            ):
                self.assertEqual(
                    _read_secret("UISPSW", "UISPsw", file_env="UISPSW_FILE"),
                    "current-password",
                )

    def test_legacy_course_ids_mode_remains_supported(self):
        original = dict(os.environ)
        try:
            with patch.dict(
                os.environ,
                {"COURSE_DISCOVERY_MODE": "explicit", "COURSE_IDS": "12, 34"},
                clear=False,
            ):
                reloaded = importlib.reload(config)
                self.assertEqual(reloaded.COURSE_DISCOVERY_MODE, "explicit")
                self.assertEqual(reloaded.COURSE_IDS, ["12", "34"])
        finally:
            os.environ.clear()
            os.environ.update(original)
            importlib.reload(config)


if __name__ == "__main__":
    unittest.main()
