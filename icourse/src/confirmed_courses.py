"""Explicit user-confirmed iCourse roster, independent of Canvas publication."""
import json
from pathlib import Path

from .course_discovery import CourseDiscoveryError, normalize_text


def load_confirmed_courses(path, term_id, client):
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CourseDiscoveryError("Unable to read confirmed iCourse roster") from exc
    if payload.get("schema_version") != 1 or str(payload.get("term_id")) != str(term_id):
        raise CourseDiscoveryError("Confirmed roster semester does not match configuration")
    courses = payload.get("courses")
    if not isinstance(courses, list) or not courses:
        raise CourseDiscoveryError("Confirmed roster is empty or malformed")
    ids, directories = [], {}
    for course in courses:
        course_id = str(course.get("icourse_id", ""))
        code, title = course.get("course_code", ""), course.get("name", "")
        directory = f"{code} {title}"
        if (not course_id.isdecimal() or not code or not title
                or any(char in directory for char in "/\\\x00")
                or any(ord(char) < 32 for char in directory)
                or course_id in directories):
            raise CourseDiscoveryError("Unsafe or duplicate confirmed course entry")
        detail = client.get_course_detail(course_id)
        if normalize_text(detail.get("title")) != normalize_text(title):
            raise CourseDiscoveryError("Confirmed course title no longer matches its ID")
        teachers = course.get("teachers") or []
        actual = normalize_text(detail.get("teacher"))
        # The API may return only the current lecturer for a co-taught course.
        if not teachers or not any(normalize_text(teacher) and normalize_text(teacher) in actual for teacher in teachers):
            raise CourseDiscoveryError("Confirmed course teacher no longer matches its ID")
        ids.append(course_id)
        directories[course_id] = directory
    return ids, directories
