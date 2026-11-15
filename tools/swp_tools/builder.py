"""builder.py — build / check / verify orchestration.

Defines : build(), build_dev(), check(), verify().
Used by : cli.py (`swp build|check|verify`), gate.py (fresh test builds).
Uses    : config, version, bundle, assemble, package, credentials.

Outputs in public/: index.html + config.js + app.js + base.css (+ app.css) +
sw.js + manifest.webmanifest + _headers + icons/ (hosted site); the local
copies chosen by site.json "distribution" — the single file (<downloadName>),
plus <id>-local.zip (local server, and the command line when the app has one)
for "local-server" or any app with "cli", none for "site-only"; and
version.json (version, date, each published copy and its SHA-256).
"""

import datetime
import hashlib
import json
import logging
import pathlib
import shutil
import tempfile

from swp_tools.assemble import (VERSION_FILENAME, config_js, headers_file, manifest_json, platform_css,
                                render_page, service_worker)
from swp_tools.arch import check_architecture
from swp_tools.bundle import AppBundle, bundle_app, bundle_cli, bundle_launcher, check_node, typecheck
from swp_tools.config import Project, load_project
from swp_tools.credentials import check_secrets
from swp_tools.data import check_datasets, resolve_assets
from swp_tools.package import local_zip
from swp_tools.version import source_version

_LOG = logging.getLogger("swp.build")
ICON_FILES = ("icon.svg", "icon-192.png", "icon-512.png", "apple-touch-icon.png")


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _shared_files(project: Project, bundle: AppBundle, assets: list[str]) -> dict[str, bytes]:
    """Files identical on the hosted site and in the local-server copy (read once)."""
    files: dict[str, bytes] = {
        "app.js": bundle.js.encode("utf-8"),
        "base.css": platform_css(project).encode("utf-8"),
        "manifest.webmanifest": manifest_json(project.site).encode("utf-8"),
    }
    if bundle.css:
        files["app.css"] = bundle.css.encode("utf-8")
    for name, code in bundle.workers.items():
        files[f"workers/{name}.js"] = code.encode("utf-8")
    for name in ICON_FILES:
        source = project.src / "icons" / name
        if not source.is_file():
            raise SystemExit(f"{source} missing (render the PNGs with `swp icons`)")
        files[f"icons/{name}"] = source.read_bytes()
    for asset in assets:                         # served files only (never in the single file)
        files[asset] = (project.src / asset).read_bytes()
    return files


def _page_files(project: Project, mode: str, bundle: AppBundle, version: str, date: str,
                assets: list[str]) -> dict[str, bytes]:
    """What differs between the hosted site ("site") and the local-server copy ("local")."""
    return {
        "index.html": render_page(project, mode, bundle, version, date, assets).encode("utf-8"),
        "config.js": config_js(project, mode, version, date, assets).encode("utf-8"),
        # The local copy keeps the security headers (the launcher applies them)
        # but has no download of its own.
        "_headers": headers_file([name for name in (project.download_filename, project.local_zip_filename)
                                  if name and mode == "site"]).encode("utf-8"),
    }


