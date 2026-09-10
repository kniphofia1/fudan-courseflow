import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DeploymentTests(unittest.TestCase):
    def test_init_is_private_and_never_overwrites(self):
        module = load_script("init_local")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env.example").write_text((ROOT / ".env.example").read_text())
            old_mask = os.umask(0o077)
            try:
                module.initialize(root, "2026-fall")
                env = root / ".env"
                self.assertEqual(env.stat().st_mode & 0o777, 0o600)
                env.write_text("custom\n")
                module.initialize(root, "2026-fall")
                self.assertEqual(env.read_text(), "custom\n")
                self.assertTrue((root / ".runtime/canvas/2026-fall/.state").is_dir())
            finally:
                os.umask(old_mask)

    def test_invalid_semester_cannot_escape_runtime(self):
        module = load_script("init_local")
        with self.assertRaises(ValueError):
            module.initialize(ROOT, "../../escape")

    def test_canvas_retries_and_forces_token_refresh(self):
        module = load_script("canvas_run")
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(module, "Path", return_value=Path(directory) / "lock"), \
             patch.object(module.subprocess, "run") as run, \
             patch.object(module.time, "sleep") as sleep:
            old_mask = os.umask(0o077)
            try:
                run.return_value.returncode = 2
                self.assertEqual(module.main(), 2)
                self.assertEqual(run.call_count, 3)
                self.assertEqual(sleep.call_count, 2)
                self.assertIn("--force-refresh-token", run.call_args.args[0])
                run.reset_mock()
                run.return_value.returncode = 0
                self.assertEqual(module.main(), 0)
                run.assert_called_once()
            finally:
                os.umask(old_mask)

    def test_canvas_does_not_run_when_lock_is_busy(self):
        module = load_script("canvas_run")
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(module, "Path", return_value=Path(directory) / "lock"), \
             patch.object(module.fcntl, "flock", side_effect=BlockingIOError), \
             patch.object(module.subprocess, "run") as run:
            old_mask = os.umask(0o077)
            try:
                self.assertEqual(module.main(), 0)
                run.assert_not_called()
            finally:
                os.umask(old_mask)


if __name__ == "__main__":
    unittest.main()
