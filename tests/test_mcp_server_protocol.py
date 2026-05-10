import asyncio
import json
import subprocess
import sys
import unittest
from pathlib import Path

from mcp.server import ProjectRAGServer


ROOT_DIR = Path(__file__).resolve().parents[1]
PYTHON = ROOT_DIR / ".venv" / "bin" / "python"


class MCPServerProtocolTests(unittest.TestCase):
    def test_configured_script_entrypoint_starts_and_lists_tools(self):
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        completed = subprocess.run(
            [str(PYTHON), str(ROOT_DIR / "mcp" / "server.py")],
            cwd="/tmp",
            input=json.dumps(request) + "\n",
            text=True,
            capture_output=True,
            check=True,
            timeout=5,
        )

        response = json.loads(completed.stdout)
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["id"], 1)
        tool_names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertIn("search", tool_names)
        self.assertIn("get_document", tool_names)

    def test_initialize_uses_mcp_jsonrpc_shape(self):
        server = ProjectRAGServer()
        response = asyncio.run(
            server.process_request(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05"},
                }
            )
        )

        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["result"]["serverInfo"]["name"], "project-rag")
        self.assertIn("tools", response["result"]["capabilities"])

    def test_tools_call_wraps_tool_result_as_mcp_content(self):
        server = ProjectRAGServer()
        response = asyncio.run(
            server.process_request(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "list_projects", "arguments": {}},
                }
            )
        )

        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertFalse(response["result"]["isError"])
        self.assertEqual(response["result"]["content"][0]["type"], "text")

    def test_legacy_list_tools_shape_still_works(self):
        server = ProjectRAGServer()
        response = asyncio.run(server.process_request({"type": "list_tools"}))

        self.assertEqual(response["type"], "tools")
        self.assertTrue(response["tools"])


if __name__ == "__main__":
    unittest.main()
