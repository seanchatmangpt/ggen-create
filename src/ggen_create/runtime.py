from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
from typing import Any
from uuid import uuid4

from .model import GgenCreateError


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise GgenCreateError("TIMESTAMP_PARSE_REFUSED", repr(value)) from exc


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
            handle.flush()
            os.fsync(handle.fileno())
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
        latest = self.latest()
        if parent is None and latest is not None:
            parent = latest.get("receipt_digest")
        receipt_id = str(uuid4())
        payload = {
            "schema": "ggen-create-native-receipt/0.2",
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
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise GgenCreateError("RECEIPT_PARSE_REFUSED", str(exc)) from exc
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
        computed = digest_json(payload)
        valid = isinstance(claimed, str) and computed == claimed
        return {
            "path": str(path.resolve()),
            "valid": valid,
            "claimed": claimed,
            "computed": computed,
            "operation": receipt.get("operation"),
            "state": receipt.get("state"),
            "parent": receipt.get("parent"),
        }

    def verify_chain(self) -> dict[str, Any]:
        receipts = self.list()
        previous: str | None = None
        checks: list[dict[str, Any]] = []
        for receipt in receipts:
            check = self.verify(Path(receipt["path"]))
            chain_valid = receipt.get("parent") == previous
            checks.append({**check, "chain_valid": chain_valid})
            previous = receipt.get("receipt_digest")
        latest = self.latest()
        latest_valid = latest is None or latest.get("receipt_digest") == previous
        return {
            "valid": all(item["valid"] and item["chain_valid"] for item in checks)
            and latest_valid,
            "count": len(checks),
            "latest_valid": latest_valid,
            "receipts": checks,
        }


class TaskStore:
    TERMINAL = {"completed", "failed", "cancelled", "rejected"}
    INTERRUPTED = {"input_required", "auth_required"}
    TRANSITIONS = {
        "working": TERMINAL | INTERRUPTED,
        "input_required": {"working"} | TERMINAL | {"auth_required"},
        "auth_required": {"working"} | TERMINAL | {"input_required"},
    }

    def __init__(self, subject_root: Path, namespace: str):
        self.subject_root = subject_root.resolve()
        self.root = self.subject_root / ".ggen-create" / "tasks" / namespace
        self._lock = threading.RLock()

    def _path(self, task_id: str) -> Path:
        allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
        if not task_id or any(ch not in allowed for ch in task_id):
            raise GgenCreateError("TASK_ID_REFUSED", f"invalid task id: {task_id!r}")
        return self.root / f"{task_id}.json"

    @staticmethod
    def _bounded_ttl(ttl: int | None) -> int | None:
        if ttl is None:
            return None
        return max(1_000, min(int(ttl), 86_400_000))

    def _expired(self, task: dict[str, Any]) -> bool:
        ttl = task.get("ttl")
        if ttl is None:
            return False
        created = parse_timestamp(str(task["createdAt"]))
        return datetime.now(timezone.utc) >= created + timedelta(milliseconds=int(ttl))

    def _read(self, path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise GgenCreateError("TASK_PARSE_REFUSED", str(exc)) from exc
        if not isinstance(value, dict) or not isinstance(value.get("taskId"), str):
            raise GgenCreateError("TASK_PARSE_REFUSED", f"invalid task document: {path}")
        return value

    def create(
        self,
        *,
        kind: str,
        request: dict[str, Any],
        ttl: int | None = 300_000,
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
            "ttl": self._bounded_ttl(ttl),
            "pollInterval": max(50, min(int(poll_interval), 60_000)),
            "contextId": context_id,
            "request": request,
            "history": [request],
            "result": None,
            "error": None,
        }
        with self._lock:
            atomic_write_json(self._path(task_id), task)
        return task

    def get(self, task_id: str) -> dict[str, Any]:
        path = self._path(task_id)
        with self._lock:
            if not path.is_file():
                raise GgenCreateError("TASK_NOT_FOUND_REFUSED", task_id)
            task = self._read(path)
            if self._expired(task):
                path.unlink(missing_ok=True)
                raise GgenCreateError("TASK_EXPIRED_REFUSED", task_id)
            return task

    def _update(self, task: dict[str, Any]) -> dict[str, Any]:
        task["lastUpdatedAt"] = utc_now()
        with self._lock:
            atomic_write_json(self._path(task["taskId"]), task)
        return task

    def _transition(
        self,
        task_id: str,
        status: str,
        *,
        message: str,
        result: Any = None,
        error: Any = None,
    ) -> dict[str, Any]:
        task = self.get(task_id)
        current = str(task.get("status"))
        if status not in self.TRANSITIONS.get(current, set()):
            raise GgenCreateError(
                "TASK_TRANSITION_REFUSED", f"{task_id}: {current} -> {status}"
            )
        task["status"] = status
        task["statusMessage"] = message
        task["result"] = result
        task["error"] = error
        return self._update(task)

    def resume(self, task_id: str, request: dict[str, Any]) -> dict[str, Any]:
        task = self.get(task_id)
        if task["status"] not in self.INTERRUPTED:
            raise GgenCreateError("TASK_NOT_RESUMABLE_REFUSED", task_id)
        task["history"].append(request)
        task["request"] = request
        task["status"] = "working"
        task["statusMessage"] = "Additional input accepted."
        task["result"] = None
        task["error"] = None
        return self._update(task)

    def complete(self, task_id: str, result: Any) -> dict[str, Any]:
        return self._transition(
            task_id, "completed", message="Execution completed.", result=result
        )

    def fail(self, task_id: str, error: Any) -> dict[str, Any]:
        return self._transition(
            task_id, "failed", message="Execution failed.", error=error
        )

    def require_input(self, task_id: str, request: Any) -> dict[str, Any]:
        return self._transition(
            task_id,
            "input_required",
            message="Additional input is required.",
            result=request,
        )

    def require_auth(self, task_id: str, request: Any) -> dict[str, Any]:
        return self._transition(
            task_id,
            "auth_required",
            message="Additional authorization is required.",
            result=request,
        )

    def reject(self, task_id: str, error: Any) -> dict[str, Any]:
        return self._transition(
            task_id, "rejected", message="Execution was rejected.", error=error
        )

    def cancel(self, task_id: str) -> dict[str, Any]:
        return self._transition(
            task_id, "cancelled", message="Cancelled by request."
        )

    def result(self, task_id: str) -> Any:
        task = self.get(task_id)
        if task["status"] == "completed":
            return task["result"]
        if task["status"] in self.INTERRUPTED:
            return task["result"]
        if task["status"] == "failed":
            raise GgenCreateError("TASK_EXECUTION_REFUSED", json.dumps(task["error"]))
        if task["status"] == "rejected":
            raise GgenCreateError("TASK_REJECTED_REFUSED", json.dumps(task["error"]))
        if task["status"] == "cancelled":
            raise GgenCreateError("TASK_CANCELLED_REFUSED", task_id)
        raise GgenCreateError("TASK_NOT_READY_REFUSED", task_id)

    def prune(self) -> int:
        if not self.root.is_dir():
            return 0
        removed = 0
        with self._lock:
            for path in self.root.glob("*.json"):
                try:
                    task = self._read(path)
                except GgenCreateError:
                    continue
                if self._expired(task):
                    path.unlink(missing_ok=True)
                    removed += 1
        return removed

    def query(
        self,
        *,
        status: str | None = None,
        context_id: str | None = None,
        cursor: str | None = None,
        page_size: int = 50,
    ) -> dict[str, Any]:
        self.prune()
        page_size = max(1, min(int(page_size), 100))
        try:
            offset = int(cursor or "0")
        except ValueError as exc:
            raise GgenCreateError("TASK_CURSOR_REFUSED", repr(cursor)) from exc
        if offset < 0:
            raise GgenCreateError("TASK_CURSOR_REFUSED", repr(cursor))
        values = self.list()
        if status is not None:
            values = [item for item in values if item.get("status") == status]
        if context_id is not None:
            values = [item for item in values if item.get("contextId") == context_id]
        page = values[offset : offset + page_size]
        next_offset = offset + len(page)
        return {
            "tasks": page,
            "totalSize": len(values),
            "pageSize": len(page),
            "nextCursor": str(next_offset) if next_offset < len(values) else None,
        }

    def list(self) -> list[dict[str, Any]]:
        if not self.root.is_dir():
            return []
        values: list[dict[str, Any]] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                task = self._read(path)
            except GgenCreateError:
                continue
            if not self._expired(task):
                values.append(task)
        return values
