from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ggen_create.cutover_dryrun import run
from ggen_create.cutover_dryrun.engine import (FAIL, PASS, UNVERIFIED, BLOCKED, Clause,
                                               evaluate, flip, read_digest, reset_reads)


class CutoverDryRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        (self.home / "srve" / "bin").mkdir(parents=True)
        (self.home / "srve" / "bin" / "golden-court").write_text("run --backend URL\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_clause_kinds_decide_real_files(self):
        has = Clause("count", "flag", {"paths": ["srve:bin/golden-court"], "pattern": "--backend",
                                       "op": "ge", "n": 1})
        self.assertEqual(evaluate(has, self.home).status, PASS)
        gone = Clause("count", "flag", {"paths": ["srve:bin/none"], "pattern": "x", "op": "ge",
                                        "n": 1})
        self.assertEqual(evaluate(gone, self.home).status, BLOCKED)
        absent = Clause("absent", "no flag", {"paths": ["srve:bin/golden-court"],
                                              "pattern": "--backend"})
        self.assertEqual(evaluate(absent, self.home).status, FAIL)

    def test_every_deterministic_clause_refuses_its_mutation(self):
        mutable = [
            Clause("exists", "e", {"paths": ["srve:bin/golden-court"]}),
            Clause("not_exists", "n", {"paths": ["srve:bin/nope"]}),
            Clause("count", "c", {"paths": ["srve:bin/golden-court"], "pattern": "run",
                                  "op": "eq", "n": 1}),
            Clause("absent", "a", {"paths": ["srve:bin/golden-court"], "pattern": "zzz"}),
        ]
        for clause in mutable:
            self.assertEqual(evaluate(clause, self.home).status, PASS, clause.desc)
            mutated = flip(clause)
            self.assertIsNotNone(mutated)
            self.assertNotEqual(evaluate(mutated, self.home).status, PASS, clause.desc)

    def test_cmd_clause_only_runs_syntax_checks_and_never_executes_repo_scripts(self):
        script = self.home / "srve" / "bin" / "touch-marker"
        marker = self.home / "marker"
        script.write_text(f"#!/bin/sh\ntouch {marker}\n")
        script.chmod(0o755)
        bad = Clause("cmd", "exec", {"argv": ["@srve:bin/touch-marker", "--backend", "x"],
                                     "expect_rc": 0})
        self.assertEqual(evaluate(bad, self.home).status, FAIL)
        self.assertFalse(marker.exists())
        ok = Clause("cmd", "syntax", {"argv": ["bash", "-n", "@srve:bin/touch-marker"],
                                      "expect_rc": 0})
        self.assertEqual(evaluate(ok, self.home).status, PASS)
        self.assertFalse(marker.exists())

    def test_read_set_digest_detects_a_file_changing_during_evaluation(self):
        reset_reads()
        clause = Clause("count", "flag", {"paths": ["srve:bin/golden-court"], "pattern": "--backend",
                                          "op": "ge", "n": 1})
        evaluate(clause, self.home)
        _, before = read_digest()
        (self.home / "srve" / "bin" / "golden-court").write_text("run --backend URL\nmore\n")
        _, after = read_digest()
        self.assertNotEqual(before, after)
        reset_reads()

    def test_run_reports_standing_and_never_writes(self):
        report = run(self.home, ["T-027"], do_selftest=True)
        row = report["tickets"][0]
        self.assertEqual(row["standing"], PASS)
        self.assertEqual(report["verdict"], "READY_TO_REHEARSE")
        self.assertEqual(report["selftest"], {"vacuous": []})
        self.assertEqual(sorted(p.name for p in (self.home / "srve" / "bin").iterdir()),
                         ["golden-court"])
        self.assertEqual(UNVERIFIED, "UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
