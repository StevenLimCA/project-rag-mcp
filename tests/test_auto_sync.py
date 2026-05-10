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


if __name__ == "__main__":
    unittest.main()
