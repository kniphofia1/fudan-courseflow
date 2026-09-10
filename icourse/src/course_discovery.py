"""Resolve iCourse IDs from the credential-free Canvas course manifest."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


class CourseDiscoveryError(RuntimeError):
    """Base class for automatic course selection errors."""


class CourseManifestPending(CourseDiscoveryError):
    """Canvas has not published the target semester manifest yet."""


@dataclass(frozen=True)
class ResolvedCourse:
    canvas_id: str
    course_code: str
    canvas_name: str
    directory_name: str
    icourse_id: str
    icourse_title: str
    icourse_teacher: str
    matched_by: str


CODE_PATTERN = re.compile(
    r"(?<![A-Z])[A-Z]{2,}\d{4,}(?:\.\d+)?(?!\d)", re.IGNORECASE
)
CODE_KEYS = (
    "course_code",
    "course_no",
    "course_number",
    "code",
    "number",
    "kch",
    "kkh",
    "xkkh",
)
TEACHER_KEYS = ("realname", "teacher", "teacher_name", "lecturer_name")


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(char for char in text if char.isalnum())


def normalize_person(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(char for char in text if char.isalnum())


def extract_course_code(course: dict[str, Any]) -> str:
    for value in (course.get("course_code"), course.get("name")):
        match = CODE_PATTERN.search(str(value or ""))
        if match:
            return match.group(0).upper()
    return ""


def extract_chinese_title(course: dict[str, Any]) -> str:
    """Prefer the Chinese title embedded in Canvas's course_code field."""

    values = (course.get("course_code"), course.get("name"))
    for value in values:
        text = unicodedata.normalize("NFKC", str(value or "")).strip()
        text = CODE_PATTERN.sub("", text, count=1).strip(" -—_:：")
        if any("\u3400" <= char <= "\u9fff" for char in text):
            match = re.match(r"[\u3400-\u9fffA-Za-z0-9（）()·—：:、与和ⅠⅡⅢⅣⅤⅥ\s]+", text)
            return (match.group(0) if match else text).strip(" -—_:：")
    return str(course.get("name") or course.get("course_code") or "").strip()


def _candidate_values(candidate: dict[str, Any], keys: Iterable[str]) -> list[str]:
    values: list[str] = []
    for key in keys:
        value = candidate.get(key)
        if isinstance(value, list):
            values.extend(str(item) for item in value if item)
        elif value:
            values.append(str(value))
    return values


def _candidate_id(candidate: dict[str, Any]) -> str:
    return str(candidate.get("id") or candidate.get("course_id") or "")


def choose_candidate(
    canvas_course: dict[str, Any], candidates: Iterable[dict[str, Any]]
) -> tuple[dict[str, Any] | None, str]:
    """Choose only a unique, corroborated iCourse catalog candidate."""

    title = extract_chinese_title(canvas_course)
    title_key = normalize_text(title)
    canvas_code = extract_course_code(canvas_course)
    canvas_teachers = {
        normalize_person(name) for name in canvas_course.get("teachers", []) if name
    }
    scored: list[tuple[int, dict[str, Any], str]] = []

    for candidate in candidates:
        if not _candidate_id(candidate):
            continue
        candidate_title = candidate.get("title") or candidate.get("course_title")
        if normalize_text(candidate_title) != title_key:
            continue

        candidate_codes = {
            match.group(0).upper()
            for value in _candidate_values(candidate, CODE_KEYS)
            for match in CODE_PATTERN.finditer(value)
        }
        candidate_teachers = {
            normalize_person(value)
            for value in _candidate_values(candidate, TEACHER_KEYS)
            if value
        }
        code_match = bool(canvas_code and canvas_code in candidate_codes)
        teacher_match = bool(canvas_teachers & candidate_teachers)
        score = 10 + (100 if code_match else 0) + (30 if teacher_match else 0)
        reasons = ["title"]
        if code_match:
            reasons.append("course_code")
        if teacher_match:
            reasons.append("teacher")
        scored.append((score, candidate, "+".join(reasons)))

    if not scored:
        return None, "no exact title match"

    top_score = max(item[0] for item in scored)
    leaders = [item for item in scored if item[0] == top_score]
    if len(leaders) != 1:
        return None, f"ambiguous: {len(leaders)} candidates share score {top_score}"
    if len(scored) > 1 and top_score == 10:
        return None, f"ambiguous: {len(scored)} title-only candidates"
    return leaders[0][1], leaders[0][2]


