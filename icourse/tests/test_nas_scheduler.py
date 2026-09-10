import importlib.util
import tempfile
import unittest
from datetime import datetime
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "nas_scheduler.py"
SPEC = importlib.util.spec_from_file_location("nas_scheduler", SCRIPT)
nas_scheduler = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(nas_scheduler)


class SchedulerTests(unittest.TestCase):
    def test_parse_and_deduplicate_times(self):
        self.assertEqual(
            nas_scheduler.parse_run_times("22:00, 13:00,13:00"),
            [(13, 0), (22, 0)],
        )

    def test_next_run_today_or_tomorrow(self):
        times = [(13, 0), (22, 0)]
        now = datetime.fromisoformat("2026-09-07T14:00:00+08:00")
        self.assertEqual(
            nas_scheduler.next_run(now, times).isoformat(),
            "2026-09-07T22:00:00+08:00",
        )
        late = datetime.fromisoformat("2026-09-07T23:00:00+08:00")
        self.assertEqual(
            nas_scheduler.next_run(late, times).isoformat(),
            "2026-09-08T13:00:00+08:00",
        )

    def test_invalid_time_is_rejected(self):
        with self.assertRaises(ValueError):
            nas_scheduler.parse_run_times("25:00")

    def test_nonblocking_lock_rejects_overlapping_run(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "scheduler.lock")
            with nas_scheduler.exclusive_run_lock(path) as first:
                self.assertTrue(first)
                with nas_scheduler.exclusive_run_lock(path) as second:
                    self.assertFalse(second)


if __name__ == "__main__":
    unittest.main()
