from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gall_hygen_parity import (  # noqa: E402
    ALIVE,
    check_case_corpus,
    check_documentation,
    check_reference_blobs,
    execute_example,
    manufacture,
    run_checkpoints,
    transform_text,
)


class HygenParityCheckpointTests(unittest.TestCase):
    def test_reference_examples_are_exact_upstream_blobs(self) -> None:
        evidence = check_reference_blobs(ROOT)
        self.assertEqual(
            evidence["dist/hello.js"]["git_blob"],
            "31b71d3edcaa117ddfc26284862641805a696059",
        )
        self.assertEqual(len(evidence), 4)

    def test_original_case_corpus_is_closed(self) -> None:
        evidence = check_case_corpus(ROOT)
        self.assertEqual(evidence["comparisons"], 24)
        self.assertEqual(transform_text("ClsWord", "word", "result"), "ClsWord")
        self.assertEqual(
            transform_text("double_word_with_sfx", "DoubleWord", "TheResult"),
            "the_result_with_sfx",
        )

    def test_documented_commands_are_bound_to_fixture_consequences(self) -> None:
        evidence = check_documentation(ROOT)
        self.assertIn("ggen-create generate", evidence["commands"])
        self.assertIn("dist/hola.js", evidence["facts"])

    def test_hola_example_executes_through_package_script(self) -> None:
        reference = ROOT / "examples" / "hygen-create-reference"
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw)
            result = manufacture(reference, output, "Hola")
            execution = execute_example(output)
            self.assertEqual(result["files"], ["dist/hola.js", "hygen-create.json", "package.json"])
            self.assertEqual(execution["exit_code"], 0)
            self.assertEqual(execution["stdout"], "Hola!")
            package = json.loads((output / "package.json").read_text(encoding="utf-8"))
            self.assertEqual(package["scripts"], {"hola": "node dist/hola.js"})

    def test_full_gall_checkpoint_crown_is_alive(self) -> None:
        receipt = run_checkpoints(ROOT)
        self.assertEqual(receipt["standing"], ALIVE, receipt["failures"])
        self.assertEqual(
            {item["standing"] for item in receipt["checkpoints"].values()},
            {ALIVE},
        )


if __name__ == "__main__":
    unittest.main()
