"""Export processed lecture summaries and transcripts as Markdown."""

from __future__ import annotations

import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from . import config


def safe_filename(value: object, fallback: str = "item", max_length: int = 100) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    text = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return (text or fallback)[:max_length].rstrip(" .")


def _match_key(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(char for char in text if char.isalnum())


def _front_matter(value: object) -> str:
    return str(value or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


class MarkdownExporter:
    def __init__(
        self,
        output_dir: str | os.PathLike[str] | None = None,
        include_transcript: bool | None = None,
        use_existing_course_dirs: bool | None = None,
        course_subdir: str | None = None,
        course_directory_map: dict[str, str] | None = None,
    ):
        self.output_dir = Path(output_dir or config.EXPORT_DIR)
        self.include_transcript = (
            config.EXPORT_TRANSCRIPT if include_transcript is None else include_transcript
        )
        self.use_existing_course_dirs = (
            config.EXPORT_USE_EXISTING_COURSE_DIRS
            if use_existing_course_dirs is None
            else use_existing_course_dirs
        )
        self.course_subdir = (
            config.EXPORT_COURSE_SUBDIR if course_subdir is None else course_subdir
        )
        self.course_directory_map = {
            str(key): value for key, value in (course_directory_map or {}).items()
        }

    def export_item(self, item: dict) -> str:
        course_id = str(item.get("course_id") or "")
        sub_id = str(item.get("sub_id") or "")
        course_title = item.get("course_title") or item.get("title") or course_id
        course_dir = self._resolve_course_dir(course_title, course_id)
        course_dir.mkdir(parents=True, exist_ok=True)
        filename = "{}_{}_{}.md".format(
            safe_filename(item.get("date"), "unknown-date", 32),
            safe_filename(sub_id, "unknown", 32),
            safe_filename(item.get("sub_title"), "lecture", 80),
        )
        path = course_dir / filename
        path.write_text(self._build_markdown(item), encoding="utf-8")
        self._write_index(course_dir, course_title, course_id, item.get("teacher") or "")
        return str(path)

    def _resolve_course_dir(self, course_title: str, course_id: str) -> Path:
        mapped = self.course_directory_map.get(str(course_id))
        if mapped:
            base_dir = self.output_dir / safe_filename(mapped, "course", 120)
        elif self.use_existing_course_dirs:
            base_dir = self._find_existing_course_dir(course_title, course_id)
            if base_dir is None:
                base_dir = self.output_dir / self._course_dir_name(course_title, course_id)
        else:
            base_dir = self.output_dir / self._course_dir_name(course_title, course_id)
        subdir = safe_filename(self.course_subdir, fallback="", max_length=60)
        return base_dir / subdir if subdir else base_dir

    def _find_existing_course_dir(self, course_title: str, course_id: str) -> Path | None:
        if not self.output_dir.is_dir():
            return None
        title_key = _match_key(course_title)
        course_id_key = _match_key(course_id)
        matches: list[tuple[int, str, Path]] = []
        for path in self.output_dir.iterdir():
            if not path.is_dir() or path.name.startswith(".") or path.name == "raw":
                continue
            folder_key = _match_key(path.name)
            score = 0
            if title_key and folder_key == title_key:
                score = 100
            elif title_key and title_key in folder_key:
                score = 90
            elif course_id_key and course_id_key in folder_key:
                score = 80
            elif title_key and folder_key in title_key:
                score = 50
            if score:
                matches.append((score, path.name, path))
        return max(matches)[2] if matches else None

    @staticmethod
    def _course_dir_name(course_title: str, course_id: str) -> str:
        return f"{safe_filename(course_title, 'course', 80)}-{safe_filename(course_id, 'unknown', 32)}"

    def _build_markdown(self, item: dict) -> str:
        lines = [
            "---",
            f'title: "{_front_matter(item.get("sub_title") or item.get("sub_id"))}"',
            f'course: "{_front_matter(item.get("course_title"))}"',
            f'course_id: "{_front_matter(item.get("course_id"))}"',
            f'lecture_id: "{_front_matter(item.get("sub_id"))}"',
            f'date: "{_front_matter(item.get("date"))}"',
            f'teacher: "{_front_matter(item.get("teacher"))}"',
            f'summary_model: "{_front_matter(item.get("summary_model"))}"',
            f'exported_at: "{datetime.now().isoformat(timespec="seconds")}"',
            "---",
            "",
            f'# {item.get("sub_title") or item.get("sub_id")}',
            "",
            "## AI 摘要",
            "",
            str(item.get("summary") or "").strip(),
        ]
        if self.include_transcript:
            lines.extend(
                ["", "## 完整转写", "", str(item.get("transcript") or "").strip()]
            )
        lines.append("")
        return "\n".join(lines)

    def _write_index(self, course_dir: Path, course_title: str, course_id: str, teacher: str) -> None:
        files = sorted(path.name for path in course_dir.glob("*.md") if path.name != "README.md")
        lines = [
            f"# {course_title} · 录课转写",
            "",
            f"- 课程 ID：{course_id}",
            f"- 教师：{teacher}",
            f"- 已导出课次：{len(files)}",
            "",
            "## 课次",
            "",
        ]
        lines.extend(f"- [{name}]({name})" for name in files)
        lines.append("")
        (course_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
