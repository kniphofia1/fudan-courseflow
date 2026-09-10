import json
import tempfile
import unittest
from pathlib import Path

from nas.semester import (
    AmbiguousTargetSemester,
    TargetSemesterPending,
    build_manifest,
    course_directory_name,
    inject_term_id,
    select_target_courses,
    write_manifest_atomic,
)


TARGET = "2026-2027学年第一学期"


def course(course_id, term_id, term_name=TARGET, code="CS100.01 测试课程"):
    return {
        "id": course_id,
        "course_code": code,
        "name": f"{code} Test Course",
        "term": {"id": term_id, "name": term_name},
    }


class SemesterTests(unittest.TestCase):
    def test_selects_every_course_in_the_unique_target_term(self):
        term, selected = select_target_courses(
            [course(2, 29), course(1, 29), course(3, 28, "旧学期")], TARGET
        )
        self.assertEqual(term, {"id": 29, "name": TARGET})
        self.assertEqual([item["id"] for item in selected], [1, 2])

    def test_missing_term_is_pending(self):
        with self.assertRaises(TargetSemesterPending):
            select_target_courses([course(1, 28, "旧学期")], TARGET)

    def test_duplicate_term_name_is_rejected(self):
        with self.assertRaises(AmbiguousTargetSemester):
            select_target_courses([course(1, 29), course(2, 30)], TARGET)

    def test_directory_name_matches_downloader_slash_replacement(self):
        self.assertEqual(
            course_directory_name({"course_code": "CS/101.01 测试"}),
            "CS_101.01 测试",
        )

    def test_manifest_has_no_credentials_and_is_owner_only(self):
        term = {"id": 29, "name": TARGET}
        manifest = build_manifest(
            term,
            [course(1, 29)],
            lambda _: ["教师甲"],
            generated_at="2026-09-07T00:00:00+00:00",
        )
        self.assertNotIn("token", json.dumps(manifest).lower())
        self.assertEqual(manifest["courses"][0]["teachers"], ["教师甲"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state" / "courses.json"
            write_manifest_atomic(path, manifest)
            self.assertEqual(json.loads(path.read_text()), manifest)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_injects_discovered_term_and_rejects_explicit_term(self):
        self.assertEqual(
            inject_term_id(["-n", "-d", "/downloads"], 29),
            ["-n", "-d", "/downloads", "-t", "29"],
        )
        for args in (["-t", "28"], ["--term-ids", "28"], ["--term-ids=28"]):
            with self.assertRaises(ValueError):
                inject_term_id(args, 29)


if __name__ == "__main__":
    unittest.main()
