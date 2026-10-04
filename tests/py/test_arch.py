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


def make_app(files: dict[str, str]) -> Project:
    root = pathlib.Path(tempfile.mkdtemp(prefix="arch_"))
    for name, text in files.items():
        path = root / "src" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return Project(root=root, site={}, platform_dir=root)


GOOD = {
    "core/types.ts": "export type X = 1;",
    "core/dataset.ts": 'import rows from "../data/rows.json";',
    "data/rows.json": "[]",
    "core/ids/parse.ts": 'import type { X } from "../types.ts";',
    "ui/frame.ts": 'import { el } from "static-web-platform";\nimport type { X } from "../core/types.ts";',
    "state/selection.ts": 'import type { X } from "../core/types.ts";',
    "features/notes/notes.ts": 'import "./notes.css";\nimport { tabs } from "./tabs.ts";\nimport { frame } from "../../ui/frame.ts";',
    "features/notes/tabs.ts": 'import { sel } from "../../state/selection.ts";',
    "features/search.ts": 'import { el } from "static-web-platform";\nimport { parse } from "../core/ids/parse.ts";',
    "workers/solver.ts": 'import { parse } from "../core/ids/parse.ts";',
    "main.ts": 'import { search } from "./features/search.ts";\nimport { notes } from "./features/notes/notes.ts";',
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
        self.assert_broken({"core/x.ts": 'import { el } from "static-web-platform";'}, "may not use the platform")

    def test_core_importing_ui(self):
        self.assert_broken({"core/x.ts": 'import { frame } from "../ui/frame.ts";'}, "(core) may not import")

    def test_core_modes_are_isolated(self):
        self.assert_broken({"core/files/x.ts": 'import { parse } from "../ids/parse.ts";'},
                           "core modes never import each other")

    def test_deep_platform_import(self):
        self.assert_broken({"features/search.ts": 'import { x } from "static-web-platform/src/ui/dom.ts";'},
                           "public API only")

    def test_feature_reading_a_dataset_directly(self):
        self.assert_broken({"features/search.ts": 'import rows from "../data/rows.json";'}, "may not import data/rows.json")

    def test_worker_using_the_platform(self):
        self.assert_broken({"workers/solver.ts": 'import { el } from "static-web-platform";'}, "may not use the platform")


if __name__ == "__main__":
    unittest.main()
