"""Discover a Canvas semester and produce a credential-free course manifest.

The NAS refresh wrapper calls :func:`discover_target_semester` immediately
after it creates and validates a short-lived Canvas access token.  Keeping the
term selection here prevents a stale hard-coded term ID from downloading an
older semester.
"""

from __future__ import annotations

import json
import os
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence


class SemesterDiscoveryError(RuntimeError):
    """Base class for semester discovery failures."""


class TargetSemesterPending(SemesterDiscoveryError):
    """The requested semester has not been published to this account yet."""


class AmbiguousTargetSemester(SemesterDiscoveryError):
    """More than one Canvas term ID has the requested display name."""


class CanvasAPIError(SemesterDiscoveryError):
    """Canvas returned an error or a malformed response."""


def normalize_text(value: object) -> str:
    """Normalize display text for exact, whitespace-insensitive matching."""

    text = unicodedata.normalize("NFKC", str(value or ""))
    return "".join(text.split()).casefold()


def course_directory_name(course: dict[str, Any]) -> str:
    """Return the directory name used by the Rust downloader."""

    value = course.get("course_code") or course.get("name") or course.get("id")
    return str(value).replace("/", "_").replace("\x00", "").strip()


def select_target_courses(
    courses: Iterable[dict[str, Any]], target_term_name: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Select all courses for one uniquely named term.

    Missing terms are a normal pending state.  Duplicate names with different
    IDs are rejected so the caller never silently chooses the wrong semester.
    """

    wanted = normalize_text(target_term_name)
    matching: list[dict[str, Any]] = []
    terms: dict[str, dict[str, Any]] = {}
    for course in courses:
        term = course.get("term") or {}
        if normalize_text(term.get("name")) != wanted:
            continue
        term_id = str(term.get("id") or "")
        if not term_id:
            continue
        terms[term_id] = {"id": term.get("id"), "name": term.get("name")}
        matching.append(course)

    if not terms:
        raise TargetSemesterPending(
            f"Canvas term {target_term_name!r} is not available yet"
        )
    if len(terms) != 1:
        raise AmbiguousTargetSemester(
            f"Canvas term {target_term_name!r} maps to IDs {sorted(terms)}"
        )

    term = next(iter(terms.values()))
    selected = [
        course
        for course in matching
        if str((course.get("term") or {}).get("id")) == str(term["id"])
    ]
    selected.sort(
        key=lambda item: (
            normalize_text(item.get("course_code")),
            normalize_text(item.get("name")),
            str(item.get("id") or ""),
        )
    )
    return term, selected


class CanvasAPI:
    """Small read-only Canvas API client used during scheduled discovery."""

    def __init__(
        self,
        canvas_url: str,
        token: str,
        *,
        timeout: int = 30,
        opener: Callable[..., Any] | None = None,
    ):
        self.canvas_url = canvas_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._opener = opener or urllib.request.urlopen

    def _get_page(
        self, path: str, params: Sequence[tuple[str, object]], page: int
    ) -> list[dict[str, Any]]:
        query = [(key, str(value)) for key, value in params]
        query.extend((("per_page", "100"), ("page", str(page))))
        url = f"{self.canvas_url}{path}?{urllib.parse.urlencode(query)}"
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "User-Agent": "fudan-canvas-nas/2026-fall",
            },
        )
        try:
            with self._opener(request, timeout=self.timeout) as response:
                payload = json.load(response)
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise CanvasAPIError(f"Canvas GET {path} failed: {exc}") from exc
        if not isinstance(payload, list):
            raise CanvasAPIError(f"Canvas GET {path} returned a non-list payload")
        return payload

    def _get_all(
        self, path: str, params: Sequence[tuple[str, object]]
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for page in range(1, 101):
            batch = self._get_page(path, params, page)
            rows.extend(batch)
            if len(batch) < 100:
                return rows
        raise CanvasAPIError(f"Canvas GET {path} exceeded 100 pages")

    def list_available_courses(self) -> list[dict[str, Any]]:
        return self._get_all(
            "/api/v1/courses",
            (
                ("enrollment_state", "active"),
                ("state[]", "available"),
                ("include[]", "term"),
            ),
        )

    def list_teachers(self, course_id: object) -> list[str]:
        rows = self._get_all(
            f"/api/v1/courses/{urllib.parse.quote(str(course_id), safe='')}/users",
            (("enrollment_type[]", "teacher"),),
        )
        names = {
            str(row.get("sortable_name") or row.get("name") or "").strip()
            for row in rows
        }
        return sorted(name for name in names if name)


def build_manifest(
    term: dict[str, Any],
    courses: Iterable[dict[str, Any]],
    teacher_lookup: Callable[[object], list[str]],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build the stable, secret-free handoff manifest for iCourse."""

    entries = []
    for course in courses:
        course_id = course.get("id")
        entries.append(
            {
                "canvas_id": course_id,
                "course_code": str(course.get("course_code") or "").strip(),
                "name": str(course.get("name") or "").strip(),
                "teachers": teacher_lookup(course_id),
                "directory_name": course_directory_name(course),
            }
        )
    return {
        "schema_version": 1,
        "generated_at": generated_at
        or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "term": {"id": term.get("id"), "name": term.get("name")},
        "courses": entries,
    }


def write_manifest_atomic(path: str | os.PathLike[str], manifest: dict[str, Any]) -> None:
    """Atomically write a manifest with owner-only permissions."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(destination.parent, 0o700)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def discover_target_semester(
    canvas_url: str,
    token: str,
    target_term_name: str,
    manifest_path: str | os.PathLike[str],
    *,
    api: CanvasAPI | None = None,
) -> tuple[str, dict[str, Any]]:
    """Resolve a term, fetch teachers, persist the manifest, and return its ID."""

    client = api or CanvasAPI(canvas_url, token)
    term, courses = select_target_courses(
        client.list_available_courses(), target_term_name
    )
    manifest = build_manifest(term, courses, client.list_teachers)
    write_manifest_atomic(manifest_path, manifest)
    return str(term["id"]), manifest


def inject_term_id(args: Sequence[str], term_id: object) -> list[str]:
    """Append one discovered term ID, rejecting any explicit stale selector."""

    for argument in args:
        if argument in {"-t", "--term-ids"} or argument.startswith("--term-ids="):
            raise ValueError(
                "explicit Canvas term IDs are forbidden when automatic term discovery is enabled"
            )
    return [*args, "-t", str(term_id)]
