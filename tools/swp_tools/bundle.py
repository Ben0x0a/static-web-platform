"""bundle.py — type check and bundle the app (the framework-agnostic contract).

Defines : typecheck(), bundle_app(), bundle_cli(), bundle_launcher(), AppBundle.
Used by : builder.py.
Uses    : the app's node_modules/.bin/tsc and esbuild (pinned in the app's
          lockfile), or the app's own build command (site.json "appBuild").

THE CONTRACT with any app, whatever its framework: produce, in one folder,
  app.js   — ONE self-contained script (all imports bundled, platform included),
             loadable as a classic <script> (IIFE) or inline;
  app.css  — optional, the app's styles (component CSS included).
  workers/<name>.js — one self-contained script per site.json "workers" entry.
The command-line shell (site.json "cli") and the local-server launcher are
always bundled by esbuild (ES modules for Deno), whatever builds app.js.
Default: esbuild bundles site.json "entry" (src/main.ts|tsx) — TypeScript,
JSX (React/Preact) and CSS imports work out of the box. Svelte/Vue apps set
"appBuild": {"command": [...], "outDir": "..."} (e.g. Vite in library/IIFE
mode); the command gets SWP_OUT_DIR in its environment.
"""

import dataclasses
import json
import os
import pathlib
import re
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


EMBEDDED_ASSET_TYPES = ("png", "jpg", "jpeg", "gif", "webp", "avif", "svg", "ico", "woff", "woff2", "ttf", "otf")
CORE_RUNTIME_TYPES = pathlib.Path(__file__).resolve().parent / "core-runtime.d.ts"


def check_node(project: Project) -> None:
    """The Node.js on PATH must be the version pinned in the app's mise.toml.

    WHY: npm ships with Node, and npm versions differ in how they link package
    binaries (Node 24.19.0's npm did not link esbuild). A pinned EXACT version
    makes every machine and CI install and build the same way.
    """
    mise = project.root / "mise.toml"
    pinned = re.search(r'^node\s*=\s*"([^"]+)"', mise.read_text(encoding="utf-8"), re.MULTILINE) if mise.is_file() else None
    if not pinned:
        return
    # Invariant: an exact x.y.z pin — "24" floats to whatever 24.x is newest,
    # which is how two machines ended up with npm versions that link differently.
    if not re.fullmatch(r"\d+\.\d+\.\d+", pinned.group(1)):
        raise SystemExit(f'mise.toml: pin an exact Node version (e.g. node = "24.21.0"), not "{pinned.group(1)}"')
    try:
        running = subprocess.run(["node", "--version"], capture_output=True, text=True).stdout.strip().lstrip("v")
    except OSError:
        raise SystemExit("node not on PATH: run through mise, e.g. `mise exec -- npx swp build`")
    if running != pinned.group(1):
        raise SystemExit(f"Node {running} on PATH, but mise.toml pins {pinned.group(1)}: "
                         "run through mise (`mise exec -- npx swp build`), then `npm ci`")


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
    check_pure_layers(project)


PURE_PROGRAMS = (
    # (label, folders under src/, run only when this folder exists or None for
    # "any of them"): each one type-checked on its own, WITHOUT the DOM library
    # and with only core-runtime.d.ts as extra runtime API.
    ("core and api (no DOM, no I/O)", ("core", "api"), None),
    # cli/ gets the Deno file and stream APIs through the platform's CLI entry
    # (its triple-slash reference to deno-io.d.ts) and nothing else: no fetch,
    # no sockets. A separate program, so the first one checks core/ and api/
    # without Deno; core/ and api/ are included here too only so that their own
    # declaration files (e.g. types for an untyped npm package) are loaded.
    ("cli (Deno file and stream APIs only, no network)", ("core", "api", "cli"), "cli"),
)


