import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import refresh_and_run
from nas.semester import TargetSemesterPending


class RefreshWrapperTests(unittest.TestCase):
    def test_rust_cli_receives_private_json_credentials_and_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            options = self.options(Path(directory))
            options.config.write_text('canvas_url = "https://canvas.invalid"\n'
                                      'canvas_token = "test-only-token"\n')
            captured = []
            def execute(command, _options):
                self.assertEqual(command[1], "-c")
                path = Path(command[2])
                captured.append(path)
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(json.loads(path.read_text()), {
                    "canvasUrl": "https://canvas.invalid",
                    "canvasToken": "test-only-token"})
                self.assertNotIn("test-only-token", command)
                self.assertEqual(command[-2:], ["-t", "29"])
                return 0
            with patch.object(refresh_and_run, "run_downloader_command", side_effect=execute):
                self.assertEqual(refresh_and_run.run_downloader(options, ["-t", "29"]), 0)
            self.assertFalse(captured[0].exists())

    def test_external_credential_arguments_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for args in (["-c", "old.json"], ["--credential-file=old.json"], ["-cold.json"]):
                with self.assertRaises(ValueError):
                    refresh_and_run.run_downloader(self.options(Path(directory)), args)

    def options(self, root):
        return refresh_and_run.RuntimeOptions(
            config=root / "canvas-downloader.toml",
            binary=root / "canvas-downloader",
            log_file=root / "sync.log",
            update_log_dir=root / "log",
            storage_state=root / ".state" / "browser.json",
            token_purpose="test",
            token_expires_at=None,
            force_refresh_token=False,
            headless=True,
            login_timeout_ms=1000,
            auto_yes=True,
            target_term_name="2026-2027学年第一学期",
            course_manifest=root / ".state" / "2026-fall-courses.json",
            downloader_args=["-n", "-d", "/downloads"],
        )

    def test_pending_semester_never_runs_old_downloader(self):
        with tempfile.TemporaryDirectory() as directory:
            options = self.options(Path(directory))
            app_config = refresh_and_run.AppConfig(
                canvas_url="https://canvas.invalid", canvas_token="secret-token"
            )
            with (
                patch.object(refresh_and_run, "read_app_config", return_value=app_config),
                patch.object(
                    refresh_and_run,
                    "check_canvas_token",
                    return_value=refresh_and_run.TokenState.VALID,
                ),
                patch.object(
                    refresh_and_run,
                    "discover_target_semester",
                    side_effect=TargetSemesterPending("not published"),
                ),
                patch.object(refresh_and_run, "run_downloader") as downloader,
            ):
                self.assertEqual(refresh_and_run.run_once(options), 0)
                downloader.assert_not_called()

    def test_discovered_term_is_injected_once(self):
        with tempfile.TemporaryDirectory() as directory:
            options = self.options(Path(directory))
            app_config = refresh_and_run.AppConfig(
                canvas_url="https://canvas.invalid", canvas_token="secret-token"
            )
            manifest = {
                "term": {"id": 29, "name": options.target_term_name},
                "courses": [{"canvas_id": 1}],
            }
            with (
                patch.object(refresh_and_run, "read_app_config", return_value=app_config),
                patch.object(
                    refresh_and_run,
                    "check_canvas_token",
                    return_value=refresh_and_run.TokenState.VALID,
                ),
                patch.object(
                    refresh_and_run,
                    "discover_target_semester",
                    return_value=("29", manifest),
                ),
                patch.object(refresh_and_run, "run_downloader", return_value=0) as downloader,
            ):
                self.assertEqual(refresh_and_run.run_once(options), 0)
                called_args = downloader.call_args.args[1]
                self.assertEqual(called_args.count("-t"), 1)
                self.assertEqual(called_args[-2:], ["-t", "29"])


if __name__ == "__main__":
    unittest.main()
