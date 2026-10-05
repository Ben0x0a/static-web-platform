"""config.py — the Project data container: an app's paths and validated site.json.

Defines : Project, load_project(), PLATFORM_PACKAGE_NAME.
Used by : version.py, bundle.py, assemble.py, builder.py, gate.py, cli.py.
Uses    : the app's src/site.json; node_modules/static-web-platform (the
          installed platform, possibly a symlink for a local file: dependency).
"""

import dataclasses
import json
import pathlib
import re
import urllib.parse

PLATFORM_PACKAGE_NAME = "static-web-platform"
SITE_FILENAME = "site.json"
REQUIRED_SITE_KEYS = ("id", "title", "shortName", "lang", "themeColor", "siteUrl", "downloadName", "netOrigins", "options")
DEFAULT_ENTRY = "src/main.ts"
DEFAULT_APP_BUILD_DIR = "build/app"


@dataclasses.dataclass(frozen=True)
class Project:
    root: pathlib.Path
    site: dict
    platform_dir: pathlib.Path          # installed platform package (real path)

    @property
    def src(self) -> pathlib.Path:
        return self.root / "src"

    @property
    def public(self) -> pathlib.Path:
        return self.root / "public"

    @property
    def entry(self) -> pathlib.Path:
        return self.root / self.site.get("entry", DEFAULT_ENTRY)

    @property
    def app_build_command(self) -> list[str] | None:
        """The app's own bundling command (e.g. Vite for Svelte), or None for esbuild."""
        return self.site.get("appBuild", {}).get("command")

    @property
    def app_build_inputs(self) -> list[str]:
        """Extra files (globs, relative to the app root) that shape the bundle."""
        return self.site.get("appBuild", {}).get("inputs", [])

    @property
    def workers(self) -> dict[str, pathlib.Path]:
        """Declared Web Workers: name → entry file (site.json "workers")."""
        return {name: self.root / entry for name, entry in self.site.get("workers", {}).items()}

    @property
    def precache_assets(self) -> bool:
        return bool(self.site.get("precacheAssets", False))

    @property
    def app_build_dir(self) -> pathlib.Path:
        return self.root / self.site.get("appBuild", {}).get("outDir", DEFAULT_APP_BUILD_DIR)


CSP_DIRECTIVES = {"img-src", "connect-src", "media-src", "font-src", "frame-src"}
CONSENT_SCOPES = {"origin", "request"}
REFERRER_CHOICES = {"no-referrer", "origin", "strict-origin"}


GROUP_KEYS = ("directive", "purpose", "scope", "referrerPolicy")


def _https_origins(value) -> set[str]:
    """Every https origin found in any string of a JSON value (e.g. IANA RDAP bootstrap)."""
    if isinstance(value, str):
        if value.startswith("https://"):
            parts = urllib.parse.urlsplit(value)
            return {f"https://{parts.netloc.lower()}"} if parts.netloc else set()
        return set()
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, list):
        return set().union(*(_https_origins(v) for v in value)) if value else set()
    return set()


def expand_net_origins_from(site: dict, root: pathlib.Path, site_path: pathlib.Path) -> None:
    """Declare the servers listed in a bundled dataset (site.json "netOriginsFrom").

    WHY: some services have hundreds of servers (RDAP: one per TLD registry).
    Wildcards would weaken both the CSP and the consent dialog; instead the
    build reads the dataset (reviewed through SOURCES.md) and declares every
    origin it lists EXACTLY, in the CSP and the consent list, tagged with the
    dataset as their "group" (one row in the Privacy dialog).
    """
    for group in site.get("netOriginsFrom", []):
        data = group.get("data", "")
        source = root / "src" / data
        # Invariant: the list comes from a reviewed dataset (src/data/ +
        # SOURCES.md), never from an arbitrary file or the network.
        if not data.startswith("data/") or not source.is_file():
            raise SystemExit(f'{site_path}: netOriginsFrom "{data}" must be an existing file under src/data/')
        origins = sorted(_https_origins(json.loads(source.read_text(encoding="utf-8"))))
        if not origins:
            raise SystemExit(f"{site_path}: netOriginsFrom {data}: no https address found")
        spec = {key: group[key] for key in GROUP_KEYS if key in group}
        for origin in origins:
            # Invariant: one declaration per origin — two with different scopes
            # or purposes would make the consent dialog ambiguous.
            if origin in site["netOrigins"]:
                raise SystemExit(f"{site_path}: {origin} is declared twice (netOrigins and netOriginsFrom {data})")
            site["netOrigins"][origin] = {**spec, "group": data}


