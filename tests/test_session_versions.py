from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from ggen_create.model import (
    ABOUT,
    APP_VERSION,
    GgenCreateError,
    SUPPORTED_SESSION_VERSIONS,
)
from ggen_create.session import load_session, start_session


class SessionVersionTests(unittest.TestCase):
    def test_current_session_version_is_admitted(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = start_session(Path(raw), "greeter")
            self.assertEqual(
                load_session(path)["hygen_create_version"],
                APP_VERSION,
            )

    def test_upstream_legacy_session_versions_are_admitted(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for version in ("0.2.0", "0.2.1", "0.3.0"):
                path = root / f"capture-{version}.json"
                path.write_text(
                    json.dumps(
                        {
                            "about": ABOUT,
                            "hygen_create_version": version,
                            "name": "greeter",
                            "files_and_dirs": {path.name: True},
                            "templatize_using_name": None,
                            "gen_parent_dir": False,
                        }
                    ),
                    encoding="utf-8",
                )
                self.assertEqual(
                    load_session(path)["hygen_create_version"],
                    version,
                )

    def test_unknown_capture_version_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "ggen-create.json"
            path.write_text(
                json.dumps(
                    {
                        "about": ABOUT,
                        "hygen_create_version": "9.9.9",
                        "name": "greeter",
                        "files_and_dirs": {path.name: True},
                        "templatize_using_name": None,
                        "gen_parent_dir": False,
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                GgenCreateError,
                "SESSION_VERSION_REFUSED",
            ):
                load_session(path)

    def test_supported_versions_are_unique_and_include_current(self) -> None:
        self.assertIn(APP_VERSION, SUPPORTED_SESSION_VERSIONS)
        self.assertEqual(
            len(SUPPORTED_SESSION_VERSIONS),
            len(set(SUPPORTED_SESSION_VERSIONS)),
        )


if __name__ == "__main__":
    unittest.main()
