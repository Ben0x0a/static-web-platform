"""test_build_tools.py — unit tests of the pure build helpers (CSP, config.js, headers,
site.json validation, the local-server zip).

Used by : `npm test` (python3 -m unittest).
Uses    : tools/swp_tools/csp.py, assemble.py, config.py, package.py, serve.py, cors.py.
"""

import io
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "tools"))
from swp_tools.assemble import config_js, headers_file, inline_css, inline_js  # noqa: E402
from swp_tools.config import (Project, expand_net_origins_from, load_project, validate_net_origins,  # noqa: E402
                              validate_support)
from swp_tools.package import PORT_BLOCK, default_port, local_zip  # noqa: E402
from swp_tools.cors import ORIGIN_NULL, check_cors, copy_origins  # noqa: E402
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
        js = config_js(Project(root=pathlib.Path("."), site=SITE, platform_dir=pathlib.Path(".")),
                       "single", "abc123", "2026-10-03")
        self.assertIn('"mode": "single"', js)
        self.assertIn('"download": "app.html"', js)
        self.assertIn('"cli": null', js)
        self.assertIn('"version": "abc123"', js)
        self.assertTrue(js.splitlines()[1].startswith("window.__SWP_SITE__ = {"))

    def test_single_file_allows_blob_workers_only_when_declared(self):
        self.assertEqual(directives(build_csp(SITE, "single"))["worker-src"], ["'none'"])
        with_workers = {**SITE, "workers": {"solver": "src/workers/solver.ts"}}
        self.assertEqual(directives(build_csp(with_workers, "single"))["worker-src"], ["blob:"])
        self.assertEqual(directives(build_csp(with_workers, "site"))["worker-src"], ["'self'"])

    def test_download_is_an_attachment_with_and_without_html(self):
        rules = parse_headers_text(headers_file("app.html"))
        for path in ("/app.html", "/app"):
            self.assertIn(("Content-Disposition", 'attachment; filename="app.html"'), rules[path], path)

    def test_cors_only_on_version_json(self):
        headers = headers_file("app.html")
        block = headers.split("/version.json")[1].split("\n\n")[0]
        self.assertIn("Access-Control-Allow-Origin: *", block)
        self.assertEqual(headers.count("Access-Control-Allow-Origin"), 1)

    def test_no_download_no_attachment_rule(self):
        self.assertNotIn("Content-Disposition", headers_file(None))

    def test_local_copy_is_the_site_policy_plus_its_site(self):
        csp = directives(build_csp(SITE, "local"))
        self.assertEqual(csp["script-src"], ["'self'"])
        self.assertEqual(csp["connect-src"], ["'self'", "https://app.example"])
        self.assertEqual(directives(build_csp({**SITE, "siteUrl": ""}, "local"))["connect-src"], ["'self'"])


def make_app(site: dict, files: dict[str, str] | None = None) -> pathlib.Path:
    """A minimal app folder that load_project accepts (src/site.json + an installed platform)."""
    root = pathlib.Path(tempfile.mkdtemp(prefix="site_"))
    (root / "node_modules" / "static-web-platform").mkdir(parents=True)
    for name, text in {"src/site.json": json.dumps(site), **(files or {})}.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    return root


SITE_JSON = {**SITE, "shortName": "App", "themeColor": "#000000"}


class SiteValidationTest(unittest.TestCase):
    def assert_rejected(self, site: dict, message: str, files: dict[str, str] | None = None):
        with self.assertRaises(SystemExit) as caught:
            load_project(make_app(site, files))
        self.assertIn(message, str(caught.exception))

    def test_distribution_values(self):
        for distribution in ("single", "local-server", "site-only"):
            self.assertEqual(load_project(make_app({**SITE_JSON, "distribution": distribution})).distribution, distribution)
        self.assert_rejected({**SITE_JSON, "distribution": "zip"}, '"distribution" must be one of')

    def test_download_follows_the_distribution(self):
        site_only = {key: value for key, value in SITE_JSON.items() if key != "downloadName"}
        self.assertIsNone(load_project(make_app({**site_only, "distribution": "site-only"})).download_filename)
        self.assertEqual(load_project(make_app({**site_only, "distribution": "local-server"})).download_filename,
                         "app-local.zip")
        self.assert_rejected(site_only, '"downloadName" is required')

    def test_cli_entry_must_be_in_src_cli(self):
        project = load_project(make_app({**SITE_JSON, "cli": {"entry": "src/cli/main.ts"}}, {"src/cli/main.ts": ""}))
        self.assertEqual(project.cli_filename, "app-cli.js")
        self.assert_rejected({**SITE_JSON, "cli": {"entry": "src/main.ts"}}, '"cli" must be', {"src/main.ts": ""})
        self.assert_rejected({**SITE_JSON, "cli": {"entry": "src/cli/missing.ts"}}, '"cli" must be')
        # Resolved before the check: ".." cannot lead the entry out of src/cli/.
        self.assert_rejected({**SITE_JSON, "cli": {"entry": "src/cli/../tool.ts"}}, '"cli" must be',
                             {"src/tool.ts": "", "src/cli/x.ts": ""})
        for bad in (None, "src/cli/main.ts", {"entry": None}):
            self.assert_rejected({**SITE_JSON, "cli": bad}, '"cli" must be', {"src/cli/main.ts": ""})


