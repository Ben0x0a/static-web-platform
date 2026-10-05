"""serve.py — local test server that behaves like Cloudflare Pages for headers (swp serve).

Defines : parse_headers_file() (reads a Cloudflare `_headers` file) and
          make_server() (static server applying those headers).
Used by : gate.py (imports it); cli.py (`swp serve`).
Uses    : standard library only.

WHY parse `_headers` instead of hard-coding headers: the deployed site's
headers then have one source of truth, and a mistake in `_headers` (e.g. a
missing CORS header that breaks the update check) shows up in local tests.

It also imitates Cloudflare Pages' "pretty URLs": a request for /x.html is
redirected (308) to /x, and /x serves x.html. Header rules match the path
actually requested — so a rule written only for /x.html does not apply to
the final response, exactly as in production.

Usage: npx swp serve [public_dir] [port]
"""

import fnmatch
import functools
import http.server
import logging
import pathlib

_LOG = logging.getLogger("serve")


def parse_headers_file(path: pathlib.Path) -> list[tuple[str, list[tuple[str, str]]]]:
    """Return [(url_pattern, [(header, value), ...]), ...] from a `_headers` file.

    Format (Cloudflare Pages): an unindented URL pattern line, followed by
    indented `Name: value` lines. `#` lines are comments.
    """
    rules: list[tuple[str, list[tuple[str, str]]]] = []
    if not path.is_file():
        return rules
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw[0].isspace():
            rules.append((raw.strip(), []))
        elif rules and ":" in raw:
            name, value = raw.strip().split(":", 1)
            rules[-1][1].append((name.strip(), value.strip()))
    return rules


def _make_handler(directory: pathlib.Path):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def _pretty_urls(self) -> bool:
            """Cloudflare Pages behaviour; True when a redirect was sent."""
            path, _, query = self.path.partition("?")
            suffix = f"?{query}" if query else ""
            self.requested_path = path
            if path.endswith(".html"):
                target = path[: -len("index.html")] if path.endswith("/index.html") else path[: -len(".html")]
                self.send_response(308)
                self.send_header("Location", target + suffix)
                self.end_headers()
                return True
            name = path.rsplit("/", 1)[-1]
            if name and "." not in name and (directory / f"{path.lstrip('/')}.html").is_file():
                self.path = f"{path}.html{suffix}"      # served as x.html, headers matched on /x
            return False

        def do_GET(self):
            if not self._pretty_urls():
                super().do_GET()

        def do_HEAD(self):
            if not self._pretty_urls():
                super().do_HEAD()

        def end_headers(self):
            # Re-read on every request: the folder may be (re)built after the
            # server started (the gate needs the port before building).
            url_path = getattr(self, "requested_path", self.path.split("?", 1)[0])
            for pattern, headers in parse_headers_file(directory / "_headers"):
                if fnmatch.fnmatchcase(url_path, pattern):
                    for name, value in headers:
                        self.send_header(name, value)
            super().end_headers()

        def log_message(self, fmt, *args):
            _LOG.debug(fmt, *args)

    return functools.partial(Handler, directory=str(directory))


class _Server(http.server.ThreadingHTTPServer):
    # Python's default backlog is 5 pending connections: too few for browsers
    # (and parallel test runs) opening many connections at once.
    request_queue_size = 128
    daemon_threads = True


def make_server(directory: pathlib.Path, port: int = 0) -> http.server.ThreadingHTTPServer:
    """Create (not start) a server for `directory` on 127.0.0.1; port 0 = any free port."""
    return _Server(("127.0.0.1", port), _make_handler(directory))
