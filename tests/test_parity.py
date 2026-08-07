from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from ggen_create.cases import (
    parameterize_body,
    parameterize_path,
    render_concrete,
    values_for,
)
from ggen_create.inspect import inspect_session
from ggen_create.integrity import verify_package
from ggen_create.model import APP_VERSION, GgenCreateError
from ggen_create.package import build_package
from ggen_create.session import (
    add_paths,
    load_session,
    set_seed,
    start_session,
)
from ggen_create.verify import (
    compare_reference_trees,
    compare_trees,
    verify_parity,
)


class ParityTests(unittest.TestCase):
    def test_original_compatible_capture_shape(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            session_path = start_session(root, "greeter")
            session = load_session(session_path)
            self.assertEqual(
                list(session),
                [
                    "about",
                    "hygen_create_version",
                    "name",
                    "files_and_dirs",
                    "templatize_using_name",
                    "gen_parent_dir",
                ],
            )
            self.assertEqual(session["hygen_create_version"], APP_VERSION)
            self.assertEqual(
                session["files_and_dirs"],
                {"ggen-create.json": True},
            )

    def test_case_family_matches_original_architecture(self) -> None:
        values = values_for("HelloWorld")
        self.assertEqual(values["upper"], "HELLOWORLD")
        self.assertEqual(values["lower"], "helloworld")
        self.assertEqual(values["camel"], "helloWorld")
        self.assertEqual(values["snake"], "hello_world")
        self.assertEqual(values["upper_snake"], "HELLO_WORLD")
        self.assertEqual(values["kebab"], "hello-world")
        self.assertEqual(values["title"], "Hello World")

        source = "HelloWorld helloWorld hello_world HELLO_WORLD hello-world"
        rendered, _ = render_concrete(
            source,
            "HelloWorld",
            "CustomerAccount",
        )
        self.assertEqual(
            rendered,
            "CustomerAccount customerAccount customer_account "
            "CUSTOMER_ACCOUNT customer-account",
        )

    def test_parameterization_covers_paths_and_contents(self) -> None:
        path, path_replacements = parameterize_path(
            "dist/hello.js",
            "Hello",
        )
        body, body_replacements = parameterize_body(
            '// This is hello.js\nconsole.log("Hello!")\n',
            "Hello",
        )
        self.assertEqual(path, "dist/{{ row.lower }}.js")
        self.assertEqual(len(path_replacements), 1)
        self.assertIn("{{ row.lower }}", body)
        self.assertIn("{{ row.capitalized }}", body)
        self.assertEqual(len(body_replacements), 2)

    def test_add_rejects_outside_root_and_binary(self) -> None:
        with (
            tempfile.TemporaryDirectory() as raw,
            tempfile.TemporaryDirectory() as outside_raw,
        ):
            root = Path(raw)
            outside = Path(outside_raw)
            session_path = start_session(root, "greeter")
            (outside / "escape.txt").write_text(
                "Hello",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                GgenCreateError,
                "PATH_OUTSIDE_CAPTURE_ROOT_REFUSED",
            ):
                add_paths(
                    session_path,
                    [str(outside / "escape.txt")],
                    cwd=root,
                )

            (root / "binary.bin").write_bytes(b"abc\0def")
            with self.assertRaisesRegex(
                GgenCreateError,
                "BINARY_FILE_REFUSED",
            ):
                add_paths(
                    session_path,
                    ["binary.bin"],
                    cwd=root,
                )

    def test_package_is_deterministic_and_versions_changed_generator(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "dist").mkdir()
            (root / "dist/hello.js").write_text(
                '// This is hello.js\nconsole.log("Hello!")\n',
                encoding="utf-8",
            )
            (root / "package.json").write_text(
                json.dumps(
                    {
                        "name": "hello",
                        "scripts": {"hello": "node dist/hello.js"},
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            session_path = start_session(root, "greeter")
            add_paths(
                session_path,
                ["package.json", "dist/hello.js"],
                cwd=root,
            )
            set_seed(session_path, "Hello")

            output = root / "out"
            first = build_package(session_path, output)
            self.assertTrue(first.changed)
            second = build_package(session_path, output)
            self.assertFalse(second.changed)
            self.assertEqual(first.package_dir, second.package_dir)

            (root / "dist/hello.js").write_text(
                '// This is improved hello.js\nconsole.log("Hello! Hello!")\n',
                encoding="utf-8",
            )
            third = build_package(session_path, output)
            self.assertTrue(third.changed)
            self.assertIsNotNone(third.archived_previous)
            assert third.archived_previous is not None
            self.assertTrue(third.archived_previous.is_dir())
            self.assertTrue((third.package_dir / "ggen.toml").is_file())
            templates = list(
                (third.package_dir / "templates").glob("*.tmpl")
            )
            self.assertEqual(len(templates), 3)
            template_text = "\n".join(
                path.read_text(encoding="utf-8")
                for path in templates
            )
            self.assertIn(
                'to: "dist/{{ row.lower }}.js"',
                template_text,
            )

    def test_inspection_is_mechanical(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "Hello.txt").write_text(
                "Hello hello HELLO",
                encoding="utf-8",
            )
            session_path = start_session(root, "greeter")
            add_paths(session_path, ["Hello.txt"], cwd=root)
            set_seed(session_path, "Hello")
            report = inspect_session(session_path)
            by_path = {
                item["path"]: item
                for item in report["files"]
            }
            self.assertEqual(
                by_path["Hello.txt"]["target_template"],
                "{{ row.capitalized }}.txt",
            )
            self.assertGreaterEqual(report["replacement_count"], 4)

    def test_tree_comparison_is_byte_exact(self) -> None:
        with (
            tempfile.TemporaryDirectory() as left_raw,
            tempfile.TemporaryDirectory() as right_raw,
        ):
            left = Path(left_raw)
            right = Path(right_raw)
            (left / "a").write_text("same", encoding="utf-8")
            (right / "a").write_text("same", encoding="utf-8")
            self.assertTrue(compare_trees(left, right)["equal"])
            (right / "a").write_text("different", encoding="utf-8")
            result = compare_trees(left, right)
            self.assertFalse(result["equal"])
            self.assertEqual(result["different"], ["a"])

    def test_reference_comparison_normalizes_only_capture_manifest(self) -> None:
        with (
            tempfile.TemporaryDirectory() as left_raw,
            tempfile.TemporaryDirectory() as right_raw,
        ):
            left = Path(left_raw)
            right = Path(right_raw)
            original = {
                "about": "same",
                "hygen_create_version": "0.2.1",
                "name": "greeter",
                "files_and_dirs": {
                    "hygen-create.json": True,
                    "dist/hola.js": True,
                },
                "templatize_using_name": "Hola",
                "gen_parent_dir": False,
            }
            candidate = {
                **original,
                "hygen_create_version": APP_VERSION,
                "files_and_dirs": {
                    "ggen-create.json": True,
                    "dist/hola.js": True,
                },
            }
            (left / "hygen-create.json").write_text(
                json.dumps(original, indent=4),
                encoding="utf-8",
            )
            (right / "ggen-create.json").write_text(
                json.dumps(candidate, separators=(",", ":")),
                encoding="utf-8",
            )
            (left / "artifact.txt").write_bytes(b"same")
            (right / "artifact.txt").write_bytes(b"same")

            result = compare_reference_trees(left, right)
            self.assertTrue(result["equal"], result)
            self.assertEqual(
                result["policy"],
                "byte-exact-except-capture-session-semantic-v1",
            )

            (right / "artifact.txt").write_bytes(b"drift")
            drift = compare_reference_trees(left, right)
            self.assertFalse(drift["equal"])
            self.assertEqual(drift["different"], ["artifact.txt"])

    def test_reference_comparison_rejects_capture_alias_collision(self) -> None:
        with (
            tempfile.TemporaryDirectory() as left_raw,
            tempfile.TemporaryDirectory() as right_raw,
        ):
            left = Path(left_raw)
            right = Path(right_raw)
            document = {
                "files_and_dirs": {"ggen-create.json": True},
            }
            for name in ("hygen-create.json", "ggen-create.json"):
                (left / name).write_text(
                    json.dumps(document),
                    encoding="utf-8",
                )
            (right / "ggen-create.json").write_text(
                json.dumps(document),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                GgenCreateError,
                "REFERENCE_CAPTURE_ALIAS_COLLISION_REFUSED",
            ):
                compare_reference_trees(left, right)

    def test_full_parity_report_with_bounded_fake_ggen(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            source.mkdir()
            (source / "dist").mkdir()
            (source / "package.json").write_text(
                json.dumps(
                    {
                        "name": "hello",
                        "scripts": {"hello": "node dist/hello.js"},
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            (source / "dist/hello.js").write_text(
                'console.log("Hello!")\n',
                encoding="utf-8",
            )
            session_path = start_session(source, "greeter")
            add_paths(
                session_path,
                ["package.json", "dist/hello.js"],
                cwd=source,
            )
            set_seed(session_path, "Hello")

            fake = root / "fake-ggen"
            fake.write_text(
                """#!/usr/bin/env python3
import json
from pathlib import Path
from ggen_create.cases import values_for

root = Path.cwd()
meta = json.loads((root / 'ggen-create-package.json').read_text())
value = meta['parameter']['value']
values = values_for(value)

def render(text):
    for key, replacement in values.items():
        text = text.replace('{{ row.' + key + ' }}', replacement)
    return text.replace('{% raw %}', '').replace('{% endraw %}', '')

for item in meta['files']:
    template = (root / item['template']).read_text()
    parts = template.split('---' + '\\n', 2)
    if len(parts) != 3:
        raise SystemExit('invalid template: ' + item['template'])
    target = root / render(item['target'])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(parts[2]))
""",
                encoding="utf-8",
            )
            fake.chmod(0o755)

            reference = root / "reference"
            (reference / "dist").mkdir(parents=True)
            (reference / "package.json").write_text(
                json.dumps(
                    {
                        "name": "hola",
                        "scripts": {"hola": "node dist/hola.js"},
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            (reference / "dist/hola.js").write_text(
                'console.log("Hola!")\n',
                encoding="utf-8",
            )
            generated_session = json.loads(session_path.read_text())
            generated_session["hygen_create_version"] = "0.2.1"
            generated_session["templatize_using_name"] = "Hola"
            generated_session["files_and_dirs"] = {
                (
                    "hygen-create.json"
                    if key == "ggen-create.json"
                    else "dist/hola.js"
                    if key == "dist/hello.js"
                    else key
                ): included
                for key, included in generated_session["files_and_dirs"].items()
            }
            (reference / "hygen-create.json").write_text(
                json.dumps(generated_session, indent=2),
                encoding="utf-8",
            )

            report = verify_parity(
                session_path,
                output_root=root / "verify",
                ggen_bin=str(fake),
                variation_value="Hola",
                reference_dir=reference,
                reference_id="ronp001/hygen-create@test",
            )
            self.assertEqual(
                report["checkpoints"]["P7_PARITY_CROWN"],
                "ALIVE",
            )
            self.assertEqual(
                report["checkpoints"]["P6_REVISION_PARITY"],
                "ALIVE",
            )
            self.assertTrue(report["reference_comparison"]["equal"])
            self.assertTrue(Path(report["report_path"]).is_file())
            for label in ("reconstruction", "variation"):
                integrity = verify_package(
                    root / f"verify/{label}-run",
                    allow_extra=True,
                )
                self.assertTrue(integrity["valid"], integrity)
                self.assertTrue(integrity["extra"], integrity)


if __name__ == "__main__":
    unittest.main()
