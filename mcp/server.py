"""MCP Server implementation for Project RAG."""
import asyncio
import json
import sys
from typing import Any, Dict

from mcp.tools import ToolDefinitions


class ProjectRAGServer:
    """MCP Server for Project RAG."""

    def __init__(self):
        self.name = "project-rag"
        self.version = "1.0.0"

    async def process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming MCP request."""
        try:
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
