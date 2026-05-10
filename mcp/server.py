"""MCP Server implementation for Project RAG."""
import asyncio
import json
from pathlib import Path
import sys
from typing import Any, Dict

# Codex launches this file directly from config.toml. In that mode Python puts
# the mcp/ directory on sys.path, not the repo root, so package imports fail
# unless we add the parent explicitly.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from mcp.tools import ToolDefinitions


class ProjectRAGServer:
    """MCP Server for Project RAG."""

    def __init__(self):
        self.name = "project-rag"
        self.version = "1.0.0"

    async def process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming MCP request."""
        try:
            if "jsonrpc" in request:
                return await self._process_jsonrpc_request(request)

            request_type = request.get("type")

            if request_type == "initialize":
                return self._handle_initialize()
            elif request_type == "call_tool":
                return await self._handle_call_tool(request)
            elif request_type == "list_tools":
                return self._handle_list_tools()
            else:
                return {"error": f"Unknown request type: {request_type}"}
        except Exception as e:
            return {"error": str(e), "type": "error"}

    async def _process_jsonrpc_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Process a standard MCP JSON-RPC request."""
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}

        try:
            if method == "initialize":
                result = {
                    "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                    "capabilities": {"tools": {"listChanged": True}},
                    "serverInfo": {"name": self.name, "version": self.version},
                }
            elif method == "tools/list":
                result = {"tools": ToolDefinitions.get_tools()}
            elif method == "tools/call":
                result = await self._handle_jsonrpc_tool_call(params)
            elif method == "notifications/initialized":
                return {}
            else:
                return self._jsonrpc_error(request_id, -32601, f"Method not found: {method}")

            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as e:
            return self._jsonrpc_error(request_id, -32603, str(e))

    async def _handle_jsonrpc_tool_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a standard MCP tools/call request."""
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            ToolDefinitions.handle_tool,
            tool_name,
            arguments,
        )
        is_error = isinstance(result, dict) and result.get("status") == "error"
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2),
                }
            ],
            "isError": is_error,
        }

    @staticmethod
    def _jsonrpc_error(request_id: Any, code: int, message: str) -> Dict[str, Any]:
        """Build a JSON-RPC error response."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }

    def _handle_initialize(self) -> Dict[str, Any]:
        """Handle initialize request."""
        return {
            "type": "initialize_response",
            "serverInfo": {
                "name": self.name,
                "version": self.version,
                "capabilities": {
                    "tools": {
                        "listChanged": True
                    }
                }
            }
        }

    def _handle_list_tools(self) -> Dict[str, Any]:
        """Handle list_tools request."""
        return {
            "type": "tools",
            "tools": ToolDefinitions.get_tools()
        }

    async def _handle_call_tool(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tool call request."""
        tool_name = request.get("name")
        arguments = request.get("arguments", {})

        # Execute tool (sync for now, but wrapped in async)
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            ToolDefinitions.handle_tool,
            tool_name,
            arguments
        )

        return {
            "type": "tool_result",
            "name": tool_name,
            "result": result
        }


async def run_server():
    """Run MCP server in stdio mode."""
    server = ProjectRAGServer()

    # Read requests line by line
    loop = asyncio.get_event_loop()

    while True:
        try:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                break

            request = json.loads(line.strip())
            response = await server.process_request(request)
            if response:
                print(json.dumps(response))
                sys.stdout.flush()
        except json.JSONDecodeError:
            print(json.dumps({"error": "Invalid JSON"}))
            sys.stdout.flush()
        except Exception as e:
            print(json.dumps({"error": str(e)}))
            sys.stdout.flush()


if __name__ == "__main__":
    asyncio.run(run_server())
