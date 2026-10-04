"""version.py — the app's version: a fingerprint of everything that shapes the output.

Defines : source_version(), fingerprint_files().
Used by : builder.py (stamped into config.js and version.json; --check).
Uses    : config.Project.

WHY include the platform's files (not just its version string): with a local
file: dependency the lockfile does not change when the platform's code does,
so only hashing the files guarantees "same version ⇔ same output".
"""

import hashlib
import pathlib

from swp_tools.config import Project

APP_TOOLCHAIN_FILES = ("package.json", "package-lock.json", "tsconfig.json")
# Build configuration of framework apps (vite.config.ts, svelte.config.js, …):
# it shapes the output, so it must change the version too.
ROOT_CONFIG_GLOBS = ("*.config.js", "*.config.ts", "*.config.mjs", "*.config.cjs", "*.config.mts", "*.config.cts")
PLATFORM_PARTS = ("src", "tools/swp_tools", "package.json")
IGNORED_NAMES = {".DS_Store", "__pycache__", "node_modules"}


def fingerprint_files(project: Project) -> list[tuple[str, pathlib.Path]]:
    """(label, path) of every input, in a stable order."""
    def tree(base: pathlib.Path, label: str) -> list[tuple[str, pathlib.Path]]:
        if base.is_file():
            return [(label, base)]
        return [(f"{label}/{p.relative_to(base)}", p) for p in sorted(base.rglob("*"))
                if p.is_file() and not IGNORED_NAMES.intersection(p.parts)]
    files = tree(project.src, "src")
    files += [(name, project.root / name) for name in APP_TOOLCHAIN_FILES if (project.root / name).is_file()]
    extra = {p for pattern in ROOT_CONFIG_GLOBS for p in project.root.glob(pattern) if p.is_file()}
    for pattern in project.app_build_inputs:            # site.json appBuild.inputs
        matched = [p for p in project.root.glob(pattern) if p.is_file()]
        # Invariant: a declared input that matches nothing is a typo — silently
        # skipping it would let that file change without changing the version.
        if not matched:
            raise SystemExit(f"site.json appBuild.inputs: '{pattern}' matches no file")
        extra.update(matched)
    files += [(str(p.relative_to(project.root)), p) for p in sorted(extra)]
    for part in PLATFORM_PARTS:
        files += tree(project.platform_dir / part, f"platform/{part}")
    return files


def source_version(project: Project) -> str:
    digest = hashlib.sha256()
    for label, path in fingerprint_files(project):
        digest.update(label.encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()[:12]
