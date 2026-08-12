from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from ggen_create.connection import export_generalized_connection


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _write_valid_package(root: Path) -> Path:
    package = root / "global-cloud-factory"
    package.mkdir()
    files = {
        "ggen.toml": b'[project]\nname = "global-cloud-factory"\n',
        "ontology.ttl": b'@prefix ex: <urn:example:> .\nex:subject ex:name "Global" .\n',
        "ggen-create-package.json": json.dumps({
            "schema": "ggen-create-package/0.2",
            "generator": "global-cloud-factory",
            "parameter": {"id": "name", "seed": "Global", "value": "Global"},
            "gen_parent_dir": False,
            "files": [],
        }, indent=2, sort_keys=True).encode(),
    }
    for rel, data in files.items():
        (package / rel).write_bytes(data)
    payload = {
        "schema": "ggen-create-package-receipt/0.2",
        "algorithm": "sha256",
        "operation": "package-build",
        "generator": "global-cloud-factory",
        "parameter_value": "Global",
        "parent": None,
        "files": {rel: _sha(data) for rel, data in sorted(files.items())},
    }
    receipt = {**payload, "receipt_digest": _sha(_canonical(payload))}
    (package / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True))
    return package


def _parent(path: Path) -> None:
    value = {
        "schema": "urn:ggen:enterprise-connection:v1",
        "connection_id": "urn:test:connection",
        "stage": "RECONSTITUTE",
        "producer": {"repository": "seanchatmangpt/ggen-legacy", "revision": "a" * 40, "component": "GL-CONN-001"},
        "subject": {"id": "subject", "kind": "enterprise-architecture-reconstitution", "revision": "sha256:" + "0" * 64},
        "architecture": {"graph": None, "capabilities": ["global-cloud"], "constraints": ["ZERO_UNRECEIPTED_ACTUATION"]},
        "packs": [],
        "artifacts": [],
        "authority": {"ceiling": "CONSTRUCT_ONLY", "do_authority": False},
        "standing": {"state": "PARTIAL_ALIVE", "claim": "bounded"},
        "parent": None,
        "evidence": [],
        "next": [{"consumer": "seanchatmangpt/ggen-create", "operation": "generalize"}],
        "labels": {},
    }
    path.write_bytes(_canonical(value))


class ConnectionTest(unittest.TestCase):
    def test_generalizes_only_verified_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = root / "parent.json"
            _parent(parent)
            package = _write_valid_package(root)
            first = root / "first.json"
            second = root / "second.json"
            a = export_generalized_connection(parent, package, "b" * 40, first)
            b = export_generalized_connection(parent, package, "b" * 40, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(a, b)
            self.assertEqual(a["stage"], "GENERALIZE")
            self.assertEqual(a["packs"][0]["admission"], "CANDIDATE")
            self.assertFalse(a["authority"]["do_authority"])
            self.assertEqual(a["standing"]["state"], "PARTIAL_ALIVE")
            self.assertTrue(all(x["role"].startswith("ggen-create:") for x in a["artifacts"]))


if __name__ == "__main__":
    unittest.main()