def validate_net_origins(net_origins: dict, site_path: pathlib.Path) -> None:
    """Reject malformed declarations early: they feed both the CSP and the consent dialog."""
    for origin, spec in net_origins.items():
        problems = []
        if not origin.startswith("https://") or origin.count("/") != 2:
            problems.append("must be an https origin without path (https://host[:port])")
        if spec.get("directive") not in CSP_DIRECTIVES:
            problems.append(f"directive must be one of {sorted(CSP_DIRECTIVES)}")
        if not spec.get("purpose"):
            problems.append("purpose is required (shown in the consent dialog)")
        if spec.get("scope", "origin") not in CONSENT_SCOPES:
            problems.append(f"scope must be one of {sorted(CONSENT_SCOPES)}")
        if spec.get("referrerPolicy", "no-referrer") not in REFERRER_CHOICES:
            problems.append(f"referrerPolicy must be one of {sorted(REFERRER_CHOICES)}")
        if problems:
            raise SystemExit(f"{site_path}: netOrigins['{origin}']: " + "; ".join(problems))


def validate_support(support: dict | None, site_path: pathlib.Path) -> None:
    """site.json "support": {"url": "https://…"} — a plain https link (never a widget)."""
    if support is None:
        return
    url = support.get("url", "") if isinstance(support, dict) else ""
    if not re.fullmatch(r"https://[^\s\"<>]+", url):
        raise SystemExit(f'{site_path}: "support" must be {{"url": "https://…"}}')


def load_project(root: pathlib.Path, site_url_override: str | None = None) -> Project:
    root = root.resolve()
    site_path = root / "src" / SITE_FILENAME
    if not site_path.is_file():
        raise SystemExit(f"{site_path} not found: not a static-web-platform app")
    site = json.loads(site_path.read_text(encoding="utf-8"))
    missing = [key for key in REQUIRED_SITE_KEYS if key not in site]
    if missing:
        raise SystemExit(f"{site_path}: missing keys {', '.join(missing)}")
    expand_net_origins_from(site, root, site_path)
    validate_net_origins(site["netOrigins"], site_path)
    validate_support(site.get("support"), site_path)
    for mode in site.get("modes", []):
        # Invariant: a declared mode is a folder of core/ — a typo would silently
        # leave the real folder unprotected.
        if not (root / "src" / "core" / mode).is_dir():
            raise SystemExit(f'{site_path}: "modes": core/{mode}/ does not exist')
    for name, entry in site.get("workers", {}).items():
        if not re.fullmatch(r"[a-z][a-z0-9-]*", name):
            raise SystemExit(f"{site_path}: worker name '{name}' must be lower-case letters, digits, '-'")
        if not (root / entry).is_file():
            raise SystemExit(f"{site_path}: worker '{name}' entry {entry} not found")
    if site_url_override is not None:
        site["siteUrl"] = site_url_override
    if site["siteUrl"] and not site["siteUrl"].endswith("/"):
        site["siteUrl"] += "/"
    platform = root / "node_modules" / PLATFORM_PACKAGE_NAME
    # Invariant: the platform is installed from the app's lockfile (npm ci);
    # building against anything else would make the output irreproducible.
    if not platform.exists():
        raise SystemExit(f"{platform} missing: run `mise exec -- npm ci` first")
    return Project(root=root, site=site, platform_dir=platform.resolve())
