import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import core.database as database_module
import core.indexer as indexer_module
import core.retriever as retriever_module
from core.database import Database
from core.indexer import Indexer
from mcp.tools import ToolDefinitions


class FakeEmbeddingProvider:
    def available(self):
        return True

    def embed(self, text):
        return [0.0] * database_module.EMBEDDING_DIM


class AutoSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.repo_path = self.tmp_path / "repo"
        self.repo_path.mkdir()
        self.db_path = self.tmp_path / "index.db"
        self.original_db_path = database_module.DB_PATH
        database_module.DB_PATH = self.db_path
        ToolDefinitions._last_auto_sync = {}
        self.indexer_embedding_patch = patch.object(indexer_module, "EmbeddingProvider", FakeEmbeddingProvider)
        self.retriever_embedding_patch = patch.object(retriever_module, "EmbeddingProvider", FakeEmbeddingProvider)
        self.indexer_embedding_patch.start()
        self.retriever_embedding_patch.start()

    def tearDown(self):
        self.retriever_embedding_patch.stop()
        self.indexer_embedding_patch.stop()
        database_module.DB_PATH = self.original_db_path
        ToolDefinitions._last_auto_sync = {}
        self.tmp.cleanup()

    def write_file(self, name, content):
        path = self.repo_path / name
        path.write_text(content, encoding="utf-8")
        future = time.time() + 2
        os.utime(path, (future, future))
        return path

    def index_project(self):
        db = Database()
        try:
            docs, summaries = Indexer(db).index_project("TestRepo", str(self.repo_path))
            return docs, summaries
        finally:
            db.close()

    def index_named_project(self, project_name, project_path):
        db = Database()
        try:
            docs, summaries = Indexer(db).index_project(project_name, str(project_path))
            return docs, summaries
        finally:
            db.close()

    def call_get_document(self):
        return ToolDefinitions.handle_tool(
            "get_document",
            {"project_name": "TestRepo", "file_path": "app.py"},
        )

    def call_search(self):
        return ToolDefinitions.handle_tool(
            "search",
            {"project_name": "TestRepo", "query": "version", "top_k": 1},
        )

    def call_context_pack(self, **overrides):
        args = {
            "project_name": "TestRepo",
            "query": "version",
            "top_k": 3,
            "max_tokens": 500,
            "snippet_tokens": 120,
        }
        args.update(overrides)
        return ToolDefinitions.handle_tool("get_context_pack", args)

    def test_get_document_auto_syncs_changed_file(self):
        self.write_file("app.py", "print('version one')\n" * 3)
        self.index_project()
        self.write_file("app.py", "print('version two with longer content')\n" * 3)

        with patch.dict(os.environ, {"AUTO_SYNC_ON_QUERY": "true", "AUTO_SYNC_MIN_INTERVAL_SECONDS": "0"}):
            result = self.call_get_document()

        self.assertEqual(result["status"], "success")
        self.assertTrue(result["sync"]["ran"])
        self.assertIn("version two", result["content"])

    def test_search_auto_syncs_changed_file(self):
        self.write_file("app.py", "print('version one')\n" * 3)
        self.index_project()
        self.write_file("app.py", "print('version two with longer content')\n" * 3)

        with patch.dict(os.environ, {"AUTO_SYNC_ON_QUERY": "true", "AUTO_SYNC_MIN_INTERVAL_SECONDS": "0"}):
            result = self.call_search()

        self.assertEqual(result["status"], "success")
        self.assertTrue(result["sync"]["ran"])
        self.assertEqual(result["result_count"], 1)
        self.assertIn("version two", result["results"][0]["chunk_text"])

    def test_auto_sync_throttles_repeated_reads(self):
        self.write_file("app.py", "print('version one')\n" * 3)
        self.index_project()

        with patch.dict(os.environ, {"AUTO_SYNC_ON_QUERY": "true", "AUTO_SYNC_MIN_INTERVAL_SECONDS": "999"}):
            self.write_file("app.py", "print('version two with longer content')\n" * 3)
            first = self.call_get_document()
            self.write_file("app.py", "print('version three with even longer content')\n" * 3)
            second = self.call_get_document()

        self.assertTrue(first["sync"]["ran"])
        self.assertFalse(second["sync"]["ran"])
        self.assertEqual(second["sync"]["reason"], "throttled")
        self.assertIn("version two", second["content"])
        self.assertNotIn("version three", second["content"])

    def test_auto_sync_interval_is_read_from_environment_at_call_time(self):
        self.write_file("app.py", "print('version one')\n" * 3)
        self.index_project()

        with patch.dict(os.environ, {"AUTO_SYNC_ON_QUERY": "true", "AUTO_SYNC_MIN_INTERVAL_SECONDS": "999"}):
            self.write_file("app.py", "print('version two with longer content')\n" * 3)
            first = self.call_get_document()
            self.write_file("app.py", "print('version three with even longer content')\n" * 3)

        with patch.dict(os.environ, {"AUTO_SYNC_ON_QUERY": "true", "AUTO_SYNC_MIN_INTERVAL_SECONDS": "0"}):
            second = self.call_get_document()

        self.assertTrue(first["sync"]["ran"])
        self.assertTrue(second["sync"]["ran"])
        self.assertIn("version three", second["content"])

    def test_auto_sync_skips_projects_over_document_limit(self):
        self.write_file("app.py", "print('version one')\n" * 3)
        self.index_project()
        self.write_file("app.py", "print('version two with longer content')\n" * 3)

        with patch.dict(
            os.environ,
            {
                "AUTO_SYNC_ON_QUERY": "true",
                "AUTO_SYNC_MIN_INTERVAL_SECONDS": "0",
                "AUTO_SYNC_MAX_DOCUMENTS_ON_QUERY": "0",
            },
        ):
            result = self.call_get_document()

        self.assertEqual(result["status"], "success")
        self.assertFalse(result["sync"]["ran"])
        self.assertEqual(result["sync"]["reason"], "skipped_large_project")
        self.assertEqual(result["sync"]["documents"], 1)
        self.assertIn("version one", result["content"])
        self.assertNotIn("version two", result["content"])

    def test_context_pack_returns_bounded_snippets_with_line_metadata(self):
        self.write_file(
            "app.py",
            "def first():\n"
            "    return 'version one'\n\n"
            "def second():\n"
            "    return 'version two'\n",
        )
        self.index_project()

        with patch.dict(os.environ, {"AUTO_SYNC_ON_QUERY": "false"}):
            result = self.call_context_pack()

        self.assertEqual(result["status"], "success")
        self.assertLessEqual(result["estimated_tokens"], result["max_tokens"])
        self.assertGreaterEqual(result["included_count"], 1)
        self.assertEqual(result["snippets"][0]["file_path"], "app.py")
        self.assertEqual(result["snippets"][0]["line_start"], 1)
        self.assertIn("version", result["snippets"][0]["snippet"])
        self.assertNotIn("content", result["snippets"][0])

    def test_context_pack_omits_results_that_exceed_budget(self):
        self.write_file("one.py", "print('version one')\n" * 80)
        self.write_file("two.py", "print('version two')\n" * 80)
        self.write_file("three.py", "print('version three')\n" * 80)
        self.index_project()

        with patch.dict(os.environ, {"AUTO_SYNC_ON_QUERY": "false"}):
            result = self.call_context_pack(
                max_tokens=100,
                snippet_tokens=50,
                include_summaries=False,
            )

        self.assertEqual(result["status"], "success")
        self.assertLessEqual(result["estimated_tokens"], result["max_tokens"])
        self.assertGreaterEqual(result["result_count"], 2)
        self.assertGreater(result["omitted_for_budget"], 0)
        self.assertLess(result["included_count"], result["result_count"])

    def test_project_search_fallback_stays_project_scoped(self):
        other_repo = self.tmp_path / "other"
        other_repo.mkdir()
        self.write_file("app.py", "print('version one')\n" * 3)
        (other_repo / "other.py").write_text("print('different project')\n" * 3, encoding="utf-8")
        self.index_project()
        self.index_named_project("OtherRepo", other_repo)

        db = Database()
        try:
            project = db.get_project_by_name("TestRepo")
            results = db._search_project_embeddings_in_python(
                [0.0] * database_module.EMBEDDING_DIM,
                top_k=5,
                project_id=project["id"],
            )
        finally:
            db.close()

        self.assertTrue(results)
        self.assertTrue(all("version one" in result["text"] for result in results))


if __name__ == "__main__":
    unittest.main()