def check_pure_layers(project: Project) -> None:
    """Type-check the layers that must run outside a page WITHOUT the DOM library.

    WHY: core/ and api/ must run in the page, in workers, in Node (unit tests)
    and in Deno (the CLI); cli/ must never reach the network. A type check
    against a curated list of runtime APIs is a precise, zero-maintenance way
    to prove both: anything not declared (document, fetch, sockets…) fails.
    """
    config_dir = project.root / "build"
    for index, (label, folders, required) in enumerate(PURE_PROGRAMS):
        present = [folder for folder in folders if (project.src / folder).is_dir()]
        if not present or (required is not None and required not in present):
            continue
        config_dir.mkdir(exist_ok=True)
        config = config_dir / f"tsconfig.pure-{index}.json"
        config.write_text(json.dumps({
            "extends": "../tsconfig.json",
            "compilerOptions": {"lib": ["es2023"], "types": [], "noEmit": True},
            # core-runtime.d.ts: the few non-DOM runtime APIs these layers may
            # use (TextEncoder/Decoder, structuredClone, crypto) — see that file.
            "include": [*(f"../src/{folder}/**/*.ts" for folder in present), str(CORE_RUNTIME_TYPES)],
        }, indent=2), encoding="utf-8")
        _run([_bin(project, "tsc"), "-p", str(config)], project, f"purity check of {label}")


def _esbuild(project: Project, entry: pathlib.Path, outfile: pathlib.Path, options: list[str]) -> None:
    _run([_bin(project, "esbuild"), str(entry), "--bundle", "--target=es2022",
          "--charset=utf8", "--legal-comments=inline", "--log-level=warning",
          # Keep node_modules/... paths (not the symlink target) in the bundle's
          # source comments: no local path leaks into the published file, and
          # the output is identical on every machine (swp verify in CI).
          "--preserve-symlinks", *options, f"--outfile={outfile}"], project, "esbuild")


def _read_bundle(project: Project, entry: pathlib.Path, name: str, options: list[str]) -> str:
    out = project.root / "build" / "deno" / name
    out.parent.mkdir(parents=True, exist_ok=True)
    _esbuild(project, entry, out, options)
    return out.read_text(encoding="utf-8")


# --platform=neutral leaves main-fields empty: packages that declare only "main"
# (no "exports") would not resolve. List them as the browser platform would.
DENO_OPTIONS = ["--format=esm", "--platform=neutral", "--main-fields=module,main"]


def bundle_cli(project: Project, version: str, date: str) -> str:
    """The command-line shell + the app's api/ in one ES module for Deno.

    The same file is the CLI (`deno run … <id>-cli.js <command>`) and the
    app's library (`import { … } from "./<id>-cli.js"`): cli/deno.ts starts
    the command line only when the module is the program's entry point.
    """
    assert project.cli_entry is not None, "Invariant violated: bundle_cli called without site.json cli"
    defines = [f"--define:__SWP_VERSION__={json.dumps(version)}", f"--define:__SWP_DATE__={json.dumps(date)}"]
    return _read_bundle(project, project.cli_entry, project.cli_filename, [*DENO_OPTIONS, *defines])


LAUNCHER_ENTRY = pathlib.Path("src") / "launcher" / "serve.ts"


def bundle_launcher(project: Project) -> str:
    """The platform's local-server launcher (distribution "local-server"), for Deno."""
    return _read_bundle(project, project.platform_dir / LAUNCHER_ENTRY, "serve.js", DENO_OPTIONS)


def bundle_app(project: Project) -> AppBundle:
    out = project.app_build_dir
    if out.exists():
        shutil.rmtree(out)                      # no stale files from a previous build
    out.mkdir(parents=True)
    if project.app_build_command:
        _run(project.app_build_command, project, "app build command", env={**os.environ, "SWP_OUT_DIR": str(out)})
    else:
        page_options = ["--format=iife",
                        # Images and fonts referenced from CSS (e.g. a library's stylesheet)
                        # are embedded as data: URLs — they then work in both outputs,
                        # including the single file, with no extra request.
                        *(f"--loader:.{ext}=dataurl" for ext in EMBEDDED_ASSET_TYPES)]
        _esbuild(project, project.entry, out / "app.js", page_options)
        for name, entry in project.workers.items():
            _esbuild(project, entry, out / "workers" / f"{name}.js", page_options)
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
