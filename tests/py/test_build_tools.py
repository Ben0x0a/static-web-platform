"""test_build_tools.py — unit tests of the pure build helpers (CSP, config.js, headers).

Used by : `npm test` (python3 -m unittest).
Uses    : tools/swp_tools/csp.py, assemble.py.
"""

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "tools"))
from swp_tools.assemble import config_js, headers_file, inline_css, inline_js  # noqa: E402
from swp_tools.config import expand_net_origins_from, validate_net_origins, validate_support  # noqa: E402
from swp_tools.cors import check_cors  # noqa: E402
from swp_tools.csp import build_csp  # noqa: E402
from swp_tools.serve import make_server, parse_headers_file  # noqa: E402

SITE = {"id": "app", "title": "App", "lang": "en", "siteUrl": "https://app.example/", "downloadName": "app.html",
        "netOrigins": {"https://icons.example": {"directive": "img-src", "purpose": "Icons"}}, "options": {}}


def parse_headers_text(text: str) -> dict[str, list[tuple[str, str]]]:
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "_headers"
        path.write_text(text, encoding="utf-8")
        return dict(parse_headers_file(path))


def directives(csp: str) -> dict[str, list[str]]:
    return {p.split()[0]: p.split()[1:] for p in csp.split(";") if p.strip()}


class CspTest(unittest.TestCase):
    def test_site_forbids_inline_code(self):
        csp = directives(build_csp(SITE, "site"))
        self.assertEqual(csp["script-src"], ["'self'"])
        self.assertEqual(csp["style-src"], ["'self'"])
        self.assertEqual(csp["connect-src"], ["'self'"])

    def test_single_file_may_only_reach_its_site(self):
        csp = directives(build_csp(SITE, "single"))
        self.assertEqual(csp["connect-src"], ["https://app.example"])
        self.assertEqual(csp["worker-src"], ["'none'"])

    def test_single_file_without_site_url_reaches_nothing(self):
        csp = directives(build_csp({**SITE, "siteUrl": ""}, "single"))
        self.assertEqual(csp["connect-src"], ["'none'"])

    def test_fonts_only_from_embedded_data(self):
        for mode in ("site", "single"):
            self.assertEqual(directives(build_csp(SITE, mode))["font-src"], ["data:"])

    def test_declared_origins_are_added_under_their_directive(self):
        for mode in ("site", "single"):
            self.assertIn("https://icons.example", directives(build_csp(SITE, mode))["img-src"])


class AssembleTest(unittest.TestCase):
    def test_config_js_carries_mode_and_version(self):
        js = config_js(SITE, "single", "abc123", "2026-10-03")
        self.assertIn('"mode": "single"', js)
        self.assertIn('"version": "abc123"', js)
        self.assertTrue(js.splitlines()[1].startswith("window.__SWP_SITE__ = {"))

    def test_single_file_allows_blob_workers_only_when_declared(self):
        self.assertEqual(directives(build_csp(SITE, "single"))["worker-src"], ["'none'"])
        with_workers = {**SITE, "workers": {"solver": "src/workers/solver.ts"}}
        self.assertEqual(directives(build_csp(with_workers, "single"))["worker-src"], ["blob:"])
        self.assertEqual(directives(build_csp(with_workers, "site"))["worker-src"], ["'self'"])

    def test_download_is_an_attachment_with_and_without_html(self):
        rules = parse_headers_text(headers_file(SITE))
        for path in ("/app.html", "/app"):
            self.assertIn(("Content-Disposition", 'attachment; filename="app.html"'), rules[path], path)

    def test_cors_only_on_version_json(self):
        headers = headers_file(SITE)
        block = headers.split("/version.json")[1].split("\n\n")[0]
        self.assertIn("Access-Control-Allow-Origin: *", block)
        self.assertEqual(headers.count("Access-Control-Allow-Origin"), 1)



class NetOriginsValidationTest(unittest.TestCase):
    def test_valid_declaration_passes(self):
        validate_net_origins({"https://tile.example": {"directive": "img-src", "purpose": "Map",
                                                       "scope": "origin", "referrerPolicy": "strict-origin"}},
                             pathlib.Path("site.json"))

    def test_malformed_declarations_are_rejected(self):
        for spec in ({"directive": "script-src", "purpose": "x"}, {"directive": "img-src"},
                     {"directive": "img-src", "purpose": "x", "scope": "always"},
                     {"directive": "img-src", "purpose": "x", "referrerPolicy": "unsafe-url"}):
            with self.assertRaises(SystemExit):
                validate_net_origins({"https://x.example": spec}, pathlib.Path("site.json"))
        with self.assertRaises(SystemExit):
            validate_net_origins({"http://x.example/path": {"directive": "img-src", "purpose": "x"}},
                                 pathlib.Path("site.json"))


BOOTSTRAP = {"version": "1.0", "services": [
    [["com", "net"], ["https://rdap.verisign.com/com/v1/"]],
    [["ch", "li"], ["https://rdap.nic.ch/"]],
    [["org"], ["https://rdap.publicinterestregistry.org/rdap/", "http://insecure.example/"]],
]}


