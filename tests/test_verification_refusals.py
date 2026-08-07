from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from ggen_create.cli import run as run_cli
from ggen_create.mcp import MCP_PROTOCOL_VERSION, McpServer
from ggen_create.model import GgenCreateError
from ggen_create.package import build_package
from ggen_create.runtime import ReceiptStore
from ggen_create.session import add_paths, set_seed, start_session
from ggen_create.skills import Broker, SkillRegistry


class VerificationRefusalTests(unittest.TestCase):
    def fixture(self, root: Path) -> tuple[Path, Path]:
        (root / "Hello.txt").write_text("Hello", encoding="utf-8")
        session = start_session(root, "greeter")
        add_paths(session, ["Hello.txt"], cwd=root)
        set_seed(session, "Hello")
        package = build_package(session, root / "packages").package_dir
        return session, package

    def test_broker_refuses_invalid_package(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            session, package = self.fixture(root)
            (package / "ggen.toml").write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(
                GgenCreateError,
                "PACKAGE_INTEGRITY_REFUSED",
            ):
                Broker(root).execute(
                    SkillRegistry().plan(
                        "package.verify",
                        {"package": str(package)},
                    ),
                    session_path=session,
                )

    def test_broker_refuses_invalid_receipt_and_chain(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            store = ReceiptStore(root)
            receipt = store.append(
                operation="test",
                state="ALIVE",
                inputs={},
                outputs={},
            )
            path = Path(receipt["path"])
            value = json.loads(path.read_text(encoding="utf-8"))
            value["operation"] = "tampered"
            path.write_text(json.dumps(value), encoding="utf-8")
            broker = Broker(root)
            registry = SkillRegistry()
            with self.assertRaisesRegex(
                GgenCreateError,
                "RECEIPT_DIGEST_REFUSED",
            ):
                broker.execute(
                    registry.plan("receipt.verify", {"path": str(path)}),
                    session_path=None,
                )
            with self.assertRaisesRegex(
                GgenCreateError,
                "RECEIPT_CHAIN_REFUSED",
            ):
                broker.execute(
                    registry.plan("receipt.chain.verify", {}),
                    session_path=None,
                )

    def test_mcp_returns_tool_error_for_invalid_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            receipt = ReceiptStore(root).append(
                operation="test",
                state="ALIVE",
                inputs={},
                outputs={},
            )
            path = Path(receipt["path"])
            value = json.loads(path.read_text(encoding="utf-8"))
            value["state"] = "BLOCKED"
            path.write_text(json.dumps(value), encoding="utf-8")

            server = McpServer(root)
            initialized = server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1"},
                    },
                }
            )
            assert initialized is not None
            server.handle(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {},
                }
            )
            response = server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "ggen_create_receipt_verify",
                        "arguments": {
                            "path": str(path.relative_to(root)),
                        },
                    },
                }
            )
            assert response is not None
            self.assertTrue(response["result"]["isError"], response)
            self.assertEqual(
                response["result"]["structuredContent"]["code"],
                "RECEIPT_DIGEST_REFUSED",
            )

    def test_cli_package_verify_raises_on_invalid_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _, package = self.fixture(root)
            (package / "ontology.ttl").write_text(
                "tampered",
                encoding="utf-8",
            )
            previous = Path.cwd()
            os.chdir(root)
            try:
                with self.assertRaisesRegex(
                    GgenCreateError,
                    "PACKAGE_INTEGRITY_REFUSED",
                ):
                    run_cli(
                        [
                            "package",
                            "verify",
                            "--package",
                            str(package),
                        ]
                    )
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
