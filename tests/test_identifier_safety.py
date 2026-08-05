from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from ggen_create.automatic import automatic_plan
from ggen_create.model import GgenCreateError, validate_identifier
from ggen_create.package import build_package, rewrite_package_parameter
from ggen_create.session import (
    add_paths,
    load_session,
    rename_session,
    set_seed,
    start_session,
)
from ggen_create.verify import verify_parity


UNSAFE_IDENTIFIERS = (
    "../escape",
    "/tmp/escape",
    r"C:\\escape",
    "{{ bad }}",
    " bad",
    "bad ",
    "CON",
    "NUL.txt",
    "x" * 129,
)
SAFE_IDENTIFIERS = (
    "Hello",
    "Hello World",
    "hello-world",
    "hello_world",
    "Hello.World",
    "A",
)


class IdentifierSafetyTests(unittest.TestCase):
    def fixture(self, root: Path) -> tuple[Path, Path]:
        (root / "Hello.txt").write_text(
            "Hello hello HELLO",
            encoding="utf-8",
        )
        session = start_session(root, "greeter")
        add_paths(session, ["Hello.txt"], cwd=root)
        set_seed(session, "Hello")
        package = build_package(session, root / "packages").package_dir
        return session, package

    @staticmethod
    def manifest(root: Path) -> dict[str, bytes]:
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }

    def test_safe_identifiers_are_admitted(self) -> None:
        for value in SAFE_IDENTIFIERS:
            self.assertEqual(validate_identifier(value), value)

    def test_unsafe_identifiers_are_refused(self) -> None:
        for value in UNSAFE_IDENTIFIERS:
            with self.assertRaisesRegex(
                GgenCreateError,
                "IDENTIFIER_REFUSED",
                msg=repr(value),
            ):
                validate_identifier(value)

    def test_invalid_generator_does_not_create_session(self) -> None:
        for value in UNSAFE_IDENTIFIERS:
            with tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                with self.assertRaisesRegex(
                    GgenCreateError,
                    "GENERATOR_NAME_REFUSED",
                    msg=repr(value),
                ):
                    start_session(root, value)
                self.assertFalse((root / "ggen-create.json").exists())

    def test_invalid_seed_and_rename_leave_session_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            session = start_session(root, "greeter")
            before = session.read_bytes()
            for value in UNSAFE_IDENTIFIERS:
                with self.assertRaisesRegex(
                    GgenCreateError,
                    "PARAMETER_SEED_REFUSED",
                    msg=repr(value),
                ):
                    set_seed(session, value)
                self.assertEqual(session.read_bytes(), before)
                with self.assertRaisesRegex(
                    GgenCreateError,
                    "GENERATOR_NAME_REFUSED",
                    msg=repr(value),
                ):
                    rename_session(session, value)
                self.assertEqual(session.read_bytes(), before)

    def test_hand_edited_unsafe_identifiers_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            session = start_session(root, "greeter")
            value = json.loads(session.read_text(encoding="utf-8"))
            value["name"] = "../escape"
            session.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(
                GgenCreateError,
                "GENERATOR_NAME_REFUSED",
            ):
                load_session(session)

    def test_invalid_package_rewrite_has_no_consequence(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _, package = self.fixture(root)
            before = self.manifest(package)
            for value in UNSAFE_IDENTIFIERS:
                with self.assertRaisesRegex(
                    GgenCreateError,
                    "PARAMETER_VALUE_REFUSED",
                    msg=repr(value),
                ):
                    rewrite_package_parameter(package, value)
                self.assertEqual(self.manifest(package), before)

    def test_invalid_parity_variation_preserves_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            session, _ = self.fixture(root)
            output = root / "verification"
            output.mkdir()
            sentinel = output / "sentinel.txt"
            sentinel.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(
                GgenCreateError,
                "PARAMETER_VALUE_REFUSED",
            ):
                verify_parity(
                    session,
                    output_root=output,
                    ggen_bin="not-executed",
                    variation_value="../escape",
                    force=True,
                )
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
            self.assertEqual(list(output.iterdir()), [sentinel])

    def test_invalid_automatic_plan_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            session, _ = self.fixture(root)
            output = root / "automatic-output"
            with self.assertRaisesRegex(
                GgenCreateError,
                "PARAMETER_VALUE_REFUSED",
            ):
                automatic_plan(
                    session,
                    output_root=output,
                    variation_value="{{ bad }}",
                    verify=True,
                )
            self.assertFalse(output.exists())
            self.assertFalse((root / ".ggen-create").exists())


if __name__ == "__main__":
    unittest.main()
