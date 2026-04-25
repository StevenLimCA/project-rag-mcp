#!/usr/bin/env python3
"""Demo script for Project RAG MCP."""
import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.database import Database
from core.indexer import Indexer
from core.retriever import Retriever


def demo():
    """Run demo workflow."""
    print("=" * 60)
    print("Project RAG MCP - Demo")
    print("=" * 60)

    db = Database()

    try:
        # 1. Index projects
        print("\n1. Indexing projects...")
        indexer = Indexer(db)

        for project in ["Codex", "DogeMonsters", "ScoreAI"]:
            try:
                print(f"   Indexing {project}...", end=" ")
                docs, summaries = indexer.index_project(project)
                print(f"✓ ({docs} docs, {summaries} summaries)")
            except Exception as e:
                print(f"✗ {e}")

        # 2. List projects
        print("\n2. Indexed projects:")
        retriever = Retriever(db)
        projects = retriever.list_projects()
        for p in projects:
            if "error" not in p:
                print(f"   - {p['name']}: {p['documents']} documents, {p['summarized']} summarized")

        # 3. Search
        print("\n3. Searching...")
        queries = [
            "practice scoring",
            "game mechanics",
            "AI integration"
        ]
        for query in queries:
            print(f"   Query: '{query}'")
            results = retriever.search(query, top_k=3)
            for i, r in enumerate(results, 1):
                print(f"     {i}. {r['file_path']} (relevance: {r['relevance']:.2f})")

        # 4. Get project context
        print("\n4. Getting full project context for ScoreAI...")
        context = retriever.get_full_context("ScoreAI")
        lines = context.split('\n')
        print(f"   Generated context: {len(lines)} lines, {len(context)} chars")
        if lines:
            print(f"   First 200 chars: {context[:200]}...")

        print("\n" + "=" * 60)
        print("Demo complete! The RAG system is ready to use.")
        print("=" * 60)

    except Exception as e:
        print(f"\nError during demo: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("Warning: OPENAI_API_KEY not set. Summaries will use fallback method.")
        print("Set it with: export OPENAI_API_KEY='sk-...'")
        print()

    demo()