class LocalZipTest(unittest.TestCase):
    PROJECT = Project(root=pathlib.Path("."), site=SITE, platform_dir=pathlib.Path("."))
    FILES = {"index.html": b"<p>page</p>", "icons/icon.svg": b"<svg/>", "app.js": b"run()"}

    def zip_bytes(self, files: dict[str, bytes]) -> bytes:
        target = pathlib.Path(tempfile.mkdtemp(prefix="zip_")) / "app-local.zip"
        local_zip(self.PROJECT, files, "serve()", target)
        return target.read_bytes()

    def test_reproducible_whatever_the_input_order(self):
        reversed_files = dict(reversed(list(self.FILES.items())))
        self.assertEqual(self.zip_bytes(self.FILES), self.zip_bytes(reversed_files))

    def test_launcher_config_holds_the_app_port(self):
        with zipfile.ZipFile(io.BytesIO(self.zip_bytes(self.FILES))) as archive:
            config = json.loads(archive.read("app-local/serve.json"))
        self.assertEqual(config, {"port": default_port(self.PROJECT), "first": PORT_BLOCK[0], "last": PORT_BLOCK[1]})

    def test_layout_and_fixed_metadata(self):
        with zipfile.ZipFile(io.BytesIO(self.zip_bytes(self.FILES))) as archive:
            names = archive.namelist()
            self.assertEqual(names, sorted(names))
            self.assertIn("app-local/serve.js", names)
            self.assertIn("app-local/README.txt", names)
            self.assertIn("app-local/public/icons/icon.svg", names)
            for info in archive.infolist():
                self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(info.compress_type, zipfile.ZIP_STORED)
            self.assertEqual(archive.read("app-local/public/app.js"), b"run()")



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
            (root / "_headers").write_text(headers_file("app.html"), encoding="utf-8")
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


class PortTest(unittest.TestCase):
    def project(self, app_id: str) -> Project:
        return Project(root=pathlib.Path("."), site={**SITE, "id": app_id}, platform_dir=pathlib.Path("."))

    def test_stable_per_app_inside_the_unassigned_block(self):
        ports = {default_port(self.project(f"app-{i}")) for i in range(50)}
        self.assertTrue(all(PORT_BLOCK[0] <= port <= PORT_BLOCK[1] for port in ports))
        self.assertGreater(len(ports), 40)                 # different apps, different ports (almost always)
        self.assertEqual(default_port(self.project("app")), default_port(self.project("app")))


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
        self.assertTrue(all(r.allowed for r in check_cors([url], ["https://app.example", ORIGIN_NULL])))

    def test_site_only_fails_the_single_file(self):
        url = self.serve("/*\n  Access-Control-Allow-Origin: https://app.example\n")
        results = {r.origin: r.allowed for r in check_cors([url], ["https://app.example", ORIGIN_NULL])}
        self.assertEqual(results, {"https://app.example": True, "null": False})

    def test_origins_follow_the_local_copy(self):
        def project(distribution: str) -> Project:
            return Project(root=pathlib.Path("."), site={**SITE, "distribution": distribution},
                           platform_dir=pathlib.Path("."))
        self.assertEqual(copy_origins(project("single")), [ORIGIN_NULL])
        self.assertEqual(copy_origins(project("local-server")), [f"http://127.0.0.1:{default_port(project('single'))}"])
        self.assertEqual(copy_origins(project("site-only")), [])
        self.assertEqual(copy_origins(None), [ORIGIN_NULL])


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
