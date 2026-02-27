"""Check Unity Editor.log for C# compilation errors.

Cross-platform Editor.log locations:
- Windows: %LOCALAPPDATA%/Unity/Editor/Editor.log
- macOS:   ~/Library/Logs/Unity/Editor.log
- Linux:   ~/.config/unity3d/Editor.log
"""

import os
import re
import sys
import logging

from daemon.checks.base import CheckResult

logger = logging.getLogger(__name__)

name = "unity_compile"

# Matches: Assets/Scripts/Foo.cs(42,10): error CS1002: ; expected
_ERROR_RE = re.compile(
    r"^(Assets/[^\(]+)\((\d+),(\d+)\):\s+error\s+(CS\d+):\s+(.+)$",
    re.MULTILINE,
)


def _find_editor_log() -> str | None:
    """Locate Unity Editor.log based on OS."""
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            path = os.path.join(local, "Unity", "Editor", "Editor.log")
            if os.path.isfile(path):
                return path
    elif sys.platform == "darwin":
        path = os.path.expanduser("~/Library/Logs/Unity/Editor.log")
        if os.path.isfile(path):
            return path
    else:
        path = os.path.expanduser("~/.config/unity3d/Editor.log")
        if os.path.isfile(path):
            return path
    return None


def run(project_path: str) -> CheckResult:
    """Parse Editor.log for compilation errors related to this project."""
    log_path = _find_editor_log()

    if not log_path:
        return CheckResult(
            check_name=name,
            ok=True,
            summary="Editor.log not found (Unity not running?)",
        )

    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            # Read last 200KB to avoid parsing huge logs
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 200_000))
            content = f.read()
    except OSError as e:
        return CheckResult(
            check_name=name,
            ok=True,
            summary=f"Cannot read Editor.log: {e}",
        )

    errors = []
    seen = set()
    for match in _ERROR_RE.finditer(content):
        file_path, line, col, code, message = match.groups()
        key = (file_path, code, line)
        if key in seen:
            continue
        seen.add(key)
        errors.append({
            "file": file_path,
            "line": int(line),
            "column": int(col),
            "code": code,
            "message": message.strip(),
        })

    if errors:
        return CheckResult(
            check_name=name,
            ok=False,
            issues=errors,
            summary=f"{len(errors)} compilation error(s) found",
        )

    return CheckResult(
        check_name=name,
        ok=True,
        summary="No compilation errors",
    )
