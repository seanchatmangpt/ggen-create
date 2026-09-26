from __future__ import annotations
import hashlib
from pathlib import Path
import re

POLICY = Path(__file__).resolve().parents[2] / "ontology" / "phase2-admission.ttl"
TERM = re.compile(r"gc:([A-Za-z0-9_]+)")
STATE = re.compile(r'gc:state\s+"([A-Z_]+)"')

def evaluate(path: Path = POLICY) -> dict[str, object]:
    data = path.read_bytes()
    text = data.decode()
    policy = text.split("gc:Phase2Policy", 1)[1].split(".", 1)[0]
    required = tuple(TERM.findall(policy.split("gc:requires", 1)[1]))
    states = {}
    for name in required:
        match = re.search(rf"gc:{name}\s+a\s+gc:Capability\s*;\s*gc:state\s+\"([A-Z_]+)\"", text)
        if not match:
            raise ValueError(f"POLICY_TURTLE_INVALID: {name}")
        states[name] = match.group(1)
    blockers = [name for name in required if states[name] not in {"ADMITTED", "ALIVE"}]
    return {"policy_digest": "sha256:" + hashlib.sha256(data).hexdigest(), "state": "ALIVE" if not blockers else "PARTIAL_ALIVE", "requirements": states, "blockers": blockers}