def load_manifest(path: str | os.PathLike[str]) -> dict[str, Any]:
    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise CourseManifestPending(f"Canvas manifest not available: {manifest_path}")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CourseDiscoveryError(f"Unable to read Canvas manifest: {exc}") from exc
    if payload.get("schema_version") != 1 or not isinstance(payload.get("courses"), list):
        raise CourseDiscoveryError("Unsupported or malformed Canvas manifest")
    return payload


def _manifest_fingerprint(manifest: dict[str, Any]) -> str:
    stable = json.dumps(
        {"term": manifest.get("term"), "courses": manifest.get("courses")},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(stable.encode()).hexdigest()


def _read_cache(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if payload.get("schema_version") == 1 else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _catalog_candidates(client: Any, term_id: str, title: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 1
    while page <= 100:
        result = client.get_course_list(
            term=term_id, page=page, per_page=100, title=title
        )
        batch = result.get("courses") or []
        rows.extend(batch)
        total = int(result.get("total") or len(rows))
        if not batch or len(rows) >= total:
            return rows
        page += 1
    raise CourseDiscoveryError(f"iCourse search for {title!r} exceeded 100 pages")


def discover_courses(
    client: Any,
    manifest_path: str | os.PathLike[str],
    term_id: str,
    cache_path: str | os.PathLike[str],
) -> tuple[list[ResolvedCourse], list[str]]:
    """Resolve every safe manifest match and persist a non-secret mapping cache."""

    if not term_id:
        raise CourseDiscoveryError("ICOURSE_TERM_ID is required in manifest mode")
    manifest = load_manifest(manifest_path)
    fingerprint = _manifest_fingerprint(manifest)
    cache_file = Path(cache_path)
    cache = _read_cache(cache_file)
    cached_by_canvas = {
        str(item.get("canvas_id")): item
        for item in cache.get("resolved", [])
        if cache.get("manifest_fingerprint") == fingerprint
        and str(cache.get("term_id")) == str(term_id)
    }

    resolved: list[ResolvedCourse] = []
    diagnostics: list[str] = []
    for canvas_course in manifest["courses"]:
        canvas_id = str(canvas_course.get("canvas_id") or "")
        cached = cached_by_canvas.get(canvas_id)
        if cached:
            resolved.append(ResolvedCourse(**cached))
            diagnostics.append(
                f"{canvas_course.get('course_code') or canvas_course.get('name')}: cached"
            )
            continue

        title = extract_chinese_title(canvas_course)
        candidates = _catalog_candidates(client, term_id, title)
        candidate, matched_by = choose_candidate(canvas_course, candidates)
        label = canvas_course.get("course_code") or canvas_course.get("name") or canvas_id
        if candidate is None:
            diagnostics.append(f"{label}: skipped ({matched_by})")
            continue

        detail = client.get_course_detail(_candidate_id(candidate))
        lectures = detail.get("lectures") or []
        if not any(lecture.get("has_playback") for lecture in lectures):
            diagnostics.append(f"{label}: skipped (no playable recordings)")
            continue
        item = ResolvedCourse(
            canvas_id=canvas_id,
            course_code=str(canvas_course.get("course_code") or ""),
            canvas_name=str(canvas_course.get("name") or ""),
            directory_name=str(canvas_course.get("directory_name") or label),
            icourse_id=_candidate_id(candidate),
            icourse_title=str(detail.get("title") or candidate.get("title") or title),
            icourse_teacher=str(
                detail.get("teacher")
                or next(iter(_candidate_values(candidate, TEACHER_KEYS)), "")
            ),
            matched_by=matched_by,
        )
        resolved.append(item)
        diagnostics.append(f"{label}: {item.icourse_id} ({matched_by})")

    resolved.sort(key=lambda item: (item.course_code, item.canvas_id))
    _write_json_atomic(
        cache_file,
        {
            "schema_version": 1,
            "manifest_fingerprint": fingerprint,
            "term_id": str(term_id),
            "resolved": [asdict(item) for item in resolved],
            "diagnostics": diagnostics,
        },
    )
    return resolved, diagnostics
