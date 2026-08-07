from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from ggen_create.model import GgenCreateError
from ggen_create.package import build_package
from ggen_create.session import add_paths, set_seed, start_session
from ggen_create.verify import compare_trees, verify_parity


class CollisionLawTests(unittest.TestCase):
    @staticmethod
    def manifest(root: Path) -> dict[str, bytes]:
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }

    def make_order_fixture(
        self,
        root: Path,
        order: list[str],
    ) -> Path:
        (root / "src").mkdir()
        (root / "src/HelloOne.txt").write_text(
            "HelloOne",
            encoding="utf-8",
        )
        (root / "src/HelloTwo.txt").write_text(
            "HelloTwo",
            encoding="utf-8",
        )
        session = start_session(root, "greeter")
        add_paths(session, order, cwd=root)
        set_seed(session, "Hello")
        return build_package(session, root / "packages").package_dir

    def test_admission_order_does_not_change_package_identity(self) -> None:
        with (
            tempfile.TemporaryDirectory() as left_raw,
            tempfile.TemporaryDirectory() as right_raw,
        ):
            left = self.make_order_fixture(
                Path(left_raw),
                ["src/HelloOne.txt", "src/HelloTwo.txt"],
            )
            right = self.make_order_fixture(
                Path(right_raw),
                ["src/HelloTwo.txt", "src/HelloOne.txt"],
            )
            self.assertEqual(self.manifest(left), self.manifest(right))

    def test_seed_target_collision_refuses_before_output_creation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            upper = root / "Hello.txt"
            lower = root / "hello.txt"
            upper.write_text("Hello", encoding="utf-8")
            lower.write_text("hello", encoding="utf-8")
            try:
                if upper.samefile(lower):
                    self.skipTest("filesystem is case-insensitive")
            except OSError:
                pass
            session = start_session(root, "greeter")
            add_paths(session, [upper.name, lower.name], cwd=root)
            set_seed(session, "Hello")
            output = root / "packages"
            with self.assertRaisesRegex(
                GgenCreateError,
                "TARGET_COLLISION_REFUSED",
            ):
                build_package(session, output)
            self.assertFalse(output.exists())

    def test_variation_collision_preserves_existing_verifier_output(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "HelloWorld.txt").write_text(
                "HelloWorld",
                encoding="utf-8",
            )
            (root / "hello-world.txt").write_text(
                "hello-world",
                encoding="utf-8",
            )
            session = start_session(root, "greeter")
            add_paths(
                session,
                ["HelloWorld.txt", "hello-world.txt"],
                cwd=root,
            )
            set_seed(session, "HelloWorld")
            build_package(session, root / "packages")

            output = root / "verification"
            output.mkdir()
            sentinel = output / "sentinel.txt"
            sentinel.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(
                GgenCreateError,
                "ARTIFACT_TARGET_COLLISION_REFUSED",
            ):
                verify_parity(
                    session,
                    output_root=output,
                    ggen_bin="not-executed",
                    variation_value="X",
                    force=True,
                )
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
            self.assertEqual(list(output.iterdir()), [sentinel])

    @unittest.skipIf(not hasattr(os, "symlink"), "symlinks unavailable")
    def test_comparison_tree_symlink_is_refused(self) -> None:
        with (
            tempfile.TemporaryDirectory() as left_raw,
            tempfile.TemporaryDirectory() as right_raw,
            tempfile.TemporaryDirectory() as outside_raw,
        ):
            left = Path(left_raw)
            right = Path(right_raw)
            outside = Path(outside_raw) / "outside.txt"
            outside.write_text("outside", encoding="utf-8")
            try:
                (left / "escape.txt").symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"symlink creation unavailable: {exc}")
            (right / "escape.txt").write_text("outside", encoding="utf-8")
            with self.assertRaisesRegex(
                GgenCreateError,
                "TREE_SYMLINK_REFUSED",
            ):
                compare_trees(left, right)


if __name__ == "__main__":
    unittest.main()
