"""Offline integration against the exact Rust binary, without real courses."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


@unittest.skipUnless(os.getenv("CANVAS_TEST_BINARY"), "Set CANVAS_TEST_BINARY to built Rust binary")
class BinaryIntegrationTests(unittest.TestCase):
    def test_future_term_download_then_idempotent_second_run(self):
        requests_seen = []
        contents = b"fixture-only course material\n"
        term = {"id": 29, "name": "2026-2027学年第一学期"}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                path = urlsplit(self.path).path
                requests_seen.append(path)
                base = "http://127.0.0.1:" + str(self.server.server_port)
                routes = {
                    "/api/v1/users/self": {"id": 1},
                    "/api/v1/courses": [
                        {"id": 101, "name": "测试课程", "course_code": "CS99999.01 测试课程",
                         "term": term, "enrollment_term_id": 29, "enrollments": []},
                        {"id": 99, "name": "旧课程", "course_code": "OLD 旧课程",
                         "term": {"id": 28, "name": "旧学期"}, "enrollment_term_id": 28, "enrollments": []},
                    ],
                    "/api/v1/courses/101/users": [{"name": "教师甲"}],
                    "/api/v1/courses/101/folders/by_path/": [
                        {"id": 1, "name": "course files", "parent_folder_id": None,
                         "files_url": base + "/empty", "folders_url": base + "/folders",
                         "for_submissions": False, "can_upload": False}],
                    "/folders": [{"id": 2, "name": "讲义", "parent_folder_id": 1,
                                  "files_url": base + "/files", "folders_url": base + "/empty",
                                  "for_submissions": False, "can_upload": False}],
                    "/empty": [],
                    "/files": [{"id": 1, "folder_id": 2, "display_name": "第一讲.txt",
                                "size": len(contents), "url": base + "/material",
                                "updated_at": "2026-09-01T00:00:00Z", "locked_for_user": False}],
                }
                payload = contents if path == "/material" else json.dumps(routes.get(path), ensure_ascii=False).encode()
                self.send_response(200 if path in routes or path == "/material" else 404)
                self.send_header("Content-Type", "application/json" if path != "/material" else "text/plain")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config = root / "config.toml"
                config.write_text(f'canvas_url = "http://127.0.0.1:{server.server_port}"\ncanvas_token = "fixture-token"\n')
                manifest = root / "state" / "courses.json"
                output = root / "downloads"
                command = [sys.executable, str(Path(__file__).resolve().parents[1] / "refresh_and_run.py"),
                           "--config", str(config), "--binary", os.environ["CANVAS_TEST_BINARY"],
                           "--target-term-name", term["name"], "--course-manifest", str(manifest),
                           "--log-file", str(root / "sync.log"), "--update-log-dir", str(root / "log"),
                           "--", "-n", "-d", str(output)]
                for _ in range(2):
                    result = subprocess.run(command, capture_output=True, text=True, timeout=30,
                                            env={**os.environ, "CANVAS_DOWNLOADER_AUTO_YES": "true", "NO_PROXY": "127.0.0.1,localhost"})
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                data = json.loads(manifest.read_text())
                self.assertEqual(data["term"], term)
                self.assertEqual(len(data["courses"]), 1)
                course_directory = data["courses"][0]["directory_name"]
                self.assertEqual((output / course_directory / "讲义" / "第一讲.txt").read_bytes(), contents)
                self.assertEqual(requests_seen.count("/material"), 1)
                self.assertFalse(any("/courses/99/" in path for path in requests_seen))
                self.assertEqual(len(list(output.iterdir())), 1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
