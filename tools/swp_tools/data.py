"""data.py — local datasets and optional assets of an app (rules + resolution).

Defines : resolve_assets(), check_datasets(), DATA_BUDGET_BYTES.
Used by : builder.py (before bundling).
Uses    : config.Project (src/data/, site.json "assets").

Rules (static-web-app skill, "Local datasets"):
- every file under src/data/ is named in src/data/SOURCES.md (source URL,
  retrieval date UTC, licence, SHA-256, update procedure);
- data bundled into app.js (both outputs) stays within DATA_BUDGET_BYTES;
  anything larger is declared in site.json "assets" (hosted site only).
"""

import pathlib

from swp_tools.config import Project

DATA_BUDGET_BYTES = 5_000_000          # bundled data (both outputs); larger → "assets"
SOURCES_FILENAME = "SOURCES.md"


def resolve_assets(project: Project) -> list[str]:
    """Asset files (paths relative to src/, sorted) matched by site.json "assets"."""
    found: set[str] = set()
    for pattern in project.site.get("assets", []):
        matched = [p for p in project.src.glob(pattern) if p.is_file()]
        # Invariant: a declared pattern matching nothing is a typo; the app would
        # then ask for a file that is never published.
        if not matched:
            raise SystemExit(f"site.json assets: '{pattern}' matches no file under src/")
        found.update(str(p.relative_to(project.src)) for p in matched)
    return sorted(found)


def check_datasets(project: Project, assets: list[str]) -> None:
    data_dir = project.src / "data"
    if not data_dir.is_dir():
        return
    files = [p for p in sorted(data_dir.rglob("*"))
             if p.is_file() and p.name not in (SOURCES_FILENAME, ".DS_Store")]
    sources = data_dir / SOURCES_FILENAME
    if files and not sources.is_file():
        raise SystemExit(f"{sources} missing: every dataset needs its source, date, licence and SHA-256")
    listed = sources.read_text(encoding="utf-8") if sources.is_file() else ""
    unlisted = [str(p.relative_to(project.src)) for p in files if p.name not in listed]
    if unlisted:
        raise SystemExit(f"Datasets not described in src/data/{SOURCES_FILENAME}: {', '.join(unlisted)}")
    bundled = sum(p.stat().st_size for p in files if str(p.relative_to(project.src)) not in assets)
    if bundled > DATA_BUDGET_BYTES:
        raise SystemExit(f"Bundled data is {bundled:,} bytes (> {DATA_BUDGET_BYTES:,}): move large files to "
                         'site.json "assets" (hosted site only)')
