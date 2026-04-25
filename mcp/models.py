"""Data models for MCP requests/responses."""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel


class IndexProjectRequest(BaseModel):
    project_name: str
    project_path: Optional[str] = None


class IndexProjectResponse(BaseModel):
    status: str
    documents_indexed: int
    summaries_generated: int
    message: str


class AddProjectRequest(BaseModel):
    project_name: str
    project_path: str


class AddProjectResponse(BaseModel):
    status: str
    project_id: int
    project_name: str
    project_path: str
    message: str


class SearchRequest(BaseModel):
    query: str
    project_name: Optional[str] = None
    top_k: int = 5


class SearchResult(BaseModel):
    file_path: str
    chunk_text: str
    summary: Optional[str]
    relevance: float


class SearchResponse(BaseModel):
    status: str
    query: str
    results: List[SearchResult]


class ProjectSummary(BaseModel):
    name: str
    documents: int
    summarized: int
    last_indexed: Optional[str] = None


class ListProjectsResponse(BaseModel):
    projects: List[ProjectSummary]


class GetProjectContextRequest(BaseModel):
    project_name: str


class GetProjectContextResponse(BaseModel):
    status: str
    project_name: str
    context: str


class GetDocumentRequest(BaseModel):
    project_name: str
    file_path: str


class GetDocumentResponse(BaseModel):
    status: str
    file_path: str
    content: Optional[str]
