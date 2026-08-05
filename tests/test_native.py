from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ggen_create.a2a import A2AService
from ggen_create.agents import AgentRuntime
from ggen_create.automatic import automatic_plan, run_automatic
from ggen_create.autonomic import AutonomicPolicy, run_autonomic
from ggen_create.mcp import McpServer
from ggen_create.model import GgenCreateError
from ggen_create.runtime import ReceiptStore
from ggen_create.selfplay import run_selfplay
from ggen_create.session import add_paths, set_seed, start_session
from ggen_create.skills import Broker, SkillRegistry


class NativeTests(unittest.TestCase):
    def fixture(self, root: Path) -> Path:
        (root / "Hello.txt").write_text("Hello hello", encoding="utf-8")
        session = start_session(root, "greeter")
        add_paths(session, ["Hello.txt"], cwd=root)
        set_seed(session, "Hello")
        return session

    def test_automatic_plan_apply_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); session = self.fixture(root)
            plan = automatic_plan(session, output_root=root / "_ggen")
            self.assertEqual(plan["state"], "CANDIDATE")
            with self.assertRaisesRegex(GgenCreateError, "ACTUATION_CONFIRMATION_REQUIRED_REFUSED"):
                run_automatic(session, output_root=root / "_ggen", apply=True, confirm=False)
            report = run_automatic(session, output_root=root / "_ggen", apply=True, confirm=True)
            self.assertEqual(report["state"], "ALIVE")
            self.assertTrue(ReceiptStore.verify(Path(report["receipt"]["path"]))["valid"])

    def test_autonomic_converges(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); session = self.fixture(root)
            report = run_autonomic(session, output_root=root / "_ggen", policy=AutonomicPolicy(max_cycles=3, stable_cycles=1, apply=True, confirm=True))
            self.assertTrue(report["converged"])
            self.assertEqual(report["state"], "ALIVE")

    def test_agent_authority_and_broker(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); session = self.fixture(root); agents = AgentRuntime(root)
            self.assertEqual(agents.route("manufacture package")["agent"], "manufacturing-architect")
            with self.assertRaisesRegex(GgenCreateError, "AGENT_SKILL_AUTHORITY_REFUSED"):
                agents.plan("receiver", "package.build", {})
            intent = SkillRegistry().plan("package.build", {"output_root": str(root / "_ggen")})
            with self.assertRaisesRegex(GgenCreateError, "ACTUATION_CONFIRMATION_REQUIRED_REFUSED"):
                Broker(root).execute(intent, session_path=session)
            self.assertEqual(Broker(root).execute(intent, session_path=session, confirm=True)["state"], "ALIVE")

    def test_mcp_lifecycle_resources_tools_and_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); self.fixture(root); server = McpServer(root)
            initialized = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}})
            self.assertEqual(initialized["result"]["protocolVersion"], "2025-11-25")
            server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
            tools = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            self.assertGreaterEqual(len(tools["result"]["tools"]), 9)
            resources = server.handle({"jsonrpc": "2.0", "id": 3, "method": "resources/list", "params": {}})
            self.assertEqual(len(resources["result"]["resources"]), 4)
            denied = server.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "ggen_create_apply", "arguments": {"confirm": False}}})
            self.assertTrue(denied["result"]["isError"])
            task = server.handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "ggen_create_apply", "arguments": {"confirm": True, "output_root": "_ggen"}, "task": {"ttl": 60000}}})
            task_id = task["result"]["task"]["taskId"]
            self.assertEqual(task["result"]["task"]["status"], "completed")
            result = server.handle({"jsonrpc": "2.0", "id": 6, "method": "tasks/result", "params": {"taskId": task_id}})
            self.assertFalse(result["result"]["isError"])

    def test_a2a_agent_card_and_task(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); self.fixture(root); service = A2AService(root, base_url="http://127.0.0.1:8765")
            card = service.agent_card()
            self.assertEqual(card["supportedInterfaces"][0]["protocolVersion"], "1.0")
            self.assertEqual(len(card["skills"]), 9)
            response = service.handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "SendMessage", "params": {"message": {"messageId": "m1", "role": "ROLE_USER", "parts": [{"data": {"operation": "automatic.plan", "arguments": {"output_root": "_ggen"}}}]}}})
            task = response["result"]["task"]
            self.assertEqual(task["status"]["state"], "TASK_STATE_COMPLETED")
            fetched = service.handle_rpc({"jsonrpc": "2.0", "id": 2, "method": "GetTask", "params": {"id": task["id"]}})
            self.assertEqual(fetched["result"]["task"]["id"], task["id"])

    def test_selfplay_closes_native_rail(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); session = self.fixture(root)
            report = run_selfplay(session, output_root=root / ".ggen-create/selfplay-run")
            self.assertEqual(report["state"], "ALIVE")
            self.assertEqual(report["failed_count"], 0)
            self.assertGreaterEqual(report["scenario_count"], 8)


if __name__ == "__main__":
    unittest.main()
