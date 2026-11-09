"""package.py — the local-server copy as one reproducible zip (distribution "local-server").

Defines : local_zip(), default_port(), LAUNCH_COMMAND, PORT_BLOCK.
Used by : builder.py (public/<id>-local.zip); gate.py (unzips it to run the
          launcher); cors.py (the Origin a local-server copy sends).
Uses    : config.Project; the files of the "local" page (builder) and the
          bundled launcher (bundle.bundle_launcher).

Layout:  <id>-local/serve.js      the platform's launcher (Deno)
         <id>-local/serve.json    its default port and port block
         <id>-local/README.txt    how to start it
         <id>-local/public/…      the page and its files (mode "local")

WHY stored (no compression), a fixed date, sorted names and fixed attributes:
`swp verify` requires a byte-for-byte rebuild on any machine. Deflate output
depends on the zlib version, and zip entries otherwise carry the build time,
the file system's order and the operating system of the machine that made them.
"""

import hashlib
import json
import pathlib
import zipfile

from swp_tools.config import Project

LAUNCH_COMMAND = "deno run --no-config --no-prompt --allow-net=127.0.0.1 --allow-read=. serve.js"
# Local-server ports: a block the IANA service-name and port registry leaves
# unassigned (checked against its CSV on 2026-11-09), so no well-known service
# or common development tool uses it by default.
PORT_BLOCK = (29170, 29998)
ZIP_DATE = (1980, 1, 1, 0, 0, 0)          # the earliest date a zip entry can hold
UNIX_FILE_MODE = 0o644 << 16              # rw-r--r--, in the high bits of external_attr
UNIX_SYSTEM = 3                           # "made on Unix", whatever the build machine


def default_port(project: Project) -> int:
    """The app's own port in PORT_BLOCK, derived from its id.

    WHY per app and stable: the port is part of the page's origin, and the
    browser keeps saved data per origin — the same port at every start keeps
    that data reachable, and different apps' copies can run side by side.
    """
    first, last = PORT_BLOCK
    digest = hashlib.sha256(project.site["id"].encode("utf-8")).digest()
    return first + int.from_bytes(digest[:4], "big") % (last - first + 1)


def _readme(project: Project) -> str:
    site = project.site
    port = default_port(project)
    return f"""{site["title"]} — local copy

This folder runs the app on this computer only, at http://127.0.0.1:{port}/.
It needs Deno (https://deno.com). From this folder:

    {LAUNCH_COMMAND}

then open http://127.0.0.1:{port}/ in a browser. If that port is taken, the next
free one is used and shown (data saved in the page stays with the first port).
To choose one: add --port N.

The permissions are the whole contract: the launcher may listen on 127.0.0.1
(this computer) and read this folder, nothing else. It sends no data anywhere
and logs no request. Stop it with Ctrl+C.

Check for updates (in the page) compares this copy with {site["siteUrl"] or "the hosted site"};
version.json there lists the SHA-256 of this zip.
"""


def local_zip(project: Project, files: dict[str, bytes], launcher: str, target: pathlib.Path) -> None:
    """Write the zip to `target` (streamed to disk: assets can be large)."""
    folder = f"{project.site['id']}-local"
    first, last = PORT_BLOCK
    serve_config = {"port": default_port(project), "first": first, "last": last}
    entries = {f"{folder}/serve.js": launcher.encode("utf-8"),
               f"{folder}/serve.json": (json.dumps(serve_config, indent=2) + "\n").encode("utf-8"),
               f"{folder}/README.txt": _readme(project).encode("utf-8"),
               **{f"{folder}/public/{name}": data for name, data in files.items()}}
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=ZIP_DATE)
            info.create_system = UNIX_SYSTEM
            info.external_attr = UNIX_FILE_MODE
            archive.writestr(info, entries[name])
