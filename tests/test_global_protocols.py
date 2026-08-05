from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ggen_create.a2a import A2AService
from ggen_create.mcp import MCP_PROTOCOL_VERSION, McpServer
from ggen_create.model import GgenCreateError
from ggen_create.skills import Broker, SkillRegistry


class GlobalProtocolTests(unittest.TestCase):
    def test_broker_enforces_session_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            broker = Broker(root)
            registry = SkillRegistry()

            with self.assertRaisesRegex(
                GgenCreateError,
                "SESSION_REQUIRED_REFUSED",
            ):
                broker.execute(
                    registry.plan("capture.inspect", {}),
                    session_path=None,
                )

            skills = broker.execute(
                registry.plan("skills.list", {}),
                session_path=None,
            )
            self.assertGreaterEqual(len(skills["result"]), 16)

            route = broker.execute(
                registry.plan(
                    "agents.route",
                    {"goal": "calculate runtime standing"},
                ),
                session_path=None,
            )
            self.assertEqual(route["result"]["skill"], "doctor.inspect")

            doctor = broker.execute(
                registry.plan("doctor.inspect", {}),
                session_path=None,
            )
            self.assertEqual(doctor["result"]["state"], "PARTIAL_ALIVE")
            self.assertEqual(
                doctor["result"]["checks"]["capture"]["state"],
                "BLOCKED",
            )

            ledger = broker.execute(
                registry.plan("receipt.chain.verify", {}),
                session_path=None,
            )
            self.assertTrue(ledger["result"]["valid"])
            self.assertEqual(ledger["result"]["count"], 0)

    def test_mcp_global_tools_work_without_capture(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            server = McpServer(root)
            initialized = server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "capabilities": {"tasks": {}},
                        "clientInfo": {"name": "test", "version": "1"},
                    },
                }
            )
            assert initialized is not None
            self.assertEqual(
                initialized["result"]["protocolVersion"],
                MCP_PROTOCOL_VERSION,
            )
            self.assertIsNone(
                server.handle(
                    {
                        "jsonrpc": "2.0",
                        "method": "notifications/initialized",
                        "params": {},
                    }
                )
            )

            for request_id, name, arguments in (
                (2, "ggen_create_agent_route", {"goal": "runtime health"}),
                (3, "ggen_create_receipt_chain_verify", {}),
                (4, "ggen_create_doctor", {}),
            ):
                response = server.handle(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "method": "tools/call",
                        "params": {"name": name, "arguments": arguments},
                    }
                )
                assert response is not None
                self.assertFalse(response["result"]["isError"], response)

            capture = server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {
                        "name": "ggen_create_status",
                        "arguments": {},
                    },
                }
            )
            assert capture is not None
            self.assertTrue(capture["result"]["isError"])
            self.assertEqual(
                capture["result"]["structuredContent"]["code"],
                "NO_SESSION_REFUSED",
            )

    def test_a2a_global_tasks_work_without_capture(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            service = A2AService(
                root,
                base_url="http://127.0.0.1:8765",
            )
            doctor = service.handle_rpc(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "SendMessage",
                    "params": {
                        "message": {
                            "messageId": "doctor-1",
                            "role": "ROLE_USER",
                            "parts": [
                                {
                                    "data": {
                                        "operation": "doctor.inspect",
                                        "arguments": {},
                                    }
                                }
                            ],
                        }
                    },
                }
            )
            self.assertEqual(
                doctor["result"]["task"]["status"]["state"],
                "TASK_STATE_COMPLETED",
            )

            skills = service.handle_rpc(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "SendMessage",
                    "params": {
                        "message": {
                            "messageId": "skills-1",
                            "role": "ROLE_USER",
                            "parts": [
                                {
                                    "data": {
                                        "operation": "skills.list",
                                        "arguments": {},
                                    }
                                }
                            ],
                        }
                    },
                }
            )
            self.assertEqual(
                skills["result"]["task"]["status"]["state"],
                "TASK_STATE_COMPLETED",
            )


if __name__ == "__main__":
    unittest.main()
