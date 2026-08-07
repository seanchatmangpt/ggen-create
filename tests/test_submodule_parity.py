from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gall_submodule_parity import (  # noqa: E402
    check_live_blob_match,
    check_live_reconstruction,
    check_submodule_pinned,
)

SUBMODULE_MARKER = ROOT / "vendor" / "hygen-create" / "package.json"


@unittest.skipUnless(
    SUBMODULE_MARKER.is_file(),
    "vendor/hygen-create submodule not initialized (run `git submodule update --init`)",
)
class SubmoduleParityTests(unittest.TestCase):
    """Bind the live-submodule corroboration checkpoints (SM0, SM2, SM3).

    SM1 (upstream's own npm install/build/test) is intentionally excluded from the
    default unit run: it needs network access and can take minutes, matching this
    checkpoint family's opt-in design (see scripts/gall_submodule_parity.py). Run it
    directly via `python3 scripts/gall_submodule_parity.py` when validating a submodule
    bump.
    """

    def test_submodule_is_pinned_to_reference_commit(self) -> None:
        evidence = check_submodule_pinned(ROOT)
        self.assertEqual(evidence["repository"], "ronp001/hygen-create")

    def test_live_example_files_match_static_fixture_blobs(self) -> None:
        evidence = check_live_blob_match(ROOT)
        self.assertEqual(len(evidence["files"]), 4)

    def test_transform_logic_reconstructs_live_tree_byte_exactly(self) -> None:
        evidence = check_live_reconstruction(ROOT)
        self.assertIn("hello", evidence)
        self.assertIn("hola", evidence)
        self.assertEqual(evidence["hola"]["execution"]["stdout"], "Hola!")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
