"""arch.py — enforce the app's layer rules ("bricks around a pure core") on every build.

Defines : check_architecture(), layer_of(), LAYER_RULES.
Used by : builder.py (before type checking; violations stop the build).
Uses    : the app's src/ tree (imports read with regular expressions from
          .ts/.tsx/.js/.jsx/.mts/.svelte/.vue files).

Layers (by first folder under src/; anything else at the root is "app"):
  data      bundled datasets (src/data/*.json + SOURCES.md): imported ONLY by
            core, through a typed loader that a unit test pins.
  core      pure domain: may import only core and data (and pure npm packages); a
            core/<mode>/ folder never imports another core/<mode>/.
            No DOM either: checked separately by type-checking core/ without
            the DOM library (bundle.check_core_is_pure).
  ui        shared display helpers: core, ui, the platform.
  state     shared state/stores: core, state, the platform.
  features  one capability each: core, ui, state, the platform, and its OWN
            files (features/<name>.ts, features/<name>/…) — never another feature.
  workers   Web Worker entries: core, workers (no platform, no DOM).
  app       main.ts, content.ts, migrations…: anything.
The platform is imported only as "static-web-platform" (its public API),
never by deep path.
"""

import pathlib
import re

from swp_tools.config import PLATFORM_PACKAGE_NAME, Project

SOURCE_SUFFIXES = {".ts", ".tsx", ".js", ".jsx", ".mts", ".svelte", ".vue"}
LAYERS = ("core", "data", "ui", "state", "features", "workers")
LAYER_RULES: dict[str, set[str]] = {
    "core": {"core", "data"},
    "data": set(),
    "ui": {"core", "ui", "platform"},
    "state": {"core", "state", "platform"},
    "features": {"core", "ui", "state", "platform", "features"},   # features: own folder only (below)
    "workers": {"core", "workers"},
    "app": {"core", "ui", "state", "features", "workers", "platform", "app"},   # not data: go through core
}
IMPORT_PATTERNS = [
    re.compile(r"""(?:import|export)\s[^'";]*?\sfrom\s*['"]([^'"]+)['"]"""),
    re.compile(r"""import\s*['"]([^'"]+)['"]"""),
    re.compile(r"""import\(\s*['"]([^'"]+)['"]\s*\)"""),
]


def layer_of(relative: pathlib.PurePosixPath) -> str:
    return relative.parts[0] if len(relative.parts) > 1 and relative.parts[0] in LAYERS else "app"


def _feature_name(relative: pathlib.PurePosixPath) -> str:
    """features/notes.ts, features/notes.css, features/notes/tabs.ts → "notes"."""
    return relative.parts[1].split(".")[0]


def _core_mode(relative: pathlib.PurePosixPath) -> str | None:
    """core/identifiers/x.ts → "identifiers"; core/types.ts → None (shared root)."""
    return relative.parts[1] if len(relative.parts) > 2 else None


def _imports(path: pathlib.Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [m.group(1) for pattern in IMPORT_PATTERNS for m in pattern.finditer(text)]


def check_architecture(project: Project) -> None:
    src = project.src
    problems: list[str] = []
    for path in sorted(p for p in src.rglob("*") if p.suffix in SOURCE_SUFFIXES and p.is_file()):
        rel = pathlib.PurePosixPath(path.relative_to(src).as_posix())
        layer = layer_of(rel)
        for spec in _imports(path):
            if spec.startswith("."):
                target_path = (path.parent / spec).resolve()
                try:
                    target = pathlib.PurePosixPath(target_path.relative_to(src.resolve()).as_posix())
                except ValueError:
                    problems.append(f"{rel}: imports {spec} outside src/")
                    continue
                if target.suffix == ".css":
                    continue                                   # styles are not dependencies
                target_layer = layer_of(target)
                if target_layer not in LAYER_RULES[layer]:
                    problems.append(f"{rel} ({layer}) may not import {target} ({target_layer})")
                elif layer == "features" and target_layer == "features" and _feature_name(rel) != _feature_name(target):
                    problems.append(f"{rel}: features never import other features ({target}) — compose in main.ts")
                elif layer == "core" and _core_mode(rel) and _core_mode(target) and _core_mode(rel) != _core_mode(target):
                    problems.append(f"{rel}: core modes never import each other ({target}) — share via core/ root")
            elif spec == PLATFORM_PACKAGE_NAME or spec.startswith(PLATFORM_PACKAGE_NAME + "/"):
                if spec != PLATFORM_PACKAGE_NAME:
                    problems.append(f"{rel}: import the platform's public API only ('{PLATFORM_PACKAGE_NAME}'), not {spec}")
                elif "platform" not in LAYER_RULES[layer]:
                    problems.append(f"{rel} ({layer}) may not use the platform")
            # other bare specifiers: npm packages (pure ones are fine in core; DOM use is caught by the core check)
    if problems:
        raise SystemExit("Architecture rules broken (static-web-app skill, dependency rules):\n  " + "\n  ".join(problems))
