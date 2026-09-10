import json
import tempfile
import unittest
from pathlib import Path
from src.confirmed_courses import load_confirmed_courses
from src.course_discovery import CourseDiscoveryError


class Client:
    def get_course_detail(self, course_id):
        return {"title": "测试课程", "teacher": "教师甲,教师乙", "lectures": []}


class ConfirmedCoursesTests(unittest.TestCase):
    def run_roster(self, course=None, term="27"):
        course = course or {"icourse_id": "123", "course_code": "CS99999.01",
                            "name": "测试课程", "teachers": ["教师甲", "教师乙"]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "confirmed.json"
            path.write_text(json.dumps({"schema_version": 1, "term_id": term, "courses": [course]}))
            return load_confirmed_courses(path, "27", Client())

    def test_confirmed_ids_work_before_recordings_are_published(self):
        self.assertEqual(self.run_roster(), (["123"], {"123": "CS99999.01 测试课程"}))

    def test_wrong_semester_is_rejected(self):
        with self.assertRaises(CourseDiscoveryError):
            self.run_roster(term="24")

    def test_wrong_identity_and_unsafe_paths_are_rejected(self):
        for update in ({"name": "其他课程"}, {"teachers": ["其他教师"]}, {"course_code": "../"}):
            course = {"icourse_id": "123", "course_code": "CS99999.01",
                      "name": "测试课程", "teachers": ["教师甲"], **update}
            with self.assertRaises(CourseDiscoveryError):
                self.run_roster(course)
