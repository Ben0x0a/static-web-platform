"""cli.py — the `swp` command: parses arguments and dispatches (no logic here).

Defines : main().
Used by : bin/swp (installed as node_modules/.bin/swp in every app).
Uses    : builder.py, config.py, serve.py; gate.py and icons.py (Playwright —
          re-run through uvx when Playwright is not importable).

Commands (in workflow order):
  swp build  [--out DIR] [--site-url URL] [--date YYYY-MM-DD] [--dev]
  swp check                 public/ up to date with src/ (no Node needed)
  swp verify                public/ byte-for-byte equal to a fresh rebuild
  swp gate                  full verification gate (Chrome, axe-core, mobile)
  swp serve  [DIR] [PORT]   serve public/ with its _headers
  swp icons  [SVG]          render the PNG icons from src/icons/icon.svg
Run from the app's root folder, with Node.js on PATH (e.g. `mise exec -- npx swp build`).
"""

import argparse
import importlib.util
import logging
import os
import pathlib
import sys

PLAYWRIGHT_VERSION = "1.63.0"
PLAYWRIGHT_COMMANDS = {"gate", "icons"}


def _ensure_playwright(argv: list[str]) -> None:
    """Re-run this command under uvx with the pinned Playwright when it is missing."""
    if importlib.util.find_spec("playwright") is not None:
        return
    # Invariant: re-exec only once — if Playwright is still missing under uvx,
    # stop instead of looping.
    if os.environ.get("SWP_UNDER_UVX"):
        raise SystemExit("Playwright not importable even under uvx")
    os.environ["SWP_UNDER_UVX"] = "1"
    bin_path = str(pathlib.Path(__file__).resolve().parents[2] / "bin" / "swp")
    os.execvp("uvx", ["uvx", "--from", f"playwright=={PLAYWRIGHT_VERSION}", "python", bin_path, *argv])


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="swp", description="static-web-platform tools")
    commands = parser.add_subparsers(dest="command", required=True)
    build_cmd = commands.add_parser("build", help="type-check, bundle and assemble public/")
    build_cmd.add_argument("--out", type=pathlib.Path)
    build_cmd.add_argument("--site-url", help="override site.json siteUrl (tests)")
    build_cmd.add_argument("--date", help="build date YYYY-MM-DD (default: today)")
    build_cmd.add_argument("--dev", action="store_true",
                           help="only write config.js + base.css for a dev server (default --out build/dev)")
    commands.add_parser("check", help="public/ is up to date with src/")
    commands.add_parser("verify", help="public/ equals a fresh rebuild, byte for byte")
    commands.add_parser("gate", help="full verification gate")
    serve_cmd = commands.add_parser("serve", help="serve public/ with its _headers")
    serve_cmd.add_argument("directory", nargs="?", type=pathlib.Path, default=pathlib.Path("public"))
    serve_cmd.add_argument("port", nargs="?", type=int, default=8765)
    icons_cmd = commands.add_parser("icons", help="render PNG icons from the SVG")
    icons_cmd.add_argument("svg", nargs="?", type=pathlib.Path, default=pathlib.Path("src/icons/icon.svg"))
    args = parser.parse_args(argv)

    if args.command in PLAYWRIGHT_COMMANDS:
        _ensure_playwright(argv)
    root = pathlib.Path.cwd()
    if args.command == "build":
        from swp_tools.builder import build
        from swp_tools.config import load_project
        project = load_project(root, site_url_override=args.site_url)
        if args.dev:
            from swp_tools.builder import build_dev
            build_dev(project, (args.out or root / "build" / "dev").resolve())
            return 0
        build(project, (args.out or project.public).resolve(), date=args.date)
        return 0
    if args.command in ("check", "verify"):
        from swp_tools.builder import check, verify
        from swp_tools.config import load_project
        project = load_project(root)
        return (check if args.command == "check" else verify)(project, project.public)
    if args.command == "gate":
        from swp_tools.gate import run_gate
        report = run_gate(root)
        for status, name, detail in report.rows:
            print(f"{status.value:4}  {name}" + (f"\n      {detail}" if detail else ""))
        print("\nRESULT:", "FAIL" if report.failed else "PASS",
              "— then do the manual keyboard + screen-reader pass (static-web-app skill, references/accessibility.md)")
        return 1 if report.failed else 0
    if args.command == "serve":
        from swp_tools.serve import make_server
        server = make_server(args.directory.resolve(), args.port)
        logging.getLogger("swp").info(f"Serving {args.directory} at http://127.0.0.1:{server.server_port}/ (Ctrl+C to stop)")
        server.serve_forever()
        return 0
    if args.command == "icons":
        from swp_tools.icons import render
        render(args.svg.resolve())
        return 0
    raise AssertionError(f"Invariant violated: unhandled command {args.command}")
