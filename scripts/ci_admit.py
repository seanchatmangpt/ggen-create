#!/usr/bin/env python3
"""Manufacture an exact-head ggen-create CI admission receipt."""
from __future__ import annotations
import argparse, ast, json, os, shutil, subprocess, sys, time, tomllib
from pathlib import Path
from typing import Any, Sequence
from ci_router import LANES, RoutingRefusal, discover_changed_files, github_outputs, route_paths
TAIL_LIMIT=4000

def _run(check_id:str, command:Sequence[str], cwd:Path)->dict[str,Any]:
    start=time.monotonic(); done=subprocess.run(list(command),cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    passed=done.returncode==0
    return {"id":check_id,"command":" ".join(command),"exit_code":done.returncode,"elapsed_ms":round((time.monotonic()-start)*1000),"passed":passed,"typed_failure":None if passed else f"BUILD_BROKEN:{check_id.upper()}_FAILED","stdout_tail":done.stdout[-TAIL_LIMIT:],"stderr_tail":done.stderr[-TAIL_LIMIT:]}
def _record(check_id:str,passed:bool,detail:str="")->dict[str,Any]:
    return {"id":check_id,"command":"internal","exit_code":0 if passed else 1,"elapsed_ms":0,"passed":passed,"typed_failure":None if passed else f"BUILD_BROKEN:{check_id.upper()}_FAILED","stdout_tail":detail[-TAIL_LIMIT:] if passed else "","stderr_tail":"" if passed else detail[-TAIL_LIMIT:]}
def _parse_structured(path:Path)->None:
    data=path.read_bytes()
    if b"\x00" in data: raise ValueError("NUL byte refused")
    text=data.decode("utf-8"); suffix=path.suffix.lower()
    if suffix==".json": json.loads(text)
    elif suffix==".toml": tomllib.loads(text)
    elif suffix==".py": ast.parse(text,filename=str(path))
    elif suffix in {".yml",".yaml"}:
        if not shutil.which("ruby"): raise RuntimeError("UNSUPPORTED:YAML_PARSER_MISSING")
        done=subprocess.run(["ruby","-e","require 'yaml'; YAML.parse_file(ARGV.fetch(0))",str(path)],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        if done.returncode: raise ValueError(done.stderr.strip() or "YAML parse failed")
def _structured(root:Path,changed:list[str])->dict[str,Any]:
    start=time.monotonic(); failures=[]; parsed=[]
    for rel in changed:
        path=root/rel
        if not path.is_file() or path.suffix.lower() not in {".json",".toml",".py",".yml",".yaml"}: continue
        try: _parse_structured(path); parsed.append(rel)
        except Exception as exc: failures.append(f"{rel}: {exc}")
    return {"id":"structured_parse","command":"internal structured-file parser","exit_code":0 if not failures else 1,"elapsed_ms":round((time.monotonic()-start)*1000),"passed":not failures,"typed_failure":None if not failures else "BUILD_BROKEN:STRUCTURED_PARSE_FAILED","stdout_tail":json.dumps({"parsed":parsed},sort_keys=True),"stderr_tail":"\n".join(failures)[-TAIL_LIMIT:]}
def _shape(root:Path)->dict[str,Any]:
    failures=[]; readme=root/"README.md"
    if not readme.is_file() or not readme.read_text(encoding="utf-8").startswith("# ggen-create"): failures.append("README.md must identify ggen-create")
    for req in ("docs","ontology","scripts","tests",".github/workflows"):
        if not (root/req).is_dir(): failures.append(f"missing required CI-owned surface: {req}")
    return _record("repository_shape",not failures,"; ".join(failures) or "required surfaces present")
def _lane(root:Path,lane:str)->int:
    checks=[]
    if lane=="ci":
        checks += [_run("ci_unit",[sys.executable,"-m","unittest","discover","-s","tests","-p","test_ci_*.py"],root),_run("ci_compile",[sys.executable,"-m","py_compile","scripts/ci_router.py","scripts/ci_admit.py","tests/test_ci_router.py"],root),_structured(root,[".github/workflows/ci.yml"])]
    elif lane=="docs":
        bad=[]
        for p in sorted([root/"README.md",root/"BOOTSTRAP.md",*root.glob("docs/**/*.md")]):
            if p.is_file() and ("\x00" in p.read_text(encoding="utf-8") or not p.read_text(encoding="utf-8").strip()): bad.append(str(p.relative_to(root)))
        checks.append(_record("docs_integrity",not bad,"invalid markdown: "+", ".join(bad) if bad else "markdown UTF-8/non-empty"))
        parity = root/"scripts/gall_hygen_parity.py"
        if parity.is_file():
            checks.append(_run("hygen_docs_gall",[sys.executable,str(parity.relative_to(root)),"--root",".","--receipt","gall-hygen-parity-receipt.json"],root))
    elif lane=="ontology":
        bad=[]; allowed={".ttl",".trig",".nq",".nt",".jsonld",".rdf",".owl",".keep"}
        for p in root.glob("ontology/**/*"):
            if p.is_file():
                p.read_text(encoding="utf-8")
                if p.suffix.lower() not in allowed and p.name!=".keep": bad.append(str(p.relative_to(root)))
        checks.append(_record("ontology_surface",not bad,"unsupported ontology files: "+", ".join(bad) if bad else "ontology surface admitted"))
    elif lane=="build":
        parity = root/"scripts/gall_hygen_parity.py"
        if parity.is_file():
            checks += [
                _run("hygen_parity_unit",[sys.executable,"-m","unittest","discover","-s","tests","-p","test_parity_*.py","-v"],root),
                _run("hygen_parity_gall",[sys.executable,str(parity.relative_to(root)),"--root",".","--receipt","gall-hygen-parity-receipt.json"],root),
            ]
        if (root/"Cargo.toml").is_file():
            checks += [_run("cargo_fmt",["cargo","fmt","--all","--","--check"],root),_run("cargo_check",["cargo","check","--workspace","--all-targets"],root),_run("cargo_test",["cargo","test","--workspace","--all-targets"],root)]
        else: checks.append(_record("build_bootstrap",True,"Cargo.toml absent; parity subject executed when present"))
    print(json.dumps({"lane":lane,"checks":checks},indent=2,sort_keys=True)); return 0 if all(c["passed"] for c in checks) else 1
def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--base",default=""); p.add_argument("--head",default=""); p.add_argument("--repository",default=os.environ.get("GITHUB_REPOSITORY","")); p.add_argument("--receipt",default="ci-errc-receipt.json"); p.add_argument("--github-output",default=os.environ.get("GITHUB_OUTPUT","")); p.add_argument("--changed-file",action="append",default=[]); p.add_argument("--lane",choices=("build","ci","docs","ontology")); a=p.parse_args(argv); root=Path.cwd()
    if a.lane: return _lane(root,a.lane)
    checks=[]; failures=[]; changed=[]; routing={"fast_only":[],**{lane:[] for lane in LANES}}; outputs=github_outputs(routing)
    try:
        observed=subprocess.run(["git","rev-parse","HEAD"],cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE); actual=observed.stdout.strip(); ok=observed.returncode==0 and bool(a.head) and actual==a.head
        checks.append(_record("exact_head_identity",ok,f"expected={a.head} observed={actual}"))
        if not ok: failures.append("REFUSED:HEAD_IDENTITY_MISMATCH")
        changed=sorted(set(a.changed_file or discover_changed_files(a.base,a.head,str(root)))); routing=route_paths(changed); outputs=github_outputs(routing); checks.append(_record("changed_file_routing",True,json.dumps(routing,sort_keys=True)))
        checks += [_run("router_self_tests",[sys.executable,"-m","unittest","discover","-s","tests","-p","test_ci_*.py"],root),_run("python_compile",[sys.executable,"-m","py_compile","scripts/ci_router.py","scripts/ci_admit.py","tests/test_ci_router.py"],root),_structured(root,changed),_shape(root)]
    except RoutingRefusal as refusal: failures.append(refusal.reason); checks.append(_record("changed_file_routing",False,refusal.detail))
    except Exception as exc: failures.append("BUILD_BROKEN:FAST_GATE_INTERNAL_ERROR"); checks.append(_record("fast_gate_internal",False,repr(exc)))
    failures += [c["typed_failure"] for c in checks if c["typed_failure"]]; standing="ALIVE" if not failures else "BUILD_BROKEN"
    receipt={"schema":"ggen-create.ci.errc.receipt.v1","subject":{"repository":a.repository,"base":a.base,"head":a.head,"workflow":os.environ.get("GITHUB_WORKFLOW","local"),"run_id":os.environ.get("GITHUB_RUN_ID","local")},"errc":{"eliminate":["unowned all-PR fan-out","mutable action references"],"reduce":["deep lane frequency","time-to-first-falsifier"],"raise":["exact-head identity","deterministic routing","failure transparency"],"create":["universal fast gate","path-owned lanes","machine-readable receipt"]},"changed_files":changed,"routing":routing,"checks":checks,"failures":sorted(set(failures)),"standing":standing,"claim_ceiling":"EXACT_HEAD_FAST_AUTHORITY_AND_ROUTING_ONLY","replay":{"command":f"python3 scripts/ci_admit.py --base {a.base} --head {a.head} --repository {a.repository} --receipt {a.receipt}"}}
    Path(a.receipt).write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    if a.github_output:
        with open(a.github_output,"a",encoding="utf-8") as h:
            for key,value in outputs.items(): h.write(f"{key}={value}\n")
    print(json.dumps(receipt,indent=2,sort_keys=True)); return 0 if standing=="ALIVE" else 1
if __name__=="__main__": raise SystemExit(main())
