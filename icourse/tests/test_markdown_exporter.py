import tempfile
import unittest
from pathlib import Path

from src.markdown_exporter import MarkdownExporter


class MarkdownExporterTests(unittest.TestCase):
    def test_manifest_mapping_places_full_transcript_beside_canvas_materials(self):
        with tempfile.TemporaryDirectory() as directory:
            exporter = MarkdownExporter(
                output_dir=directory,
                include_transcript=True,
                course_subdir="录课转写",
                course_directory_map={"40001": "CS99999.01 测试课程"},
            )
            path = Path(
                exporter.export_item(
                    {
                        "sub_id": "88",
                        "course_id": "40001",
                        "course_title": "测试课程",
                        "teacher": "教师甲",
                        "sub_title": "第一讲",
                        "date": "2026-09-07",
                        "summary": "摘要内容",
                        "transcript": "完整转写内容",
                        "summary_model": "test-model",
                    }
                )
            )
            self.assertEqual(
                path.parent,
                Path(directory) / "CS99999.01 测试课程" / "录课转写",
            )
            text = path.read_text(encoding="utf-8")
            self.assertIn("## AI 摘要", text)
            self.assertIn("## 完整转写", text)
            self.assertIn("完整转写内容", text)
            self.assertTrue((path.parent / "README.md").is_file())


if __name__ == "__main__":
    unittest.main()
