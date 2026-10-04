"""builder.py — build / check / verify orchestration.

Defines : build(), check(), verify().
Used by : cli.py (`swp build|check|verify`), gate.py (fresh test builds).
Uses    : config, version, bundle, assemble.

Outputs in public/: index.html + config.js + app.js + base.css (+ app.css) +
sw.js + manifest.webmanifest + _headers + icons/ (hosted site), the
single-file download (<downloadName>), and version.json.
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
from swp_tools.bundle import bundle_app, typecheck
from swp_tools.config import Project, load_project
from swp_tools.data import check_datasets, resolve_assets
from swp_tools.version import source_version

_LOG = logging.getLogger("swp.build")
ICON_FILES = ("icon.svg", "icon-192.png", "icon-512.png", "apple-touch-icon.png")


def build(project: Project, out: pathlib.Path, date: str | None = None) -> None:
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
        shutil.rmtree(out)
    (out / "icons").mkdir(parents=True)
    for name in ICON_FILES:
        source = project.src / "icons" / name
        if not source.is_file():
            raise SystemExit(f"{source} missing (render the PNGs with `swp icons`)")
        shutil.copy2(source, out / "icons" / name)

    site = project.site
    files = {
        "index.html": render_page(project, "site", bundle, version, date, assets),
        "config.js": config_js(site, "site", version, date, assets),
        "app.js": bundle.js,
        "base.css": platform_css(project),
        "manifest.webmanifest": manifest_json(site),
        "_headers": headers_file(site),
    }
    if bundle.css:
        files["app.css"] = bundle.css
    for name, code in bundle.workers.items():
        files[f"workers/{name}.js"] = code
    for asset in assets:                         # hosted site only (never in the single file)
        (out / asset).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(project.src / asset, out / asset)
    single = render_page(project, "single", bundle, version, date, assets)
    files[site["downloadName"]] = single
    precache = ["./", "config.js", "app.js", "base.css", *(["app.css"] if bundle.css else []),
                "manifest.webmanifest", *(f"icons/{name}" for name in ICON_FILES),
                *(f"workers/{name}.js" for name in sorted(bundle.workers)),
                *(assets if project.precache_assets else [])]
    files["sw.js"] = service_worker(project, version, precache)
    sha256 = hashlib.sha256(single.encode("utf-8")).hexdigest()
    files[VERSION_FILENAME] = json.dumps({"version": version, "date": date, "download": site["downloadName"],
                                          "sha256": sha256}, indent=2) + "\n"
    for name, text in files.items():
        (out / name).parent.mkdir(parents=True, exist_ok=True)
        (out / name).write_text(text, encoding="utf-8")
    if not site["siteUrl"]:
        _LOG.warning("site.json siteUrl is empty: the downloaded file will not offer update checks")
    _LOG.info(f"Built {out} — version {version}; download {site['downloadName']} sha256 {sha256}")


def build_dev(project: Project, out: pathlib.Path) -> None:
    """Write only what a framework dev server cannot produce: config.js (mode
    "site", version "dev") and the platform's base.css. Point the dev server's
    static folder at `out` (e.g. Vite publicDir) and load both from the dev page.
    """
    out.mkdir(parents=True, exist_ok=True)
    assets = resolve_assets(project)
    (out / "config.js").write_text(config_js(project.site, "site", "dev", datetime.date.today().isoformat(), assets),
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
