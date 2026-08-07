from __future__ import annotations

import os
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gall_p7_crown import check_p7_crown_alive  # noqa: E402

SUBMODULE_MARKER = ROOT / "vendor" / "hygen-create" / "example" / "package.json"
GGEN_BIN = shutil.which(os.environ.get("GGEN_BIN", "ggen"))
HAS_NODE_TOOLCHAIN = all(shutil.which(tool) for tool in ("node", "npx", "yarn"))


@unittest.skipUnless(
    SUBMODULE_MARKER.is_file(),
    "vendor/hygen-create submodule not initialized (run `git submodule update --init`)",
)
@unittest.skipUnless(
    GGEN_BIN is not None,
    "no real ggen binary on PATH (or $GGEN_BIN) - checkpoint is opt-in and skips cleanly",
)
@unittest.skipUnless(
    HAS_NODE_TOOLCHAIN,
    "node/npx/yarn not all available - checkpoint is opt-in and skips cleanly",
)
class P7CrownTests(unittest.TestCase):
    """Bind the real P7 crown checkpoint: real ggen binary + real independent upstream
    hygen render, byte-exact comparison.

    Opt-in by design: needs the submodule, a real ggen binary, and a full node/npm/yarn
    toolchain with network access (npx fetches hygen on first use). Skips cleanly
    (not a failure) when any prerequisite is missing, so default `unittest discover`
    runs stay green everywhere except a machine with the full toolchain.
    """

    def test_p7_crown_reaches_alive_with_zero_drift(self) -> None:
        evidence = check_p7_crown_alive(ROOT)
        self.assertEqual(evidence["checkpoints"]["P7_PARITY_CROWN"], "ALIVE")
        comparison = evidence["reference_comparison"]
        self.assertTrue(comparison["equal"])
        self.assertEqual(comparison["only_left"], [])
        self.assertEqual(comparison["only_right"], [])
        self.assertEqual(comparison["different"], [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
