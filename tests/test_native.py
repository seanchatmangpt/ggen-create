from __future__ import annotations

import json
from pathlib import Path
import tempfile
import time
import unittest

from ggen_create.a2a import A2AService
from ggen_create.agents import AgentRuntime
from ggen_create.automatic import (
    automatic_plan,
    run_automatic,
    watch_automatic,
)
from ggen_create.autonomic import AutonomicPolicy, run_autonomic
from ggen_create.doctor import doctor_report
from ggen_create.integrity import verify_package
from ggen_create.mcp import MCP_PROTOCOL_VERSION, McpServer
from ggen_create.model import APP_VERSION, GgenCreateError
from ggen_create.runtime import ReceiptStore, TaskStore, atomic_write_json
from ggen_create.selfplay import run_selfplay
from ggen_create.session import add_paths, set_seed, start_session
from ggen_create.skills import Broker, SkillRegistry


class NativeTests(unittest.TestCase):
    def fixture(self, root: Path) -> Path:
        (root / "Hello.txt").write_text(
            "Hello hello\n",
            encoding="utf-8",
        )
        session = start_session(root, "greeter")
        add_paths(session, ["Hello.txt"], cwd=root)
        set_seed(session, "Hello")
        return session

    def poll_mcp(
        self,
        server: McpServer,
        task_id: str,
    ) -> dict[str, object]:
        for index in range(200):
            response = server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1000 + index,
                    "method": "tasks/get",
                    "params": {"taskId": task_id},
                }
            )
            assert response is not None
            task = response["result"]
            if task["status"] != "working":
                return task
            time.sleep(0.01)
        self.fail(f"MCP task did not complete: {task_id}")

    def test_version_is_canonical(self) -> None:
        self.assertEqual(APP_VERSION, "0.4.0")

    def test_automatic_plan_apply_watch_and_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            session = self.fixture(root)
            output = root / "_ggen"
            plan = automatic_plan(session, output_root=output)
            self.assertEqual(plan["state"], "CANDIDATE")
            with self.assertRaisesRegex(
                GgenCreateError,
                "ACTUATION_CONFIRMATION_REQUIRED_REFUSED",
            ):
                run_automatic(
                    session,
                    output_root=output,
                    apply=True,
                    confirm=False,
                )
            report = run_automatic(
                session,
                output_root=output,
                apply=True,
                confirm=True,
            )
            self.assertEqual(report["state"], "ALIVE")
            package = Path(report["executed"][0]["package"])
            self.assertTrue(verify_package(package)["valid"])
            stable = watch_automatic(
                session,
                output_root=output,
                cycles=1,
                confirm=True,
            )
            self.assertTrue(stable["converged"])
            self.assertEqual(stable["cycles"][0]["state"], "STABLE")
            self.assertEqual(stable["cycles"][0]["executed"], [])

            (package / "ggen.toml").write_text(
                "[project]\nname = \"tampered\"\n",
                encoding="utf-8",
            )
            self.assertFalse(verify_package(package)["valid"])
            repair = watch_automatic(
                session,
                output_root=output,
                cycles=1,
                confirm=True,
            )
            self.assertEqual(
                repair["cycles"][0]["reason"],
                "PACKAGE_INTEGRITY_DRIFT",
            )
            self.assertTrue(verify_package(package)["valid"])

    def test_autonomic_recovers_corruption_and_converges(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            session = self.fixture(root)
            output = root / "_ggen"
            initial = run_automatic(
                session,
                output_root=output,
                apply=True,
                confirm=True,
            )
            package = Path(initial["executed"][0]["package"])
            (package / "ontology.ttl").write_text(
                "corrupt",
                encoding="utf-8",
            )
            report = run_autonomic(
                session,
                output_root=output,
                policy=AutonomicPolicy(
                    max_cycles=3,
                    stable_cycles=1,
                    apply=True,
                    confirm=True,
                ),
            )
            self.assertTrue(report["converged"])
            self.assertEqual(report["state"], "ALIVE")
            self.assertTrue(verify_package(package)["valid"])
            self.assertEqual(
                report["cycles"][0]["plan"]["reason"],
                "PACKAGE_CORRUPT",
            )

    def test_agent_authority_broker_and_failure_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            session = self.fixture(root)
            agents = AgentRuntime(root)
            self.assertEqual(
                agents.route("manufacture package")["agent"],
                "manufacturing-architect",
            )
            with self.assertRaisesRegex(
                GgenCreateError,
                "AGENT_SKILL_AUTHORITY_REFUSED",
            ):
                agents.plan("receiver", "package.build", {})
            registry = SkillRegistry()
            intent = registry.plan(
                "package.build",
                {"output_root": str(root / "_ggen")},
            )
            broker = Broker(root)
            with self.assertRaisesRegex(
                GgenCreateError,
                "ACTUATION_CONFIRMATION_REQUIRED_REFUSED",
            ):
                broker.execute(intent, session_path=session)
            result = broker.execute(
                intent,
                session_path=session,
                confirm=True,
            )
            self.assertEqual(result["state"], "ALIVE")
            with self.assertRaisesRegex(
                GgenCreateError,
                "PATH_ESCAPE_REFUSED",
            ):
                broker.execute(
                    registry.plan(
                        "package.build",
                        {"output_root": str(root.parent / "escape")},
                    ),
                    session_path=session,
                    confirm=True,
                )
            receipts = ReceiptStore(root).list()
            self.assertTrue(any(item["state"] == "BLOCKED" for item in receipts))

    def test_receipt_chain_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            store = ReceiptStore(root)
            first = store.append(
                operation="one",
                state="ALIVE",
                inputs={},
                outputs={"value": 1},
            )
            store.append(
                operation="two",
                state="ALIVE",
                inputs={},
                outputs={"value": 2},
            )
            self.assertTrue(store.verify_chain()["valid"])
            path = Path(first["path"])
            value = json.loads(path.read_text(encoding="utf-8"))
            value["outputs"]["value"] = 99
            atomic_write_json(path, value)
            chain = store.verify_chain()
            self.assertFalse(chain["valid"])
            self.assertFalse(chain["receipts"][0]["valid"])

    def test_task_lifecycle_ttl_pagination_and_resume(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            store = TaskStore(root, "test")
            interrupted = store.create(
                kind="write",
                request={"step": 1},
                context_id="context-1",
            )
            store.require_input(
                interrupted["taskId"],
                {"required": "confirm"},
            )
            resumed = store.resume(
                interrupted["taskId"],
                {"step": 2, "confirm": True},
            )
            self.assertEqual(resumed["status"], "working")
            completed = store.complete(
                interrupted["taskId"],
                {"ok": True},
            )
            self.assertEqual(completed["status"], "completed")
            self.assertEqual(len(completed["history"]), 2)
            with self.assertRaisesRegex(
                GgenCreateError,
                "TASK_NOT_CANCELABLE_REFUSED",
            ):
                store.cancel(interrupted["taskId"])

            for index in range(3):
                task = store.create(
                    kind="page",
                    request={"index": index},
                    context_id="context-2",
                )
                store.complete(task["taskId"], {"index": index})
            first_page = store.query(
                status="completed",
                cursor="0",
                page_size=2,
            )
            self.assertEqual(first_page["pageSize"], 2)
            self.assertIsNotNone(first_page["nextCursor"])

            expiring = store.create(
                kind="ttl",
                request={},
                ttl=1000,
            )
            expiring["createdAt"] = "2000-01-01T00:00:00Z"
            atomic_write_json(store._path(expiring["taskId"]), expiring)
            with self.assertRaisesRegex(
                GgenCreateError,
                "TASK_EXPIRED_REFUSED",
            ):
                store.get(expiring["taskId"])

    def test_mcp_lifecycle_schema_resources_and_durable_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.fixture(root)
            server = McpServer(root)
            pre_ready = server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list",
                    "params": {},
                }
            )
            assert pre_ready is not None
            self.assertEqual(
                pre_ready["error"]["message"],
                "MCP_LIFECYCLE_REFUSED",
            )
            unsupported = server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "1900-01-01",
                        "capabilities": {},
                    },
                }
            )
            assert unsupported is not None
            self.assertIn("error", unsupported)
            initialized = server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
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
            tools = server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/list",
                    "params": {},
                }
            )
            assert tools is not None
            self.assertGreaterEqual(len(tools["result"]["tools"]), 9)
            resources = server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "resources/list",
                    "params": {},
                }
            )
            assert resources is not None
            self.assertEqual(len(resources["result"]["resources"]), 4)
            invalid = server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "tools/call",
                    "params": {
                        "name": "ggen_create_apply",
                        "arguments": {
                            "confirm": True,
                            "unexpected": True,
                        },
                    },
                }
            )
            assert invalid is not None
            self.assertTrue(invalid["result"]["isError"])
            task_response = server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 7,
                    "method": "tools/call",
                    "params": {
                        "name": "ggen_create_apply",
                        "arguments": {
                            "confirm": True,
                            "output_root": "_ggen",
                        },
                        "task": {"ttl": 60_000, "pollInterval": 50},
                    },
                }
            )
            assert task_response is not None
            task_id = task_response["result"]["task"]["taskId"]
            task = self.poll_mcp(server, task_id)
            self.assertEqual(task["status"], "completed")
            result = server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 8,
                    "method": "tasks/result",
                    "params": {"taskId": task_id},
                }
            )
            assert result is not None
            self.assertIn(
                "io.modelcontextprotocol/related-task",
                result["result"]["_meta"],
            )

    def test_a2a_input_required_continuation_history_and_pagination(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.fixture(root)
            service = A2AService(
                root,
                base_url="http://127.0.0.1:8765",
            )
            card = service.agent_card()
            self.assertEqual(
                card["supportedInterfaces"][0]["protocolVersion"],
                "1.0",
            )
            self.assertEqual(len(card["skills"]), 9)
            first = service.handle_rpc(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "SendMessage",
                    "params": {
                        "message": {
                            "messageId": "m1",
                            "contextId": "context-1",
                            "role": "ROLE_USER",
                            "parts": [
                                {
                                    "data": {
                                        "operation": "automatic.create",
                                        "arguments": {
                                            "output_root": "_ggen"
                                        },
                                    }
                                }
                            ],
                        }
                    },
                }
            )
            task = first["result"]["task"]
            self.assertEqual(
                task["status"]["state"],
                "TASK_STATE_INPUT_REQUIRED",
            )
            second = service.handle_rpc(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "SendMessage",
                    "params": {
                        "message": {
                            "messageId": "m2",
                            "taskId": task["id"],
                            "contextId": "context-1",
                            "role": "ROLE_USER",
                            "parts": [
                                {
                                    "data": {
                                        "confirm": True,
                                        "arguments": {},
                                    }
                                }
                            ],
                        }
                    },
                }
            )
            completed = second["result"]["task"]
            self.assertEqual(
                completed["status"]["state"],
                "TASK_STATE_COMPLETED",
            )
            fetched = service.handle_rpc(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "GetTask",
                    "params": {"id": task["id"], "historyLength": 2},
                }
            )
            self.assertEqual(
                len(fetched["result"]["task"]["history"]),
                2,
            )
            listed = service.handle_rpc(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "ListTasks",
                    "params": {
                        "contextId": "context-1",
                        "status": "TASK_STATE_COMPLETED",
                        "pageSize": 1,
                    },
                }
            )
            self.assertEqual(listed["result"]["totalSize"], 1)
            drift = service.handle_rpc(
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "SendMessage",
                    "params": {
                        "message": {
                            "messageId": "m3",
                            "taskId": task["id"],
                            "role": "ROLE_USER",
                            "parts": [{"text": "continue"}],
                        }
                    },
                }
            )
            self.assertEqual(
                drift["error"]["message"],
                "A2A_TASK_CONTINUATION_REFUSED",
            )

    def test_doctor_reports_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            session = self.fixture(root)
            partial = doctor_report(root)
            self.assertEqual(partial["state"], "PARTIAL_ALIVE")
            run_automatic(
                session,
                output_root=root / "_ggen",
                apply=True,
                confirm=True,
            )
            complete = doctor_report(root)
            self.assertEqual(complete["checks"]["package"]["state"], "ALIVE")
            self.assertEqual(complete["checks"]["receipts"]["state"], "ALIVE")

    def test_selfplay_closes_native_rail(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            session = self.fixture(root)
            report = run_selfplay(
                session,
                output_root=root / ".ggen-create" / "selfplay-run",
            )
            self.assertEqual(report["state"], "ALIVE")
            self.assertEqual(report["failed_count"], 0)
            self.assertGreaterEqual(report["scenario_count"], 18)


if __name__ == "__main__":
    unittest.main()
