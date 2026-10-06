"""test_links.py — unit tests of the link checker (classification, extraction, status file).

Used by : `npm test`.
Uses    : tools/swp_tools/links.py against a local test server.
"""

import http.server
import json
import pathlib
import socket
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "tools"))
from swp_tools.links import check_link, extract_links, markdown_report, update_status_file  # noqa: E402


class Handler(http.server.BaseHTTPRequestHandler):
    routes = {"/ok": 200, "/gone": 404, "/blocked": 403, "/error": 500}

    def do_GET(self):
        if self.path == "/redirect":
            self.send_response(301)
            self.send_header("Location", "/ok")
            self.end_headers()
            return
        self.send_response(self.routes.get(self.path, 404))
        self.end_headers()
        self.wfile.write(b"x")

    def log_message(self, *args):
        pass


class LinkCheckTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_classification(self):
        expected = {"/ok": ("ok", 200), "/gone": ("broken", 404), "/error": ("broken", 500),
                    "/blocked": ("unknown", 403)}
        for path, (status, code) in expected.items():
            result = check_link(self.base + path)
            self.assertEqual((result.status, result.code), (status, code), path)

    def test_redirect_followed_and_recorded(self):
        result = check_link(self.base + "/redirect")
        self.assertEqual(result.status, "ok")
        self.assertTrue(result.final_url and result.final_url.endswith("/ok"))

    def test_no_answer_is_broken(self):
        with socket.socket() as s:                    # a port where nothing listens
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        result = check_link(f"http://127.0.0.1:{port}/")
        self.assertEqual((result.status, result.code), ("broken", None))

    def test_extract_links_from_source(self):
        root = pathlib.Path(tempfile.mkdtemp(prefix="links_"))
        (root / "content.ts").write_text('''/* Format: { url: "https://..." } or icon: "https://f.start.me/…" */
// example: "https://commented.example"
{ url: "https://a.example/x?y=1" }, `https://b.example`, 'http://c.example/é' ''', encoding="utf-8")
        self.assertEqual(extract_links(root, ["content.ts"]),
                         ["http://c.example/é", "https://a.example/x?y=1", "https://b.example"])
        with self.assertRaises(SystemExit):
            extract_links(root, ["missing.ts"])

    def test_malformed_address_is_one_broken_result(self):
        result = check_link("https://.../x")
        self.assertEqual((result.status, result.code), ("broken", None))

    def test_status_file_written_only_on_change(self):
        out = pathlib.Path(tempfile.mkdtemp(prefix="status_")) / "data" / "link-status.json"
        results = [check_link(self.base + "/ok"), check_link(self.base + "/gone")]
        self.assertTrue(update_status_file(out, results, today="2026-10-01"))
        self.assertFalse(update_status_file(out, results, today="2026-10-08"))     # same statuses: untouched
        self.assertEqual(json.loads(out.read_text())["date"], "2026-10-01")
        self.assertTrue(update_status_file(out, results[:1], today="2026-10-08"))  # a link removed: written
        self.assertIn("Broken links (1)", markdown_report(results))


if __name__ == "__main__":
    unittest.main()
