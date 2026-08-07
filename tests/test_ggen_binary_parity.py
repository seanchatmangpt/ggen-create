from __future__ import annotations

import os
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gall_ggen_binary_parity import (  # noqa: E402
    check_ggen_binary_available,
    check_real_ggen_sync_run,
    check_session_from_live_submodule,
)

SUBMODULE_MARKER = ROOT / "vendor" / "hygen-create" / "example" / "package.json"
GGEN_BIN = shutil.which(os.environ.get("GGEN_BIN", "ggen"))


@unittest.skipUnless(
    SUBMODULE_MARKER.is_file(),
    "vendor/hygen-create submodule not initialized (run `git submodule update --init`)",
)
@unittest.skipUnless(
    GGEN_BIN is not None,
    "no real ggen binary on PATH (or $GGEN_BIN) - checkpoint is opt-in and skips cleanly",
)
class GgenBinaryParityTests(unittest.TestCase):
    """Bind the real-ggen-binary corroboration checkpoints (GB0-GB2).

    Opt-in by design: requires both the vendored submodule and an actual `ggen` binary
    on this machine. Skips cleanly (not a failure) when either is absent, so default
    `unittest discover` runs stay green everywhere except a machine with both.
    """

    def test_ggen_binary_reports_a_version(self) -> None:
        evidence = check_ggen_binary_available(ROOT)
        self.assertTrue(evidence["ggen_bin"])
        self.assertIn("ggen", evidence["version_output"].lower())

    def test_session_captures_from_live_submodule(self) -> None:
        evidence = check_session_from_live_submodule(ROOT)
        self.assertEqual(
            evidence["added_files"],
            ["dist/hello.js", "ggen-create.json", "package.json"],
        )

    def test_real_ggen_sync_run_reaches_p6_without_claiming_full_crown(self) -> None:
        evidence = check_real_ggen_sync_run(ROOT)
        checkpoints = evidence["checkpoints"]
        self.assertEqual(checkpoints["P6_REVISION_PARITY"], "ALIVE")
        # No reference_dir/reference_id supplied - P7 must stay PARTIAL_ALIVE, not
        # claim the full crown. Real upstream-hygen-render cross-check is a distinct,
        # unattempted follow-on (see ROADMAP.md's 80/20 ERRC section).
        self.assertEqual(checkpoints["P7_PARITY_CROWN"], "PARTIAL_ALIVE")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
