import unittest
from types import SimpleNamespace
from unittest.mock import patch
import main
from src.course_discovery import CourseManifestPending


class ConfirmedSelectionTests(unittest.TestCase):
    def test_pending_canvas_uses_confirmed_roster(self):
        with (patch.object(main.config, "COURSE_DISCOVERY_MODE", "manifest"),
              patch.object(main.config, "CONFIRMED_COURSES_PATH", "/confirmed.json"),
              patch.object(main, "discover_courses", side_effect=CourseManifestPending()),
              patch.object(main, "load_confirmed_courses", return_value=(["1"], {"1": "A 课程"}))):
            self.assertEqual(main.resolve_course_selection(None), (["1"], {"1": "A 课程"}))

    def test_partial_canvas_does_not_drop_confirmed_courses_or_duplicate_ids(self):
        with (patch.object(main.config, "COURSE_DISCOVERY_MODE", "manifest"),
              patch.object(main.config, "CONFIRMED_COURSES_PATH", "/confirmed.json"),
              patch.object(main, "discover_courses", return_value=([SimpleNamespace(icourse_id="1", directory_name="A 课程")], [])),
              patch.object(main, "load_confirmed_courses", return_value=(["1", "2"], {"1": "A 课程", "2": "B 课程"}))):
            self.assertEqual(main.resolve_course_selection(None), (["1", "2"], {"1": "A 课程", "2": "B 课程"}))
