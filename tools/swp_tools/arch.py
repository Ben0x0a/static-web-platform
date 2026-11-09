"""arch.py — enforce the app's layer rules ("bricks around a pure core") on every build.

Defines : check_architecture(), layer_of(), LAYER_RULES.
Used by : builder.py (before type checking; violations stop the build).
Uses    : the app's src/ tree (imports read with regular expressions from
          .ts/.tsx/.js/.jsx/.mts/.svelte/.vue files).

Layers (by first folder under src/; anything else at the root is "app"):
  data      bundled datasets (src/data/*.json + SOURCES.md): imported ONLY by
            core, through a typed loader that a unit test pins.
  core      pure domain: may import only core and data (and pure npm packages).
            Sub-folders are plain organisation and import each other freely,
            EXCEPT the modes declared in site.json "modes": a core/<mode>/ folder
            never imports another declared mode (shared code lives outside them).
            No DOM either: checked separately by type-checking core/ without
            the DOM library (bundle.check_pure_layers).
  ui        shared display helpers: core, ui, the platform.
  state     shared state/stores: core, state, the platform.
  features  one capability each: core, ui, state, the platform, and its OWN
            files (features/<name>.ts, features/<name>/…) — never another feature.
  workers   Web Worker entries: core, api, workers (no platform, no DOM).
  api       the app's operations (its programmatic API): core, api. Pure and
            runtime-neutral, type-checked without the DOM like core/.
  cli       the command-line shell: api, core, cli, and the platform's CLI
            entry "static-web-platform/cli" only. Type-checked without the DOM
            and with only the Deno file and stream APIs, so network code fails.
  app       main.ts, content.ts, migrations…: anything except data/ and cli/.
The platform is imported only through its public entries: "static-web-platform"
(page layers) and "static-web-platform/cli" (cli/), never by deep path.
"""

import pathlib
import re

from swp_tools.config import PLATFORM_CLI_ENTRY, PLATFORM_PACKAGE_NAME, Project

SOURCE_SUFFIXES = {".ts", ".tsx", ".js", ".jsx", ".mts", ".svelte", ".vue"}
LAYERS = ("core", "data", "api", "cli", "ui", "state", "features", "workers")
LAYER_RULES: dict[str, set[str]] = {
    "core": {"core", "data"},
    "data": set(),
    "ui": {"core", "ui", "platform"},
    "state": {"core", "state", "platform"},
    "api": {"core", "api"},
    "cli": {"api", "core", "cli", "platform-cli"},
    "features": {"core", "api", "ui", "state", "platform", "features"},   # features: own folder only (below)
    "workers": {"core", "api", "workers"},
    "app": {"core", "api", "ui", "state", "features", "workers", "platform", "app"},   # not data, not cli
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


def _core_mode(relative: pathlib.PurePosixPath, modes: set[str]) -> str | None:
    """core/identifiers/x.ts → "identifiers" when declared as a mode; otherwise None."""
    return relative.parts[1] if len(relative.parts) > 2 and relative.parts[1] in modes else None


def _imports(path: pathlib.Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [m.group(1) for pattern in IMPORT_PATTERNS for m in pattern.finditer(text)]


def check_architecture(project: Project) -> None:
    src = project.src
    modes = set(project.site.get("modes", []))
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
                elif (layer == "core" and _core_mode(rel, modes) and _core_mode(target, modes)
                      and _core_mode(rel, modes) != _core_mode(target, modes)):
                    problems.append(f"{rel}: modes never import each other ({target}) — share via code outside the modes")
            elif spec == PLATFORM_PACKAGE_NAME or spec.startswith(PLATFORM_PACKAGE_NAME + "/"):
                entry = {PLATFORM_PACKAGE_NAME: "platform", PLATFORM_CLI_ENTRY: "platform-cli"}.get(spec)
                if entry is None:
                    problems.append(f"{rel}: import the platform's public entries only ('{PLATFORM_PACKAGE_NAME}', "
                                    f"'{PLATFORM_CLI_ENTRY}'), not {spec}")
                elif entry not in LAYER_RULES[layer]:
                    problems.append(f"{rel} ({layer}) may not use '{spec}'")
            # other bare specifiers: npm packages (pure ones are fine in core; DOM use is caught by the core check)
    if problems:
        raise SystemExit("Architecture rules broken (static-web-app skill, dependency rules):\n  " + "\n  ".join(problems))