class NetOriginsFromTest(unittest.TestCase):
    def make(self, data: dict | None, declared: dict | None = None):
        root = pathlib.Path(tempfile.mkdtemp(prefix="nof_"))
        if data is not None:
            (root / "src" / "data").mkdir(parents=True)
            (root / "src" / "data" / "rdap.json").write_text(json.dumps(data), encoding="utf-8")
        site = {"netOrigins": dict(declared or {}), "netOriginsFrom": [
            {"data": "data/rdap.json", "directive": "connect-src", "purpose": "RDAP", "scope": "request"}]}
        return root, site

    def test_every_https_origin_is_declared_exactly(self):
        root, site = self.make(BOOTSTRAP)
        expand_net_origins_from(site, root, pathlib.Path("site.json"))
        self.assertEqual(sorted(site["netOrigins"]), ["https://rdap.nic.ch", "https://rdap.publicinterestregistry.org",
                                                      "https://rdap.verisign.com"])   # http:// ignored
        spec = site["netOrigins"]["https://rdap.nic.ch"]
        self.assertEqual((spec["scope"], spec["group"]), ("request", "data/rdap.json"))
        validate_net_origins(site["netOrigins"], pathlib.Path("site.json"))
        self.assertIn("https://rdap.nic.ch", directives(build_csp({**SITE, "netOrigins": site["netOrigins"]}, "site"))["connect-src"])

    def test_declared_twice_is_an_error(self):
        root, site = self.make(BOOTSTRAP, {"https://rdap.nic.ch": {"directive": "connect-src", "purpose": "x"}})
        with self.assertRaises(SystemExit):
            expand_net_origins_from(site, root, pathlib.Path("site.json"))

    def test_only_datasets_under_src_data(self):
        root, site = self.make(None)
        with self.assertRaises(SystemExit):
            expand_net_origins_from(site, root, pathlib.Path("site.json"))


class SupportValidationTest(unittest.TestCase):
    def test_https_link_or_nothing(self):
        validate_support(None, pathlib.Path("site.json"))
        validate_support({"url": "https://buymeacoffee.com/forandchips"}, pathlib.Path("site.json"))
        for bad in ({"url": "http://buymeacoffee.com/x"}, {"url": "javascript:alert(1)"}, {}, "https://x"):
            with self.assertRaises(SystemExit):
                validate_support(bad, pathlib.Path("site.json"))


class PrettyUrlServeTest(unittest.TestCase):
    """swp serve imitates Cloudflare Pages: /x.html → 308 → /x, headers matched on the path requested."""

    def test_redirect_then_attachment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "app.html").write_text("<p>offline copy</p>", encoding="utf-8")
            (root / "_headers").write_text(headers_file(SITE), encoding="utf-8")
            server = make_server(root)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/app.html", timeout=5) as response:
                    self.assertTrue(response.url.endswith("/app"))
                    self.assertIn("attachment", response.headers.get("Content-Disposition", ""))
                    self.assertIn("offline copy", response.read().decode())
            finally:
                server.shutdown()
                server.server_close()


class CorsCheckTest(unittest.TestCase):
    """swp cors: '*' works for both outputs; echoing only the site fails the single file (Origin: null)."""

    def serve(self, rules: str) -> str:
        root = pathlib.Path(tempfile.mkdtemp(prefix="cors_"))
        (root / "a.json").write_text("{}", encoding="utf-8")
        (root / "_headers").write_text(rules, encoding="utf-8")
        server = make_server(root)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}/a.json"

    def test_star_allows_both(self):
        url = self.serve("/*\n  Access-Control-Allow-Origin: *\n")
        self.assertTrue(all(r.allowed for r in check_cors([url], "https://app.example")))

    def test_site_only_fails_the_single_file(self):
        url = self.serve("/*\n  Access-Control-Allow-Origin: https://app.example\n")
        results = {r.origin: r.allowed for r in check_cors([url], "https://app.example")}
        self.assertEqual(results, {"https://app.example": True, "null": False})


HAZARDOUS_JS = r"""
const a = "<!--";
const b = "<script>x</script>";
const c = `<SCRIPT src=y></Script>`;
const d = /<!--<script>/u.test("<!--<script>") && !/<!--<script>/u.test("<!--<scrip");
const e = /<\/script>/.test("</script>");
console.log(JSON.stringify([a, b, c, d, e]));
"""


class InlineTest(unittest.TestCase):
    def test_no_hazard_remains(self):
        out = inline_js(HAZARDOUS_JS)
        for hazard in ("<!--", "<script", "</script", "<SCRIPT", "</Script"):
            self.assertNotIn(hazard, out)

    @unittest.skipUnless(shutil.which("node"), "node not on PATH")
    def test_escaped_code_means_the_same(self):
        run = lambda js: subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout
        self.assertEqual(json.loads(run(inline_js(HAZARDOUS_JS))), json.loads(run(HAZARDOUS_JS)))

    def test_css_closing_tag_escaped(self):
        self.assertNotIn("</style", inline_css('a::after { content: "</style>"; }'))


if __name__ == "__main__":
    unittest.main()
