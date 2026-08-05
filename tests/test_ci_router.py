from __future__ import annotations
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"scripts"))
from ci_router import RoutingRefusal, discover_changed_files, github_outputs, route_paths
class RouterTests(unittest.TestCase):
    def test_unrelated_documentation_only_change(self):
        r=route_paths(["README.md"]); self.assertEqual(r["docs_deep"],["README.md"]); self.assertEqual(r["build_deep"],[])
    def test_source_change(self): self.assertEqual(route_paths(["src/lib.rs"])["build_deep"],["src/lib.rs"])
    def test_test_change(self): self.assertEqual(route_paths(["tests/compiler.rs"])["build_deep"],["tests/compiler.rs"])
    def test_workflow_only_change(self):
        r=route_paths([".github/workflows/ci.yml"]); self.assertEqual(r["ci_deep"],[".github/workflows/ci.yml"]); self.assertEqual(r["build_deep"],[]); self.assertEqual(r["ontology_deep"],[])
    def test_deep_lane_owned_change(self): self.assertEqual(route_paths(["ontology/schema.ttl"])["ontology_deep"],["ontology/schema.ttl"])
    def test_exclusion_precedence(self):
        r=route_paths(["tests/test_ci_router.py"]); self.assertEqual(r["ci_deep"],["tests/test_ci_router.py"]); self.assertEqual(r["build_deep"],[])
    def test_multi_lane_change(self):
        r=route_paths(["README.md","src/lib.rs","ontology/schema.ttl"]); self.assertTrue(r["docs_deep"] and r["build_deep"] and r["ontology_deep"])
    def test_duplicate_changed_paths(self): self.assertEqual(route_paths(["README.md","README.md"])["docs_deep"],["README.md"])
    def test_changed_file_discovery_failure(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RoutingRefusal) as c: discover_changed_files("deadbeef","cafebabe",d)
            self.assertEqual(c.exception.reason,"REFUSED:CHANGED_FILE_DISCOVERY_FAILED")
    def test_exact_expected_boolean_outputs(self):
        o=github_outputs(route_paths(["README.md","ontology/schema.ttl"])); self.assertEqual(o["build_deep"],"false"); self.assertEqual(o["ci_deep"],"false"); self.assertEqual(o["docs_deep"],"true"); self.assertEqual(o["ontology_deep"],"true"); self.assertEqual(json.loads(o["docs_deep_files"]),["README.md"])
    def test_unknown_future_surface_is_conservative_build(self): self.assertEqual(route_paths(["generator/model.bin"])["build_deep"],["generator/model.bin"])
    def test_invalid_path_is_refused(self):
        with self.assertRaises(RoutingRefusal): route_paths(["../escape"])
    def test_real_two_commit_discovery(self):
        env=os.environ.copy(); env.update({"GIT_AUTHOR_NAME":"CI","GIT_AUTHOR_EMAIL":"ci@example.invalid","GIT_COMMITTER_NAME":"CI","GIT_COMMITTER_EMAIL":"ci@example.invalid"})
        with tempfile.TemporaryDirectory() as d:
            r=Path(d); subprocess.run(["git","init","-q"],cwd=r,env=env,check=True); (r/"README.md").write_text("base\n"); subprocess.run(["git","add","README.md"],cwd=r,env=env,check=True); subprocess.run(["git","commit","-q","-m","base"],cwd=r,env=env,check=True); base=subprocess.check_output(["git","rev-parse","HEAD"],cwd=r,text=True).strip(); (r/"README.md").write_text("candidate\n"); subprocess.run(["git","commit","-qam","candidate"],cwd=r,env=env,check=True); head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=r,text=True).strip(); self.assertEqual(discover_changed_files(base,head,str(r)),["README.md"])
if __name__=="__main__": unittest.main()
