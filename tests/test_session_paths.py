from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from ggen_create.model import ABOUT, APP_VERSION, GgenCreateError
from ggen_create.session import admitted_files, load_session


def document(path_name: str, *, extra: bool = False) -> dict[str, object]:
    value: dict[str, object] = {
        "about": ABOUT,
        "hygen_create_version": APP_VERSION,
        "name": "greeter",
        "files_and_dirs": {path_name: True},
        "templatize_using_name": None,
        "gen_parent_dir": False,
    }
    if extra:
        value["ambient_authority"] = True
    return value


class SessionPathTests(unittest.TestCase):
    def write_session(
        self,
        root: Path,
        value: dict[str, object],
    ) -> Path:
        path = root / "ggen-create.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_parent_traversal_is_refused_at_load(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = self.write_session(root, document("../escape.txt"))
            with self.assertRaisesRegex(
                GgenCreateError,
                "SESSION_PATH_REFUSED",
            ):
                load_session(path)

    def test_posix_absolute_path_is_refused_at_load(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = self.write_session(root, document("/etc/passwd"))
            with self.assertRaisesRegex(
                GgenCreateError,
                "SESSION_PATH_REFUSED",
            ):
                load_session(path)

    def test_windows_absolute_and_drive_relative_paths_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for unsafe in (r"C:\\Windows\\win.ini", r"C:escape.txt", r"\\server\\share\\file"):
                path = self.write_session(root, document(unsafe))
                with self.assertRaisesRegex(
                    GgenCreateError,
                    "SESSION_PATH_REFUSED",
                    msg=unsafe,
                ):
                    load_session(path)

    def test_extra_capture_fields_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = self.write_session(
                root,
                document("ggen-create.json", extra=True),
            )
            with self.assertRaisesRegex(
                GgenCreateError,
                "SESSION_SCHEMA_REFUSED",
            ):
                load_session(path)

    @unittest.skipIf(
        not hasattr(os, "symlink"),
        "symlinks are unavailable",
    )
    def test_hand_edited_symlink_is_refused_at_use(self) -> None:
        with (
            tempfile.TemporaryDirectory() as raw,
            tempfile.TemporaryDirectory() as outside_raw,
        ):
            root = Path(raw)
            outside = Path(outside_raw) / "outside.txt"
            outside.write_text("Hello", encoding="utf-8")
            link = root / "link.txt"
            try:
                link.symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"symlink creation unavailable: {exc}")
            path = self.write_session(root, document("link.txt"))
            with self.assertRaisesRegex(
                GgenCreateError,
                "SYMLINK_REFUSED",
            ):
                admitted_files(path)

    def test_safe_nested_relative_path_is_admitted(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            nested = root / "nested"
            nested.mkdir()
            (nested / "hello.txt").write_text(
                "Hello",
                encoding="utf-8",
            )
            path = self.write_session(root, document("nested/hello.txt"))
            self.assertEqual(admitted_files(path), ["nested/hello.txt"])


if __name__ == "__main__":
    unittest.main()
