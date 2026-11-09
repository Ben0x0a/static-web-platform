"""test_arch.py — unit tests of the layer rules (arch.py) on small fake apps.

Used by : `npm test`.
Uses    : tools/swp_tools/arch.py, config.py.
"""

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "tools"))
from swp_tools.arch import check_architecture  # noqa: E402
from swp_tools.config import Project  # noqa: E402


def make_app(files: dict[str, str], modes: list[str] | None = None) -> Project:
    root = pathlib.Path(tempfile.mkdtemp(prefix="arch_"))
    for name, text in files.items():
        path = root / "src" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return Project(root=root, site={"modes": modes if modes is not None else ["ids", "files"]}, platform_dir=root)


GOOD = {
    "core/types.ts": "export type X = 1;",
    "core/dataset.ts": 'import rows from "../data/rows.json";',
    "data/rows.json": "[]",
    "core/ids/parse.ts": 'import type { X } from "../types.ts";\nimport { enc } from "../text/encode.ts";',
    "core/text/encode.ts": 'import { vcard } from "../vcard/parse.ts";',
    "core/vcard/parse.ts": 'import type { X } from "../types.ts";',
    "core/files/read.ts": 'import { enc } from "../text/encode.ts";',
    "ui/frame.ts": 'import { el } from "static-web-platform";\nimport type { X } from "../core/types.ts";',
    "state/selection.ts": 'import type { X } from "../core/types.ts";',
    "features/notes/notes.ts": 'import "./notes.css";\nimport { tabs } from "./tabs.ts";\nimport { frame } from "../../ui/frame.ts";',
    "features/notes/tabs.ts": 'import { sel } from "../../state/selection.ts";',
    "features/search.ts": 'import { el } from "static-web-platform";\nimport { parse } from "../core/ids/parse.ts";',
    "workers/solver.ts": 'import { parse } from "../core/ids/parse.ts";',
    "main.ts": 'import { search } from "./features/search.ts";\nimport { notes } from "./features/notes/notes.ts";',
    "api/index.ts": 'import { parse } from "../core/ids/parse.ts";\nimport { run } from "./run.ts";',
    "api/run.ts": 'import type { X } from "../core/types.ts";',
    "cli/main.ts": ('import { startCli } from "static-web-platform/cli";\nimport { run } from "../api/index.ts";\n'
                    'import type { X } from "../core/types.ts";'),
    "features/analyse.ts": 'import { run } from "../api/index.ts";',
    "workers/analyse.ts": 'import { run } from "../api/run.ts";',
}


class ArchTest(unittest.TestCase):
    def test_valid_layout_passes(self):
        check_architecture(make_app(GOOD))

    def assert_broken(self, extra: dict[str, str], message: str):
        with self.assertRaises(SystemExit) as caught:
            check_architecture(make_app({**GOOD, **extra}))
        self.assertIn(message, str(caught.exception))

    def test_feature_importing_another_feature(self):
        self.assert_broken({"features/search.ts": 'import { notes } from "./notes/notes.ts";'},
                           "features never import other features")

    def test_core_using_the_platform(self):
        self.assert_broken({"core/x.ts": 'import { el } from "static-web-platform";'}, "(core) may not use 'static-web-platform'")

    def test_core_importing_ui(self):
        self.assert_broken({"core/x.ts": 'import { frame } from "../ui/frame.ts";'}, "(core) may not import")

    def test_core_modes_are_isolated(self):
        self.assert_broken({"core/files/x.ts": 'import { parse } from "../ids/parse.ts";'},
                           "modes never import each other")

    def test_plain_core_subfolders_import_each_other(self):
        # text/ and vcard/ are organisation, not modes: GOOD already has them importing each other.
        check_architecture(make_app(GOOD))

    def test_undeclared_subfolders_are_not_modes(self):
        check_architecture(make_app({**GOOD, "core/files/x.ts": 'import { parse } from "../ids/parse.ts";'}, modes=[]))

    def test_deep_platform_import(self):
        self.assert_broken({"features/search.ts": 'import { x } from "static-web-platform/src/ui/dom.ts";'},
                           "public entries only")

    def test_feature_reading_a_dataset_directly(self):
        self.assert_broken({"features/search.ts": 'import rows from "../data/rows.json";'}, "may not import data/rows.json")

    def test_worker_using_the_platform(self):
        self.assert_broken({"workers/solver.ts": 'import { el } from "static-web-platform";'},
                           "(workers) may not use 'static-web-platform'")

    def test_api_is_pure(self):
        for spec, message in (('import { el } from "static-web-platform";', "(api) may not use"),
                              ('import { frame } from "../ui/frame.ts";', "(api) may not import"),
                              ('import rows from "../data/rows.json";', "(api) may not import")):
            self.assert_broken({"api/x.ts": spec}, message)

    def test_cli_uses_only_api_core_and_the_cli_entry(self):
        for spec, message in (('import { el } from "static-web-platform";', "(cli) may not use 'static-web-platform'"),
                              ('import { search } from "../features/search.ts";', "(cli) may not import"),
                              ('import { frame } from "../ui/frame.ts";', "(cli) may not import")):
            self.assert_broken({"cli/main.ts": spec}, message)

    def test_cli_entry_only_in_cli(self):
        self.assert_broken({"features/search.ts": 'import { startCli } from "static-web-platform/cli";'},
                           "(features) may not use 'static-web-platform/cli'")

    def test_nothing_imports_the_cli(self):
        self.assert_broken({"main.ts": 'import { x } from "./cli/main.ts";'}, "(app) may not import cli/main.ts")


if __name__ == "__main__":
    unittest.main()
