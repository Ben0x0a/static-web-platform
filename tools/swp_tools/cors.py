"""cors.py — check that external endpoints answer CORS for BOTH outputs (swp cors).

Defines : check_cors(), CorsResult.
Used by : cli.py (`swp cors <url> …`), run by the developer BEFORE declaring
          an endpoint in site.json netOrigins.
Uses    : the network (this is a developer tool, never part of the app);
          config.Project for siteUrl.

WHY both origins: the hosted site sends Origin: https://<site>, but the
downloaded single file runs from file:// and sends Origin: null. A server that
answers "*" works for both; one that only echoes known sites back fails in
the single file. Only simple GET requests are checked (what platform.net
sends without extra headers); a request with custom headers would also need
a preflight.
"""

import dataclasses
import urllib.error
import urllib.request

ORIGIN_NULL = "null"


@dataclasses.dataclass(frozen=True)
class CorsResult:
    url: str
    origin: str
    allowed: bool
    detail: str


def _probe(url: str, origin: str) -> CorsResult:
    request = urllib.request.Request(url, headers={"Origin": origin}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            allow = response.headers.get("Access-Control-Allow-Origin", "")
            status = response.status
    except urllib.error.HTTPError as err:          # an error status still carries CORS headers
        allow, status = err.headers.get("Access-Control-Allow-Origin", ""), err.code
    except OSError as err:
        return CorsResult(url, origin, False, f"unreachable: {err}")
    allowed = allow == "*" or allow == origin
    return CorsResult(url, origin, allowed, f"HTTP {status}, Access-Control-Allow-Origin: {allow or '(none)'}")


def check_cors(urls: list[str], site_origin: str | None) -> list[CorsResult]:
    origins = ([site_origin] if site_origin else []) + [ORIGIN_NULL]
    return [_probe(url, origin) for url in urls for origin in origins]
