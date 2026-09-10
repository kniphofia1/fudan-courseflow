import unittest
from src.icourse import ICourseClient, playback_is_released


class Response:
    def raise_for_status(self):
        pass

    def json(self):
        return {"code": 0, "data": {"title": "测试课程", "realname": "教师甲", "sub_list": {
            "2026": {"9": {"2": [
                {"id": "1", "sub_title": "2026-09-07第3-5节", "playback_status": 1},
                {"id": "2", "sub_title": "尚无日期", "playback_status": 0}]}}}}}


class Session:
    def get(self, *args, **kwargs):
        return Response()


class LectureDateTests(unittest.TestCase):
    def test_recorded_but_delayed_release_is_not_playable(self):
        item = {"playback_status": "1", "sub_delayed_release": "200"}
        self.assertFalse(playback_is_released(item, now=199))
        self.assertTrue(playback_is_released(item, now=200))

    def test_closed_or_malformed_recording_is_not_playable(self):
        for item in ({"playback_status": "1", "deadline_at": "100"},
                     {"playback_status": "1", "sub_delayed_release": "unknown"},
                     {"playback_status": "1", "show": "no"},
                     {"playback_status": "0"}):
            self.assertFalse(playback_is_released(item, now=200))

    def test_week_group_is_not_used_as_calendar_day(self):
        lectures = ICourseClient(Session()).get_course_detail("123")["lectures"]
        self.assertEqual(lectures[0]["date"], "2026-09-07")
        self.assertTrue(lectures[0]["has_playback"])
        self.assertEqual(lectures[1]["date"], "")
        self.assertFalse(lectures[1]["has_playback"])
