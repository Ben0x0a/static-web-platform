"""bundle.py — type check and bundle the app (the framework-agnostic contract).

Defines : typecheck(), bundle_app(), AppBundle.
Used by : builder.py.
Uses    : the app's node_modules/.bin/tsc and esbuild (pinned in the app's
          lockfile), or the app's own build command (site.json "appBuild").

THE CONTRACT with any app, whatever its framework: produce, in one folder,
  app.js   — ONE self-contained script (all imports bundled, platform included),
             loadable as a classic <script> (IIFE) or inline;
  app.css  — optional, the app's styles (component CSS included).
  workers/<name>.js — one self-contained script per site.json "workers" entry.
Default: esbuild bundles site.json "entry" (src/main.ts|tsx) — TypeScript,
JSX (React/Preact) and CSS imports work out of the box. Svelte/Vue apps set
"appBuild": {"command": [...], "outDir": "..."} (e.g. Vite in library/IIFE
mode); the command gets SWP_OUT_DIR in its environment.
"""

import dataclasses
import json
import os
import pathlib
import shutil
import subprocess

from swp_tools.config import Project


@dataclasses.dataclass(frozen=True)
class AppBundle:
    js: str
    css: str                    # "" when the app has no CSS
    workers: dict[str, str]     # worker name → self-contained script


def _run(cmd: list[str], project: Project, what: str, env: dict | None = None) -> None:
    try:
        result = subprocess.run(cmd, cwd=project.root, capture_output=True, text=True, env=env)
    except OSError as err:                      # e.g. `node` not on PATH
        raise SystemExit(f"Cannot run {what} ({err}): put Node.js on PATH, e.g. `mise exec -- npx swp build`")
    if result.returncode != 0:
        raise SystemExit(f"{what} failed:\n{result.stdout}{result.stderr}")


def _bin(project: Project, name: str) -> str:
    path = project.root / "node_modules" / ".bin" / name
    # Invariant: tools come from the app's lockfile, never a global install —
    # otherwise two machines could build different output.
    if not path.exists():
        raise SystemExit(f"{name} missing from node_modules/.bin: add it to devDependencies and run `npm ci`")
    return str(path)


def typecheck(project: Project) -> None:
    """Strict type check of the app AND the platform it imports.

    Default: tsc --noEmit. Framework apps set site.json "typecheck":
    {"command": [...]} (e.g. svelte-check, vue-tsc), which replaces it.
    """
    command = project.site.get("typecheck", {}).get("command")
    if command:
        _run(command, project, "type check command")
    else:
        _run([_bin(project, "tsc"), "-p", "tsconfig.json", "--noEmit"], project, "TypeScript type check")
    check_core_is_pure(project)


def check_core_is_pure(project: Project) -> None:
    """Type-check src/core/ WITHOUT the DOM library: any DOM use there fails.

    WHY: core/ must stay testable without a browser (Node test runner) and
    reusable by workers; a type check is a precise, zero-maintenance way to
    prove it never touches document, window, HTMLElement…
    """
    core = project.src / "core"
    if not core.is_dir():
        return
    config_dir = project.root / "build"
    config_dir.mkdir(exist_ok=True)
    config = config_dir / "tsconfig.core.json"
    config.write_text(json.dumps({
        "extends": "../tsconfig.json",
        "compilerOptions": {"lib": ["es2023"], "types": [], "noEmit": True},
        "include": ["../src/core/**/*.ts"],
    }, indent=2), encoding="utf-8")
    _run([_bin(project, "tsc"), "-p", str(config)], project, "core purity check (no DOM in src/core)")


def bundle_app(project: Project) -> AppBundle:
    out = project.app_build_dir
    if out.exists():
        shutil.rmtree(out)                      # no stale files from a previous build
    out.mkdir(parents=True)
    if project.app_build_command:
        _run(project.app_build_command, project, "app build command", env={**os.environ, "SWP_OUT_DIR": str(out)})
    else:
        esbuild = lambda entry, outfile: _run(  # noqa: E731
            [_bin(project, "esbuild"), str(entry), "--bundle", "--format=iife", "--target=es2022",
             "--charset=utf8", "--legal-comments=inline", "--log-level=warning",
             # Keep node_modules/... paths (not the symlink target) in the bundle's
             # source comments: no local path leaks into the published file, and
             # the output is identical on every machine (swp verify in CI).
             "--preserve-symlinks",
             f"--outfile={outfile}"], project, "esbuild")
        esbuild(project.entry, out / "app.js")
        for name, entry in project.workers.items():
            esbuild(entry, out / "workers" / f"{name}.js")
    js_path, css_path = out / "app.js", out / "app.css"
    if not js_path.is_file():
        raise SystemExit(f"The app build did not produce {js_path} (see the contract in bundle.py)")
    workers = {}
    for name in project.workers:
        worker_path = out / "workers" / f"{name}.js"
        if not worker_path.is_file():
            raise SystemExit(f"The app build did not produce {worker_path} (declared in site.json workers)")
        workers[name] = worker_path.read_text(encoding="utf-8")
    return AppBundle(js=js_path.read_text(encoding="utf-8"),
                     css=css_path.read_text(encoding="utf-8") if css_path.is_file() else "", workers=workers)
