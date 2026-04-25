"""MCP tool definitions."""
import os
import time
from typing import Any, Dict

from config import AUTO_SYNC_MIN_INTERVAL_SECONDS, AUTO_SYNC_ON_QUERY
from core.database import Database
from core.indexer import Indexer
from core.retriever import Retriever


class ToolDefinitions:
    """MCP tool definitions and handlers."""
    _last_auto_sync: Dict[str, float] = {}

    @staticmethod
    def get_tools() -> list:
        """Return list of available tools."""
        return [
            {
                "name": "index_project",
                "description": "Scan and index a project, generating summaries and embeddings for semantic search",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_name": {
                            "type": "string",
                            "description": "Project name to index"
                        },
                        "project_path": {
                            "type": "string",
                            "description": "Optional absolute path. If provided, registers/updates the project before indexing."
                        }
                    },
                    "required": ["project_name"]
                }
            },
            {
                "name": "add_project",
                "description": "Register or update a project path so it can be indexed/searched",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_name": {
                            "type": "string",
                            "description": "Friendly project name"
                        },
                        "project_path": {
                            "type": "string",
                            "description": "Absolute path to the project root"
                        }
                    },
                    "required": ["project_name", "project_path"]
                }
            },
            {
                "name": "search",
                "description": "Search across indexed projects using semantic similarity",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query"
                        },
                        "project_name": {
                            "type": "string",
                            "description": "Optional: project to search in (if omitted, searches all)"
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Number of results to return (default: 5)",
                            "default": 5
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "list_projects",
                "description": "List all indexed projects with their status",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "get_project_context",
                "description": "Get concatenated summaries of all documents in a project for full context",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_name": {
                            "type": "string",
                            "description": "Name of the project"
                        }
                    },
                    "required": ["project_name"]
                }
            },
            {
                "name": "get_document",
                "description": "Retrieve the original content of a specific document",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_name": {
                            "type": "string",
                            "description": "Name of the project"
                        },
                        "file_path": {
                            "type": "string",
                            "description": "Path to file within the project"
                        }
                    },
                    "required": ["project_name", "file_path"]
                }
            }
        ]

    @staticmethod
    def handle_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tool calls."""
        db = Database()
        try:
            if tool_name == "index_project":
                return ToolDefinitions._handle_index_project(db, arguments)
            elif tool_name == "add_project":
                return ToolDefinitions._handle_add_project(db, arguments)
            elif tool_name == "search":
                return ToolDefinitions._handle_search(db, arguments)
            elif tool_name == "list_projects":
                return ToolDefinitions._handle_list_projects(db)
            elif tool_name == "get_project_context":
                return ToolDefinitions._handle_get_project_context(db, arguments)
            elif tool_name == "get_document":
                return ToolDefinitions._handle_get_document(db, arguments)
            else:
                return {"status": "error", "message": f"Unknown tool: {tool_name}"}
        finally:
            db.close()

    @staticmethod
    def _handle_index_project(db: Database, args: Dict[str, Any]) -> Dict[str, Any]:
        """Handle index_project tool."""
        try:
            project_name = args.get("project_name")
            project_path = args.get("project_path")
            indexer = Indexer(db)
            docs, summaries = indexer.index_project(project_name, project_path)
            return {
                "status": "success",
                "documents_indexed": docs,
                "summaries_generated": summaries,
                "message": f"Indexed {docs} documents and generated {summaries} summaries"
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @staticmethod
    def _handle_add_project(db: Database, args: Dict[str, Any]) -> Dict[str, Any]:
        """Handle add_project tool."""
        try:
            project_name = (args.get("project_name") or "").strip()
            project_path = (args.get("project_path") or "").strip()
            if not project_name:
                return {"status": "error", "message": "project_name is required"}
            if not project_path:
                return {"status": "error", "message": "project_path is required"}

            abs_path = os.path.abspath(os.path.expanduser(project_path))
            if not os.path.isdir(abs_path):
                return {"status": "error", "message": f"Project path not found: {abs_path}"}

            project_id = db.add_project(project_name, abs_path)
            return {
                "status": "success",
                "project_id": project_id,
                "project_name": project_name,
                "project_path": abs_path,
                "message": f"Registered project '{project_name}'"
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @staticmethod
    def _handle_search(db: Database, args: Dict[str, Any]) -> Dict[str, Any]:
        """Handle search tool."""
        try:
            query = args.get("query")
            project_name = args.get("project_name")
            top_k = args.get("top_k", 5)

            ToolDefinitions._maybe_auto_sync(db, project_name)
            
            retriever = Retriever(db)
            results = retriever.search(query, project_name, top_k)
            
            return {
                "status": "success",
                "query": query,
                "result_count": len(results),
                "results": [
                    {
                        "file_path": r["file_path"],
                        "chunk_text": r["chunk_text"][:300],  # Truncate for readability
                        "summary": r["summary"],
                        "relevance": round(r["relevance"], 3)
                    }
                    for r in results
                ]
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @staticmethod
    def _handle_list_projects(db: Database) -> Dict[str, Any]:
        """Handle list_projects tool."""
        try:
            retriever = Retriever(db)
            projects = retriever.list_projects()
            return {
                "status": "success",
                "projects": projects
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @staticmethod
    def _handle_get_project_context(db: Database, args: Dict[str, Any]) -> Dict[str, Any]:
        """Handle get_project_context tool."""
        try:
            project_name = args.get("project_name")
            ToolDefinitions._maybe_auto_sync(db, project_name)
            retriever = Retriever(db)
            context = retriever.get_full_context(project_name)
            
            if context.startswith("Error"):
                return {"status": "error", "message": context}
            
            return {
                "status": "success",
                "project_name": project_name,
                "context": context
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @staticmethod
    def _handle_get_document(db: Database, args: Dict[str, Any]) -> Dict[str, Any]:
        """Handle get_document tool."""
        try:
            project_name = args.get("project_name")
            file_path = args.get("file_path")

            ToolDefinitions._maybe_auto_sync(db, project_name)
            
            retriever = Retriever(db)
            content = retriever.get_document_content(file_path, project_name)
            
            if content is None:
                return {
                    "status": "error",
                    "message": f"Document not found: {file_path} in {project_name}"
                }
            
            return {
                "status": "success",
                "file_path": file_path,
                "content": content
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @staticmethod
    def _maybe_auto_sync(db: Database, project_name: str):
        """Incrementally sync project before read operations (throttled)."""
        if not AUTO_SYNC_ON_QUERY or not project_name:
            return

        project = db.get_project_by_name(project_name)
        if not project:
            return

        now = time.time()
        last_sync = ToolDefinitions._last_auto_sync.get(project_name, 0)
        if now - last_sync < AUTO_SYNC_MIN_INTERVAL_SECONDS:
            return

        indexer = Indexer(db)
        indexer.index_project(project_name)
        ToolDefinitions._last_auto_sync[project_name] = now
