"""csp.py — Content-Security-Policy of each output, generated from site.json.

Defines : build_csp(), site_origin().
Used by : assemble.py (the <meta> of each page).
Uses    : the site dict (netOrigins, siteUrl).

site   : no inline code at all ('self' only) — the strongest policy.
single : inline CSS/JS is unavoidable in one file; the only server it may
         reach is the site's origin, for the update check (version.json).
Declared external origins (netOrigins) are added under their directive, so the
CSP and the consent gate always list the same servers.
"""


def site_origin(site: dict) -> str:
    url = site["siteUrl"]
    return url[: url.index("/", url.index("//") + 2)] if url else ""


def build_csp(site: dict, mode: str) -> str:
    single = mode == "single"
    directives: dict[str, list[str]] = {
        "default-src": ["'none'"],
        "script-src": ["'unsafe-inline'"] if single else ["'self'"],
        "style-src": ["'unsafe-inline'"] if single else ["'self'"],
        "img-src": ["data:", "blob:"] if single else ["'self'", "data:", "blob:"],
        "connect-src": ([site_origin(site)] if site["siteUrl"] else ["'none'"]) if single else ["'self'"],
        "manifest-src": ["'none'"] if single else ["'self'"],
        # Single file: declared workers start from inline code via blob: URLs.
        "worker-src": (["blob:"] if site.get("workers") else ["'none'"]) if single else ["'self'"],
        "base-uri": ["'none'"],
        "form-action": ["'none'"],
    }
    for origin, spec in site["netOrigins"].items():
        sources = directives.setdefault(spec["directive"], ["'none'"])
        if sources == ["'none'"]:
            sources.clear()
        sources.append(origin)
    return "; ".join(f"{name} {' '.join(sources)}" for name, sources in directives.items())
