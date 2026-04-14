"""OMNIX Git History Parser — builds a timeline of codebase evolution."""

from __future__ import annotations

import os
import subprocess
from collections import defaultdict


def parse_git_history(root_path, store):
    """
    Parse git log to build a timeline of file changes.
    Returns timeline data structure for the web visualization.
    Does NOT modify the graph store — returns a separate JSON-serializable dict.
    """
    _ = store  # Reserved for future correlation with the graph store.

    if not os.path.isdir(os.path.join(root_path, ".git")):
        print("⚠️ No .git directory found — skipping timeline")
        return None

    try:
        # Get all commits with file changes (numstat for additions/deletions)
        result = subprocess.run(
            [
                "git",
                "log",
                "--all",
                "--numstat",
                "--format=COMMIT:%H|%an|%aI|%s",
                "--no-merges",
            ],
            cwd=root_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            print(f"⚠️ git log failed: {result.stderr[:200]}")
            return None
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"⚠️ git error: {e}")
        return None

    # Parse the git log output
    commits = []
    current_commit = None

    for line in result.stdout.split("\n"):
        line = line.strip()
        if not line:
            continue

        if line.startswith("COMMIT:"):
            if current_commit:
                commits.append(current_commit)
            parts = line[7:].split("|", 3)
            if len(parts) >= 4:
                current_commit = {
                    "hash": parts[0][:8],
                    "author": parts[1],
                    "date": parts[2],
                    "message": parts[3][:80],
                    "files": [],
                }
            else:
                current_commit = None
        elif current_commit and "\t" in line:
            parts = line.split("\t")
            if len(parts) >= 3:
                added = int(parts[0]) if parts[0].isdigit() else 0
                deleted = int(parts[1]) if parts[1].isdigit() else 0
                filepath = parts[2]
                # Only track Python and TypeScript files
                if filepath.endswith((".py", ".ts", ".tsx", ".js", ".jsx")):
                    current_commit["files"].append(
                        {
                            "path": filepath,
                            "added": added,
                            "deleted": deleted,
                        }
                    )

    if current_commit:
        commits.append(current_commit)

    # Reverse so oldest is first
    commits.reverse()

    if not commits:
        print("⚠️ No commits found")
        return None

    # Build timeline snapshots (sample at most 100 points)
    total = len(commits)
    step = max(1, total // 100)

    snapshots = []
    file_state = {}  # filepath → {lines, first_seen, last_modified, author, changes}

    for i, commit in enumerate(commits):
        for f in commit["files"]:
            path = f["path"]
            if path not in file_state:
                file_state[path] = {
                    "lines": 0,
                    "first_seen": commit["date"],
                    "last_modified": commit["date"],
                    "author": commit["author"],
                    "changes": 0,
                }
            file_state[path]["lines"] += f["added"] - f["deleted"]
            file_state[path]["lines"] = max(0, file_state[path]["lines"])
            file_state[path]["last_modified"] = commit["date"]
            file_state[path]["changes"] += 1

        # Sample this commit for the timeline
        if i % step == 0 or i == total - 1:
            # Group files by directory
            dir_sizes = defaultdict(lambda: {"files": 0, "lines": 0, "authors": set()})
            for path, state in file_state.items():
                if state["lines"] <= 0:
                    continue
                dir_path = "/".join(path.split("/")[:-1]) or "."
                dir_sizes[dir_path]["files"] += 1
                dir_sizes[dir_path]["lines"] += state["lines"]
                dir_sizes[dir_path]["authors"].add(state["author"])

            snapshot = {
                "index": len(snapshots),
                "hash": commit["hash"],
                "date": commit["date"][:10],  # YYYY-MM-DD
                "message": commit["message"],
                "author": commit["author"],
                "total_files": len([f for f in file_state.values() if f["lines"] > 0]),
                "total_lines": sum(f["lines"] for f in file_state.values() if f["lines"] > 0),
                "directories": {
                    d: {
                        "files": v["files"],
                        "lines": v["lines"],
                        "authors": list(v["authors"]),
                    }
                    for d, v in dir_sizes.items()
                },
            }
            snapshots.append(snapshot)

    print(f"⏳ {len(snapshots)} timeline snapshots from {len(commits)} commits")
    print(f"   Date range: {commits[0]['date'][:10]} → {commits[-1]['date'][:10]}")

    return {
        "snapshots": snapshots,
        "total_commits": len(commits),
        "first_date": commits[0]["date"][:10],
        "last_date": commits[-1]["date"][:10],
    }
