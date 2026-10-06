"""links.py — check the app's outgoing links from a server, never from visitors (swp links).

Defines : extract_links(), check_link(), check_links(), update_status_file(),
          markdown_report(), LinkResult.
Used by : cli.py (`swp links`), typically in a scheduled CI workflow that opens
          a pull request when a status changes and an issue when links break.
Uses    : site.json "linkCheck": {"sources": ["src/content.ts"],
          "output": "data/link-status.json"}; the network (this is a
          maintainer tool run in CI or by hand — never part of the app).

WHY server-side: a page cannot see another site's status (CORS: only an
opaque "answered / did not answer"), would need one consent per server, and
only informs whoever clicks. A CI check gets real status codes, makes no
request from visitors, works for the single file (the result is bundled as a
dataset) and warns the maintainer when nobody looks.

Classification:
  ok      2xx after following redirects (final address recorded when different)
  broken  404, 410, other 4xx/5xx, DNS / connection / TLS failure, timeout
  unknown 401, 403, 429, 503 challenges — sites that block robots: never shown
          as broken (a false red is worse than a grey)
A checker sees whether a page ANSWERS, not whether it is the RIGHT page.
"""

import concurrent.futures
import dataclasses
import datetime
import json
import pathlib
import re
import urllib.error
import urllib.parse
import urllib.request

URL_LITERAL = re.compile(r"""["'`](https?://[^"'`\s]+)["'`]""")
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
VALID_HOST = re.compile(r"^[^.\s…]+(\.[^.\s…]+)+$")
UNKNOWN_CODES = {401, 403, 429, 503}
USER_AGENT = "static-web-platform link check (+https://github.com/Ben0x0a/static-web-platform)"
TIMEOUT_SECONDS = 20
WORKERS = 8


@dataclasses.dataclass(frozen=True)
class LinkResult:
    url: str
    status: str                 # "ok" | "broken" | "unknown"
    code: int | None            # final HTTP status; None when no answer
    final_url: str | None       # set when redirects led elsewhere
    detail: str


def extract_links(root: pathlib.Path, sources: list[str]) -> list[str]:
    """Every http(s) URL written as a string literal in the given source files (sorted, unique)."""
    found: set[str] = set()
    for source in sources:
        path = root / source
        # Invariant: a declared source that does not exist is a typo — the
        # check would silently cover nothing.
        if not path.is_file():
            raise SystemExit(f'site.json linkCheck.sources: "{source}" not found')
        # Comments document the format with example URLs ("https://...") —
        # only real content counts: drop /* */ blocks and // comment lines.
        text = BLOCK_COMMENT.sub("", path.read_text(encoding="utf-8"))
        text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))
        found.update(url for url in URL_LITERAL.findall(text)
                     if VALID_HOST.match(urllib.parse.urlsplit(url).hostname or ""))
    return sorted(found)


def _ascii_url(url: str) -> str:
    """IDN host → punycode, non-ASCII path/query → percent-encoded (urllib needs ASCII)."""
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname.encode("idna").decode("ascii") if parts.hostname else ""
    netloc = host + (f":{parts.port}" if parts.port else "")
    quote = lambda s, safe: urllib.parse.quote(s, safe=safe)  # noqa: E731
    return urllib.parse.urlunsplit((parts.scheme, netloc, quote(parts.path, "/%:@!$&'()*+,;=-._~"),
                                    quote(parts.query, "=&%:@!$'()*+,;/?-._~"), quote(parts.fragment, "%-._~")))


def check_link(url: str) -> LinkResult:
    # Invariant: one bad address yields one "broken" result — it must never
    # abort the whole run (the report would then cover nothing).
    try:
        ascii_url = _ascii_url(url)
    except (UnicodeError, ValueError) as err:
        return LinkResult(url, "broken", None, None, f"invalid address: {err}")
    request = urllib.request.Request(ascii_url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            final = response.url
            code = response.status
    except urllib.error.HTTPError as err:
        code, final = err.code, err.url
        err.close()                                   # an error response is still an open connection
        status = "unknown" if code in UNKNOWN_CODES else "broken"
        return LinkResult(url, status, code, final if final != _ascii_url(url) else None, f"HTTP {code}")
    except (urllib.error.URLError, OSError, ValueError) as err:
        reason = getattr(err, "reason", err)
        return LinkResult(url, "broken", None, None, f"no answer: {reason}")
    redirected = final if final != _ascii_url(url) else None
    return LinkResult(url, "ok", code, redirected, f"HTTP {code}" + (f" via {final}" if redirected else ""))


def check_links(urls: list[str]) -> list[LinkResult]:
    with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
        return list(pool.map(check_link, urls))


def _entry(result: LinkResult) -> dict:
    entry = {"status": result.status, "code": result.code}
    if result.final_url:
        entry["finalUrl"] = result.final_url
    return entry


def update_status_file(path: pathlib.Path, results: list[LinkResult], today: str | None = None) -> bool:
    """Write the status file ONLY when a status changed (or links were added/removed).

    WHY: a file rewritten with a new date every week would open a pull request
    every week for nothing. The file's date is the date of the last CHANGE
    (shown as « état du … »). Returns True when the file was written.
    """
    links = {r.url: _entry(r) for r in sorted(results, key=lambda r: r.url)}
    previous = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    if previous is not None and previous.get("links") == links:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "//": "GENERATED by `swp links` (static-web-platform). Do not edit.",
        "date": today or datetime.datetime.now(datetime.timezone.utc).date().isoformat(),
        "links": links,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


def markdown_report(results: list[LinkResult]) -> str:
    """Body for the CI issue / pull request: broken first, then unknown."""
    lines = []
    for status, title in (("broken", "Broken links"), ("unknown", "Not verifiable automatically (robots blocked)")):
        rows = [r for r in results if r.status == status]
        if rows:
            lines += [f"### {title} ({len(rows)})", ""] + [f"- {r.url} — {r.detail}" for r in rows] + [""]
    ok = sum(r.status == "ok" for r in results)
    lines.append(f"{ok} of {len(results)} links answer normally.")
    return "\n".join(lines) + "\n"