def build(project: Project, out: pathlib.Path, date: str | None = None) -> None:
    check_node(project)
    check_architecture(project)
    assets = resolve_assets(project)
    check_datasets(project, assets)
    typecheck(project)
    bundle = bundle_app(project)
    version = source_version(project)
    date = date or datetime.date.today().isoformat()
    if out.exists():
        # Invariant: only ever wipe a folder this tool produced (it holds
        # version.json) or an empty one — a wrong --out must never delete data.
        if any(out.iterdir()) and not (out / VERSION_FILENAME).is_file():
            raise SystemExit(f"Refusing to overwrite {out}: not a build output (no {VERSION_FILENAME})")

    shared = _shared_files(project, bundle, assets)
    files = {**shared, **_page_files(project, "site", bundle, version, date, assets)}
    precache = ["./", "config.js", "app.js", "base.css", *(["app.css"] if bundle.css else []),
                "manifest.webmanifest", *(f"icons/{name}" for name in ICON_FILES),
                *(f"workers/{name}.js" for name in sorted(bundle.workers)),
                *(assets if project.precache_assets else [])]
    files["sw.js"] = service_worker(project, version, precache).encode("utf-8")
    download = project.download_filename
    if download:
        files[download] = render_page(project, "single", bundle, version, date, assets).encode("utf-8")
    zip_name = project.local_zip_filename
    local: dict[str, bytes] = {}
    cli = None
    if zip_name:
        local = {**shared, **_page_files(project, "local", bundle, version, date, assets)}
        cli = bundle_cli(project, version, date) if project.cli_entry is not None else None
    # Invariant: nothing is wiped or written before the scan — a key must never
    # reach public/, and a refused build leaves the previous one in place.
    check_secrets({**files, **{f"{zip_name}: {name}": data for name, data in local.items()},
                   **({f"{zip_name}: {project.cli_filename}": cli.encode("utf-8")} if cli else {})})
    if out.exists():
        shutil.rmtree(out)
    for name, data in files.items():
        (out / name).parent.mkdir(parents=True, exist_ok=True)
        (out / name).write_bytes(data)
    if zip_name:
        local_zip(project, local, bundle_launcher(project), cli, out / zip_name)

    download_sha = _sha256(out / download) if download else None
    local_copy = {"file": zip_name, "sha256": _sha256(out / zip_name)} if zip_name else None
    (out / VERSION_FILENAME).write_text(json.dumps({
        "version": version, "date": date, "download": download, "sha256": download_sha,
        "local": local_copy,
    }, indent=2) + "\n", encoding="utf-8", newline="\n")
    if not project.site["siteUrl"]:
        _LOG.warning("site.json siteUrl is empty: local copies will not offer update checks")
    _LOG.info(f"Built {out} — version {version}; distribution {project.distribution}"
              + (f", download {download} sha256 {download_sha}" if download else "")
              + (f", local {zip_name}" + (" (with cli)" if project.cli_entry else "") if zip_name else "")
              + f"; app.js {len(bundle.js.encode('utf-8')):,} bytes, app.css {len(bundle.css.encode('utf-8')):,} bytes")


def build_dev(project: Project, out: pathlib.Path) -> None:
    """Write only what a framework dev server cannot produce: config.js (mode
    "dev": no service worker, no install/download) and the platform's base.css. Point the dev server's
    static folder at `out` (e.g. Vite publicDir) and load both from the dev page.
    """
    out.mkdir(parents=True, exist_ok=True)
    assets = resolve_assets(project)
    (out / "config.js").write_text(config_js(project, "dev", "dev", datetime.date.today().isoformat(), assets),
                                   encoding="utf-8")
    (out / "base.css").write_text(platform_css(project), encoding="utf-8")
    _LOG.info(f"Dev files written to {out} (config.js, base.css)")


def check(project: Project, out: pathlib.Path) -> int:
    path = out / VERSION_FILENAME
    built = json.loads(path.read_text(encoding="utf-8"))["version"] if path.is_file() else None
    current = source_version(project)
    if built != current:
        _LOG.error(f"{out} is out of date (built {built}, sources {current}): run `npx swp build`")
        return 1
    _LOG.info(f"{out} is up to date (version {current})")
    return 0


def _files(root: pathlib.Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*")
            if p.is_file() and p.name != ".DS_Store"}


def verify(project: Project, out: pathlib.Path) -> int:
    """Rebuild into a temporary folder; require `out` to be byte-for-byte identical.

    WHY: check() only proves the version matches the sources; this proves the
    published files ARE what the sources produce — no hand edit, reproducible
    build. The date is the only input not derived from the sources, so it is
    taken from out/version.json.
    """
    if check(project, out) != 0:
        return 1
    built = json.loads((out / VERSION_FILENAME).read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="swp_verify_") as tmp:
        fresh = pathlib.Path(tmp) / "public"
        build(load_project(project.root), fresh, date=built["date"])
        published, rebuilt = _files(out), _files(fresh)
    differences = sorted(
        [f"only in {out.name}/: {n}" for n in published.keys() - rebuilt.keys()]
        + [f"missing from {out.name}/: {n}" for n in rebuilt.keys() - published.keys()]
        + [f"differs: {n}" for n in published.keys() & rebuilt.keys() if published[n] != rebuilt[n]])
    if differences:
        _LOG.error(f"{out.name}/ is not what src/ builds to:\n  " + "\n  ".join(differences))
        return 1
    _LOG.info(f"{out} is byte-for-byte identical to a fresh rebuild ({len(published)} files)")
    return 0
