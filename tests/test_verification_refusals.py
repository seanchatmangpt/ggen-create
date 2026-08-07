from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest

from fastmcp import Client

from ggen_create.cli import run as run_cli
from ggen_create.mcp import create_mcp_server
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

            async def call_tool() -> None:
                mcp = create_mcp_server(root)
                async with Client(mcp) as client:
                    response = await client.call_tool(
                        "ggen_create_receipt_verify",
                        {"path": str(path.relative_to(root))},
                        raise_on_error=False,
                    )
                    self.assertTrue(response.is_error, response)
                    self.assertEqual(
                        response.structured_content["code"],
                        "RECEIPT_DIGEST_REFUSED",
                    )

            asyncio.run(call_tool())

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
