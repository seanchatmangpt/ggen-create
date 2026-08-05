from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any
from uuid import uuid4

from .model import GgenCreateError


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def digest_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def digest_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return "sha256:" + hasher.hexdigest()


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp = Path(raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, default=str)
            handle.write("\n")
        os.replace(temp, path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


def require_under(root: Path, candidate: Path, code: str = "PATH_ESCAPE_REFUSED") -> Path:
    root = root.resolve()
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise GgenCreateError(code, f"{candidate} is outside {root}") from exc
    return candidate


@dataclass(frozen=True)
class Intent:
    intent_id: str
    action: str
    arguments: dict[str, Any]
    authority: str
    requires_confirmation: bool
    created_at: str
    digest: str

    @classmethod
    def create(
        cls,
        action: str,
        arguments: dict[str, Any],
        *,
        authority: str,
        requires_confirmation: bool,
    ) -> "Intent":
        body = {
            "intent_id": str(uuid4()),
            "action": action,
            "arguments": arguments,
            "authority": authority,
            "requires_confirmation": requires_confirmation,
            "created_at": utc_now(),
        }
        return cls(**body, digest=digest_json(body))

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "action": self.action,
            "arguments": self.arguments,
            "authority": self.authority,
            "requires_confirmation": self.requires_confirmation,
            "created_at": self.created_at,
            "digest": self.digest,
        }

    def verify(self) -> None:
        body = self.to_dict()
        claimed = body.pop("digest")
        if digest_json(body) != claimed:
            raise GgenCreateError(
                "INTENT_DIGEST_REFUSED", f"intent {self.intent_id} digest mismatch"
            )


class ReceiptStore:
    def __init__(self, subject_root: Path):
        self.subject_root = subject_root.resolve()
        self.root = self.subject_root / ".ggen-create" / "receipts"

    def append(
        self,
        *,
        operation: str,
        state: str,
        inputs: dict[str, Any],
        outputs: dict[str, Any],
        parent: str | None = None,
    ) -> dict[str, Any]:
        receipt_id = str(uuid4())
        payload = {
            "schema": "ggen-create-native-receipt/0.1",
            "receipt_id": receipt_id,
            "timestamp": utc_now(),
            "operation": operation,
            "state": state,
            "subject_root": str(self.subject_root),
            "inputs": inputs,
            "outputs": outputs,
            "parent": parent,
            "algorithm": "sha256",
        }
        receipt = {**payload, "receipt_digest": digest_json(payload)}
        path = self.root / f"{receipt_id}.json"
        atomic_write_json(path, receipt)
        atomic_write_json(self.root / "latest.json", receipt)
        return {**receipt, "path": str(path)}

    def list(self) -> list[dict[str, Any]]:
        if not self.root.is_dir():
            return []
        result: list[dict[str, Any]] = []
        for path in sorted(self.root.glob("*.json")):
            if path.name == "latest.json":
                continue
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            value["path"] = str(path)
            result.append(value)
        return result

    def latest(self) -> dict[str, Any] | None:
        path = self.root / "latest.json"
        if not path.is_file():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        value["path"] = str(path)
        return value

    @staticmethod
    def verify(path: Path) -> dict[str, Any]:
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise GgenCreateError("RECEIPT_PARSE_REFUSED", str(exc)) from exc
        claimed = receipt.get("receipt_digest")
        payload = {key: value for key, value in receipt.items() if key != "receipt_digest"}
        valid = isinstance(claimed, str) and digest_json(payload) == claimed
        return {
            "path": str(path.resolve()),
            "valid": valid,
            "claimed": claimed,
            "computed": digest_json(payload),
            "operation": receipt.get("operation"),
            "state": receipt.get("state"),
        }


class TaskStore:
    TERMINAL = {"completed", "failed", "cancelled"}

    def __init__(self, subject_root: Path, namespace: str):
        self.subject_root = subject_root.resolve()
        self.root = self.subject_root / ".ggen-create" / "tasks" / namespace

    def _path(self, task_id: str) -> Path:
        if not task_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in task_id):
            raise GgenCreateError("TASK_ID_REFUSED", f"invalid task id: {task_id!r}")
        return self.root / f"{task_id}.json"

    def create(
        self,
        *,
        kind: str,
        request: dict[str, Any],
        ttl: int = 300_000,
        poll_interval: int = 250,
        context_id: str | None = None,
    ) -> dict[str, Any]:
        task_id = str(uuid4())
        now = utc_now()
        task = {
            "taskId": task_id,
            "kind": kind,
            "status": "working",
            "statusMessage": "Accepted for bounded execution.",
            "createdAt": now,
            "lastUpdatedAt": now,
            "ttl": max(1_000, min(int(ttl), 86_400_000)),
            "pollInterval": max(50, min(int(poll_interval), 60_000)),
            "contextId": context_id,
            "request": request,
            "result": None,
            "error": None,
        }
        atomic_write_json(self._path(task_id), task)
        return task

    def get(self, task_id: str) -> dict[str, Any]:
        path = self._path(task_id)
        if not path.is_file():
            raise GgenCreateError("TASK_NOT_FOUND_REFUSED", task_id)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise GgenCreateError("TASK_PARSE_REFUSED", str(exc)) from exc

    def _update(self, task: dict[str, Any]) -> dict[str, Any]:
        task["lastUpdatedAt"] = utc_now()
        atomic_write_json(self._path(task["taskId"]), task)
        return task

    def complete(self, task_id: str, result: Any) -> dict[str, Any]:
        task = self.get(task_id)
        if task["status"] in self.TERMINAL:
            raise GgenCreateError("TASK_TERMINAL_REFUSED", task_id)
        task["status"] = "completed"
        task["statusMessage"] = "Execution completed."
        task["result"] = result
        return self._update(task)

    def fail(self, task_id: str, error: Any) -> dict[str, Any]:
        task = self.get(task_id)
        if task["status"] in self.TERMINAL:
            raise GgenCreateError("TASK_TERMINAL_REFUSED", task_id)
        task["status"] = "failed"
        task["statusMessage"] = "Execution failed."
        task["error"] = error
        return self._update(task)

    def cancel(self, task_id: str) -> dict[str, Any]:
        task = self.get(task_id)
        if task["status"] in self.TERMINAL:
            raise GgenCreateError("TASK_NOT_CANCELABLE_REFUSED", task_id)
        task["status"] = "cancelled"
        task["statusMessage"] = "Cancelled by request."
        return self._update(task)

    def result(self, task_id: str) -> Any:
        task = self.get(task_id)
        if task["status"] == "completed":
            return task["result"]
        if task["status"] == "failed":
            raise GgenCreateError("TASK_EXECUTION_REFUSED", json.dumps(task["error"]))
        if task["status"] == "cancelled":
            raise GgenCreateError("TASK_CANCELLED_REFUSED", task_id)
        raise GgenCreateError("TASK_NOT_READY_REFUSED", task_id)

    def list(self) -> list[dict[str, Any]]:
        if not self.root.is_dir():
            return []
        values: list[dict[str, Any]] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                values.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return values
