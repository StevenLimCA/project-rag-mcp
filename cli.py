"""Simple sync CLI for testing."""
import sys
import os
import time
from pathlib import Path
from typing import Dict, List, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.database import Database
from core.indexer import Indexer
from core.retriever import Retriever


def _pick_directory() -> str:
    """Open a native folder picker and return selected path."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return ""

    root = tk.Tk()
    root.withdraw()
    root.update()
    selected = filedialog.askdirectory(title="Select project folder to index")
    root.destroy()
    return selected or ""


def _discover_projects(base_path: str, max_depth: int = 3) -> List[Tuple[str, str]]:
    """Discover likely project roots under base_path."""
    marker_files = {
        ".git", "package.json", "pyproject.toml", "requirements.txt", "Cargo.toml",
        "go.mod", "pom.xml", "build.gradle", "build.gradle.kts", "composer.json",
        "Gemfile",
    }
    excluded = {
        ".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache",
        ".pytest_cache", ".next", "dist", "build", "target", ".idea", ".vscode",
    }
    source_exts = {".py", ".ts", ".tsx", ".js", ".jsx", ".swift", ".go", ".rs", ".java", ".kt", ".rb", ".php", ".md"}

    root = Path(base_path).expanduser().resolve()
    if not root.is_dir():
        return []

    discovered: Set[Path] = set()
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        rel_depth = len(current.relative_to(root).parts)
        if rel_depth > max_depth:
            dirnames[:] = []
            continue

        raw_dirnames = list(dirnames)
        dirnames[:] = [d for d in dirnames if d not in excluded]
        names = set(filenames).union(set(raw_dirnames))

        has_marker_file = any(name in marker_files for name in names)
        has_git_dir = ".git" in raw_dirnames
        has_xcodeproj = any(name.endswith(".xcodeproj") for name in raw_dirnames)
        source_count = sum(1 for name in filenames if Path(name).suffix.lower() in source_exts)
        has_source = source_count >= 2
        if rel_depth > 0 and (has_marker_file or has_git_dir or has_xcodeproj or has_source):
            discovered.add(current)

    # Keep top-level project roots, not every nested subfolder.
    selected: List[Path] = []
    for candidate in sorted(discovered, key=lambda p: len(p.parts)):
        if any(parent == candidate or parent in candidate.parents for parent in selected):
            continue
        selected.append(candidate)

    return [(p.name or "project", str(p)) for p in selected]


def _dedupe_name(db: Database, base_name: str) -> str:
    """Generate a unique project name if one already exists."""
    candidate = base_name
    idx = 2
    while db.get_project_by_name(candidate):
        candidate = f"{base_name}_{idx}"
        idx += 1
    return candidate


def main():
    """CLI interface."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python cli.py add <project_name> <project_path>")
        print("  python cli.py pick <project_name>")
        print("  python cli.py discover [base_path] [max_depth]")
        print("  python cli.py index <project_name> [project_path]")
        print("  python cli.py watch <project_name> [interval_seconds]")
        print("  python cli.py search <query> [project_name] [top_k]")
        print("  python cli.py list")
        print("  python cli.py context <project_name>")
        print("  python cli.py get <project_name> <file_path>")
        return

    command = sys.argv[1]
    db = Database()

    try:
        if command == "add":
            if len(sys.argv) < 4:
                print("Usage: python cli.py add <project_name> <project_path>")
                return
            project_name = sys.argv[2]
            project_path = os.path.abspath(os.path.expanduser(sys.argv[3]))
            if not os.path.isdir(project_path):
                print(f"Project path not found: {project_path}")
                return
            project_id = db.add_project(project_name, project_path)
            print(f"Registered {project_name} at {project_path} (id={project_id})")

        elif command == "pick":
            if len(sys.argv) < 3:
                print("Usage: python cli.py pick <project_name>")
                return
            project_name = sys.argv[2]
            project_path = _pick_directory()
            if not project_path:
                print("No folder selected.")
                return
            project_id = db.add_project(project_name, project_path)
            print(f"Registered {project_name} at {project_path} (id={project_id})")

        elif command == "discover":
            base_path = sys.argv[2] if len(sys.argv) > 2 else str(Path.home() / "Documents")
            max_depth = int(sys.argv[3]) if len(sys.argv) > 3 else 3
            base_path = os.path.abspath(os.path.expanduser(base_path))
            projects = _discover_projects(base_path, max_depth=max_depth)
            if not projects:
                print(f"No project candidates found under {base_path}")
                return

            print(f"Discovered {len(projects)} project candidates under {base_path}:")
            for i, (name, path) in enumerate(projects, 1):
                print(f"  {i:>2}. {name} -> {path}")

            choice = input("\nSelect number to register, 'a' for all, or Enter to cancel: ").strip().lower()
            if not choice:
                print("Cancelled.")
                return

            if choice == "a":
                for name, path in projects:
                    unique_name = _dedupe_name(db, name)
                    project_id = db.add_project(unique_name, path)
                    print(f"Registered {unique_name} at {path} (id={project_id})")
                return

            try:
                idx = int(choice)
            except ValueError:
                print("Invalid selection.")
                return
            if idx < 1 or idx > len(projects):
                print("Selection out of range.")
                return

            name, path = projects[idx - 1]
            unique_name = _dedupe_name(db, name)
            project_id = db.add_project(unique_name, path)
            print(f"Registered {unique_name} at {path} (id={project_id})")

        elif command == "index":
            if len(sys.argv) < 3:
                print("Usage: python cli.py index <project_name> [project_path]")
                return
            project_name = sys.argv[2]
            project_path = sys.argv[3] if len(sys.argv) > 3 else None
            indexer = Indexer(db)
            docs, summaries = indexer.index_project(project_name, project_path)
            print(f"Indexed {docs} documents, generated {summaries} summaries")

        elif command == "watch":
            if len(sys.argv) < 3:
                print("Usage: python cli.py watch <project_name> [interval_seconds]")
                return
            project_name = sys.argv[2]
            interval = float(sys.argv[3]) if len(sys.argv) > 3 else 5.0
            if interval < 1:
                interval = 1.0
            indexer = Indexer(db)
            print(f"Watching {project_name} (interval={interval:.1f}s). Press Ctrl+C to stop.")
            try:
                while True:
                    docs, summaries = indexer.index_project(project_name)
                    if docs or summaries:
                        print(f"Synced: {docs} docs updated, {summaries} summaries at {time.strftime('%H:%M:%S')}")
                    time.sleep(interval)
            except KeyboardInterrupt:
                print("\nStopped watch mode.")

        elif command == "search":
            if len(sys.argv) < 3:
                print("Usage: python cli.py search <query> [project_name] [top_k]")
                return
            query = sys.argv[2]
            project_name = sys.argv[3] if len(sys.argv) > 3 else None
            top_k = int(sys.argv[4]) if len(sys.argv) > 4 else 5

            retriever = Retriever(db)
            results = retriever.search(query, project_name, top_k)

            print(f"\nSearch: '{query}' ({len(results)} results)\n")
            for i, r in enumerate(results, 1):
                print(f"{i}. File: {r['file_path']}")
                print(f"   Relevance: {r['relevance']:.2f}")
                print(f"   Summary: {r['summary'][:100]}...")
                print()

        elif command == "list":
            retriever = Retriever(db)
            projects = retriever.list_projects()
            print("Indexed projects:\n")
            for p in projects:
                if "error" not in p:
                    print(f"  {p['name']}: {p['documents']} documents, {p['summarized']} summarized")
                    if p.get('last_indexed'):
                        print(f"    Last indexed: {p['last_indexed']}")

        elif command == "context":
            if len(sys.argv) < 3:
                print("Usage: python cli.py context <project_name>")
                return
            project_name = sys.argv[2]
            retriever = Retriever(db)
            context = retriever.get_full_context(project_name)
            print(context)

        elif command == "get":
            if len(sys.argv) < 4:
                print("Usage: python cli.py get <project_name> <file_path>")
                return
            project_name = sys.argv[2]
            file_path = sys.argv[3]
            retriever = Retriever(db)
            content = retriever.get_document_content(file_path, project_name)
            if content:
                print(content)
            else:
                print(f"Document not found: {file_path}")

        else:
            print(f"Unknown command: {command}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
