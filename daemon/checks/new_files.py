"""Check for recently modified source files since the last heartbeat.

Detects new or changed files that might need review.
"""

import json
import os
import time
import logging

from daemon.checks.base import CheckResult

logger = logging.getLogger(__name__)

name = "new_files"

# State file to track last check time
_STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "heartbeat_files.json")


def _load_state() -> dict:
    try:
        with open(_STATE_FILE, "r") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: dict):
    os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
    with open(_STATE_FILE, "w") as f:
        json.dump(state, f)


def run(
    project_path: str,
    source_dir: str = "Assets",
    file_extensions: list[str] | None = None,
) -> CheckResult:
    """Find source files modified since last check."""
    if file_extensions is None:
        file_extensions = [".cs"]

    scan_dir = os.path.join(project_path, source_dir)
    if not os.path.isdir(scan_dir):
        return CheckResult(check_name=name, ok=True, summary=f"No {source_dir}/ directory")

    state = _load_state()
    last_check = state.get("last_check", 0)
    now = time.time()

    modified = []
    for root, dirs, files in os.walk(scan_dir):
        # Skip hidden dirs
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fname in files:
            if not any(fname.endswith(ext) for ext in file_extensions):
                continue
            full = os.path.join(root, fname)
            try:
                mtime = os.path.getmtime(full)
            except OSError:
                continue
            if mtime > last_check:
                rel = os.path.relpath(full, project_path).replace("\\", "/")
                modified.append({
                    "file": rel,
                    "modified_at": mtime,
                })

    # Update state
    state["last_check"] = now
    _save_state(state)

    ext_label = "/".join(file_extensions)
    if modified:
        return CheckResult(
            check_name=name,
            ok=True,  # Modified files aren't errors, just informational
            issues=modified,
            summary=f"{len(modified)} {ext_label} file(s) modified since last check",
        )

    return CheckResult(
        check_name=name,
        ok=True,
        summary=f"No {ext_label} files modified",
    )
