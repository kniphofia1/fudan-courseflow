import json
import tempfile
import unittest
from pathlib import Path

from src.course_discovery import (
    CourseManifestPending,
    choose_candidate,
    discover_courses,
    extract_chinese_title,
    load_manifest,
)


def canvas_course(course_id="101", teachers=None):
    return {
        "canvas_id": course_id,
        "course_code": "CS20013.01 社会计算导论",
        "name": "CS20013.01 社会计算导论 Introduction to Social Computing",
        "teachers": teachers or ["卢暾"],
        "directory_name": "CS20013.01 社会计算导论",
    }


class FakeClient:
    def __init__(self, candidates, has_playback=True):
        self.candidates = candidates
        self.has_playback = has_playback
        self.searches = 0

    def get_course_list(self, *, term, page, per_page, title):
        self.searches += 1
        return {"total": len(self.candidates), "courses": self.candidates}

    def get_course_detail(self, course_id):
        match = next(item for item in self.candidates if str(item["id"]) == str(course_id))
        return {
            "title": match["title"],
            "teacher": match.get("realname", ""),
            "lectures": [{"sub_id": "1", "has_playback": self.has_playback}],
        }


class CourseDiscoveryTests(unittest.TestCase):
    def test_extracts_chinese_title_from_canvas_code(self):
        self.assertEqual(extract_chinese_title(canvas_course()), "社会计算导论")

    def test_course_code_and_teacher_select_correct_section(self):
        candidates = [
            {
                "id": "1",
                "title": "社会计算导论",
                "course_code": "CS20013.02",
                "realname": "其他教师",
            },
            {
                "id": "2",
                "title": "社会计算导论",
                "course_code": "2026-20271CS20013.01",
                "realname": "卢暾",
            },
        ]
        chosen, matched_by = choose_candidate(canvas_course(), candidates)
        self.assertEqual(chosen["id"], "2")
        self.assertEqual(matched_by, "title+course_code+teacher")

    def test_ambiguous_title_only_match_is_rejected(self):
        chosen, reason = choose_candidate(
            canvas_course(teachers=[]),
            [
                {"id": "1", "title": "社会计算导论"},
                {"id": "2", "title": "社会计算导论"},
            ],
        )
        self.assertIsNone(chosen)
        self.assertIn("ambiguous", reason)

    def test_missing_manifest_is_pending(self):
        with self.assertRaises(CourseManifestPending):
            load_manifest("/definitely/missing/semester-courses.json")

    def test_discovery_writes_cache_and_reuses_unique_mapping(self):
        candidates = [
            {
                "id": "34013",
                "title": "社会计算导论",
                "course_code": "CS20013.01",
                "realname": "卢暾",
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "manifest.json"
            cache = root / "course-map.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "term": {"id": 29, "name": "2026-2027学年第一学期"},
                        "courses": [canvas_course()],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            client = FakeClient(candidates)
            resolved, diagnostics = discover_courses(client, manifest, "27", cache)
            self.assertEqual([item.icourse_id for item in resolved], ["34013"])
            self.assertIn("course_code", diagnostics[0])
            self.assertEqual(cache.stat().st_mode & 0o777, 0o600)

            resolved_again, _ = discover_courses(client, manifest, "27", cache)
            self.assertEqual(resolved_again, resolved)
            self.assertEqual(client.searches, 1)

    def test_course_without_playable_recording_is_skipped(self):
        candidates = [
            {
                "id": "34013",
                "title": "社会计算导论",
                "course_code": "CS20013.01",
                "realname": "卢暾",
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "manifest.json"
            cache = root / "course-map.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "term": {"id": 29, "name": "2026-2027学年第一学期"},
                        "courses": [canvas_course()],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            resolved, diagnostics = discover_courses(
                FakeClient(candidates, has_playback=False), manifest, "27", cache
            )
            self.assertEqual(resolved, [])
            self.assertIn("no playable recordings", diagnostics[0])


if __name__ == "__main__":
    unittest.main()
