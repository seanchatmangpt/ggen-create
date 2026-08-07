from __future__ import annotations


def verify_script() -> str:
    return r'''#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, stat
from pathlib import Path

EXCLUDED={".git",".ggen-create",".hg",".svn",".mypy_cache",".pytest_cache",".ruff_cache",".tox",".venv","__pycache__","node_modules","target"}
def canonical(value): return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def dj(value): return "sha256:"+hashlib.sha256(canonical(value)).hexdigest()
def df(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return "sha256:"+h.hexdigest()
def fm(path): return f"{stat.S_IMODE(path.stat().st_mode):04o}"
def outputs(root):
    files=[p for p in sorted(root.rglob("*")) if p.is_file() and p.name!="receipt.json"]
    return ({p.relative_to(root).as_posix():df(p) for p in files},{p.relative_to(root).as_posix():fm(p) for p in files})
def replay(subject,root,manifest):
    admitted={item["path"]:item for item in manifest["files"]}; observed=set(); differences=[]
    for current,dirs,files in os.walk(subject,topdown=True,followlinks=False):
        cp=Path(current); kept=[]
        for name in sorted(dirs):
            p=cp/name
            if name in EXCLUDED: continue
            if p.is_symlink(): differences.append({"path":p.relative_to(subject).as_posix(),"reason":"symlink"}); continue
            resolved=p.resolve()
            if resolved==root or resolved.is_relative_to(root): continue
            kept.append(name)
        dirs[:]=kept
        for name in sorted(files):
            p=cp/name; rel=p.relative_to(subject).as_posix()
            if p.resolve().is_relative_to(root): continue
            if p.is_symlink(): differences.append({"path":rel,"reason":"symlink"}); continue
            try: mode=p.lstat().st_mode
            except OSError: differences.append({"path":rel,"reason":"stat"}); continue
            if not stat.S_ISREG(mode): differences.append({"path":rel,"reason":"special"}); continue
            observed.add(rel)
    for rel,item in admitted.items():
        p=subject/rel
        if rel not in observed: differences.append({"path":rel,"reason":"missing"})
        elif df(p)!=item["sha256"]: differences.append({"path":rel,"reason":"digest"})
        elif fm(p)!=item["mode"]: differences.append({"path":rel,"reason":"mode"})
        elif p.stat().st_size!=item["size"]: differences.append({"path":rel,"reason":"size"})
    for rel in sorted(observed-set(admitted)): differences.append({"path":rel,"reason":"unadmitted"})
    return differences
def main():
    p=argparse.ArgumentParser(); p.add_argument("bundle",nargs="?",default="."); p.add_argument("--subject")
    a=p.parse_args(); root=Path(a.bundle).resolve(); receipt=json.loads((root/"receipt.json").read_text()); manifest=json.loads((root/"manifest.json").read_text()); contract=json.loads((root/"receiving-contract.json").read_text())
    actual,modes=outputs(root); expected=receipt["outputs"]; expected_modes=receipt["output_modes"]
    checks={"output_set":set(actual)==set(expected),"output_digests":actual==expected,"output_modes":modes==expected_modes}
    payload={k:v for k,v in receipt.items() if k!="receipt_digest"}; checks["receipt_digest"]=dj(payload)==receipt.get("receipt_digest")
    checks["producer_identity"]=manifest.get("producer_identity")==contract.get("producer_identity")==receipt.get("producer_identity")
    differences=[]
    if a.subject: differences=replay(Path(a.subject).resolve(),root,manifest); checks["subject_replay"]=not differences
    valid=all(checks.values()); print(json.dumps({"checks":checks,"differences":differences,"valid":valid,"state":"ALIVE" if valid else "BUILD_BROKEN"},indent=2,sort_keys=True)); raise SystemExit(0 if valid else 1)
if __name__=="__main__": main()
'''


def replay_script() -> str:
    return r'''#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, stat
from pathlib import Path

EXCLUDED={".git",".ggen-create",".hg",".svn",".mypy_cache",".pytest_cache",".ruff_cache",".tox",".venv","__pycache__","node_modules","target"}
def df(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return "sha256:"+h.hexdigest()
def fm(path): return f"{stat.S_IMODE(path.stat().st_mode):04o}"
def main():
    p=argparse.ArgumentParser(); p.add_argument("bundle",nargs="?",default="."); p.add_argument("--subject",required=True)
    a=p.parse_args(); root=Path(a.bundle).resolve(); subject=Path(a.subject).resolve(); manifest=json.loads((root/"manifest.json").read_text()); admitted={item["path"]:item for item in manifest["files"]}; observed=set(); differences=[]
    for current,dirs,files in os.walk(subject,topdown=True,followlinks=False):
        cp=Path(current); kept=[]
        for name in sorted(dirs):
            pth=cp/name
            if name in EXCLUDED: continue
            if pth.is_symlink(): differences.append({"path":pth.relative_to(subject).as_posix(),"reason":"symlink"}); continue
            resolved=pth.resolve()
            if resolved==root or resolved.is_relative_to(root): continue
            kept.append(name)
        dirs[:]=kept
        for name in sorted(files):
            pth=cp/name; rel=pth.relative_to(subject).as_posix()
            if pth.resolve().is_relative_to(root): continue
            if pth.is_symlink(): differences.append({"path":rel,"reason":"symlink"}); continue
            try: mode=pth.lstat().st_mode
            except OSError: differences.append({"path":rel,"reason":"stat"}); continue
            if not stat.S_ISREG(mode): differences.append({"path":rel,"reason":"special"}); continue
            observed.add(rel)
    for rel,item in admitted.items():
        pth=subject/rel
        if rel not in observed: differences.append({"path":rel,"reason":"missing"})
        elif df(pth)!=item["sha256"]: differences.append({"path":rel,"reason":"digest"})
        elif fm(pth)!=item["mode"]: differences.append({"path":rel,"reason":"mode"})
        elif pth.stat().st_size!=item["size"]: differences.append({"path":rel,"reason":"size"})
    for rel in sorted(observed-set(admitted)): differences.append({"path":rel,"reason":"unadmitted"})
    match=not differences; print(json.dumps({"subject_digest":manifest["subject"]["digest"],"differences":differences,"replay_match":match,"state":"ALIVE" if match else "BUILD_BROKEN"},indent=2,sort_keys=True)); raise SystemExit(0 if match else 1)
if __name__=="__main__": main()
'''
