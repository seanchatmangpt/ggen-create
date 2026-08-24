"""Enterprise Connection v1 projection for verified ggen-create factories.

Consumes a RECONSTITUTE envelope plus a real package that passes the native
integrity verifier. Emits GENERALIZE without marketplace admission or DO authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .integrity import require_valid_package

SCHEMA="urn:ggen:enterprise-connection:v1"; HEX40=re.compile(r"^[0-9a-f]{40}$")
class ConnectionRefusal(ValueError): pass

def canonical_bytes(value: Any)->bytes: return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")
def sha256_bytes(data: bytes)->str: return "sha256:"+hashlib.sha256(data).hexdigest()

def _load_parent(path: Path):
    raw=path.read_bytes()
    try: value=json.loads(raw)
    except json.JSONDecodeError as exc: raise ConnectionRefusal(f"REFUSED:PARENT_JSON:{exc}") from exc
    if not isinstance(value,dict) or value.get("schema")!=SCHEMA: raise ConnectionRefusal("REFUSED:PARENT_SCHEMA")
    if raw!=canonical_bytes(value): raise ConnectionRefusal("REFUSED:PARENT_NON_CANONICAL")
    if value.get("stage")!="RECONSTITUTE": raise ConnectionRefusal(f"REFUSED:PARENT_STAGE:{value.get('stage')!r}")
    if value.get("authority",{}).get("do_authority") is not False: raise ConnectionRefusal("REFUSED:PARENT_AMBIENT_ACTUATION")
    return value,raw

def _media_type(path: str)->str:
    if path.endswith(".json"): return "application/json"
    if path.endswith(".ttl"): return "text/turtle"
    if path.endswith(".toml"): return "application/toml"
    if path.endswith((".tmpl",".tera")): return "text/plain"
    return "application/octet-stream"

def export_generalized_connection(parent_path: Path,package_dir: Path,revision: str,out: Path)->dict[str,Any]:
    if not HEX40.fullmatch(revision): raise ConnectionRefusal(f"REFUSED:REVISION:{revision}")
    parent,parent_raw=_load_parent(parent_path); package_dir=package_dir.resolve(); integrity=require_valid_package(package_dir)
    metadata_path=package_dir/"ggen-create-package.json"; receipt_path=package_dir/"receipt.json"
    try: metadata=json.loads(metadata_path.read_text(encoding="utf-8")); receipt=json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc: raise ConnectionRefusal(f"REFUSED:PACKAGE_METADATA:{exc}") from exc
    if not isinstance(metadata,dict) or metadata.get("schema")!="ggen-create-package/0.2": raise ConnectionRefusal("REFUSED:PACKAGE_METADATA_SCHEMA")
    if not isinstance(receipt,dict) or receipt.get("schema")!="ggen-create-package-receipt/0.2": raise ConnectionRefusal("REFUSED:PACKAGE_RECEIPT_SCHEMA")
    generator=metadata.get("generator")
    if not isinstance(generator,str) or not generator: raise ConnectionRefusal("REFUSED:GENERATOR_ID")
    prefix=package_dir.name; factory_artifacts=[]
    for path in sorted(package_dir.rglob("*")):
        if path.is_symlink(): raise ConnectionRefusal(f"REFUSED:PACKAGE_SYMLINK:{path}")
        if not path.is_file(): continue
        rel=path.relative_to(package_dir).as_posix(); factory_artifacts.append({"path":f"{prefix}/{rel}","role":"ggen-create:candidate-factory-file","media_type":_media_type(rel),"digest":sha256_bytes(path.read_bytes())})
    receipt_file_digest=sha256_bytes(receipt_path.read_bytes())
    env={**parent,"stage":"GENERALIZE","producer":{"repository":"seanchatmangpt/ggen-create","revision":revision,"component":"enterprise-connection-generalizer"},"subject":{**parent["subject"],"kind":"generalized-enterprise-architecture-factory","revision":str(receipt.get("receipt_digest") or receipt_file_digest)},"packs":parent["packs"]+[{"name":generator,"version":None,"digest":receipt_file_digest,"admission":"CANDIDATE"}],"artifacts":parent["artifacts"]+factory_artifacts,"authority":{"ceiling":"CONSTRUCT_ONLY","do_authority":False},"standing":{"state":"PARTIAL_ALIVE","claim":"GGEN_CREATE_FACTORY_INTEGRITY_VERIFIED; MARKETPLACE_ADMISSION_NOT_ESTABLISHED"},"parent":{"digest":sha256_bytes(parent_raw),"producer":f"{parent['producer']['repository']}@{parent['producer']['revision']}"},"evidence":parent["evidence"]+[{"kind":"ggen-create-package-receipt","identity":str(receipt.get("receipt_digest") or integrity.get("claimed_receipt_digest")),"digest":receipt_file_digest}],"next":[{"consumer":"seanchatmangpt/ggen-marketplace","operation":"catalog"}],"labels":{**parent["labels"],"candidate_factory":generator,"candidate_factory_integrity":"VERIFIED","candidate_factory_prefix":prefix}}
    data=canonical_bytes(env); out.parent.mkdir(parents=True,exist_ok=True); out.write_bytes(data); return env

def main(argv=None)->int:
    parser=argparse.ArgumentParser(); parser.add_argument("--parent",type=Path,required=True); parser.add_argument("--package",type=Path,required=True); parser.add_argument("--revision",required=True); parser.add_argument("--out",type=Path,required=True); args=parser.parse_args(argv)
    try: env=export_generalized_connection(args.parent,args.package,args.revision,args.out)
    except (ConnectionRefusal,OSError,ValueError) as exc: print(json.dumps({"standing":"REFUSED","error":str(exc)},sort_keys=True)); return 2
    print(json.dumps({"standing":env["standing"]["state"],"stage":env["stage"],"digest":sha256_bytes(args.out.read_bytes()),"out":str(args.out),"do_authority":False},sort_keys=True)); return 0

if __name__=="__main__": raise SystemExit(main())
