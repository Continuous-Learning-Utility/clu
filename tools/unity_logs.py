"""unity_logs tool: reads Unity Editor logs to see compile errors and console output."""

import os
import re

from tools.base import BaseTool


class UnityLogsTool(BaseTool):
    """
    Reads Unity Editor logs to give the agent feedback on:
    - Compile errors (CS####)
    - Script import errors
    - Runtime exceptions (NullReferenceException, etc.)
    - Debug.Log output

    Unity stores logs in multiple locations:
    1. Editor.log: %LOCALAPPDATA%/Unity/Editor/Editor.log (global)
    2. Project Logs/: <project>/Logs/ directory
    """

    # Common Unity error patterns
    _ERROR_PATTERNS = [
        re.compile(r"error CS\d+:.*", re.IGNORECASE),
        re.compile(r"Assets/.*\.cs\(\d+,\d+\):.*error.*", re.IGNORECASE),
        re.compile(r"NullReferenceException.*"),
        re.compile(r"MissingReferenceException.*"),
        re.compile(r"MissingComponentException.*"),
        re.compile(r"IndexOutOfRangeException.*"),
        re.compile(r"ArgumentException.*"),
        re.compile(r"InvalidOperationException.*"),
        re.compile(r"Compilation failed.*"),
        re.compile(r"Script has compile errors.*"),
    ]

    _WARNING_PATTERNS = [
        re.compile(r"warning CS\d+:.*", re.IGNORECASE),
        re.compile(r"Assets/.*\.cs\(\d+,\d+\):.*warning.*", re.IGNORECASE),
    ]

    @property
    def name(self) -> str:
        return "unity_logs"

    @property
    def description(self) -> str:
        return (
            "Read Unity Editor logs to see compile errors, runtime exceptions, and console output. "
            "Use this AFTER writing files to check if Unity reports errors. "
            "Modes: 'errors' (only errors/warnings), 'recent' (last 50 lines), 'full' (last 200 lines)."
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["errors", "recent", "full"],
                    "description": (
                        "'errors': only compilation errors and exceptions (recommended). "
                        "'recent': last 50 lines of the log. "
                        "'full': last 200 lines of the log."
                    ),
                },
                "source": {
                    "type": "string",
                    "enum": ["editor", "project"],
                    "description": (
                        "'editor': main Unity Editor.log (compile errors, imports). "
                        "'project': project Logs/ directory. "
                        "Default: 'editor'."
                    ),
                },
            },
        }

    def execute(self, args: dict, project_path: str, sandbox, backup) -> dict:
        mode = args.get("mode", "errors")
        source = args.get("source", "editor")

        log_path = self._find_log_path(source, project_path)
        if not log_path:
            return {"error": f"Unity log not found (source={source}). Is Unity Editor running?"}

        if not os.path.isfile(log_path):
            return {"error": f"Log file not found: {log_path}"}

        try:
            # Read the log file (can be large, read from end)
            content = self._read_tail(log_path, max_lines=500)
        except (PermissionError, UnicodeDecodeError) as e:
            return {"error": f"Cannot read log: {e}"}

        if mode == "errors":
            return self._extract_errors(content, log_path)
        elif mode == "recent":
            lines = content.split("\n")
            return {
                "source": log_path,
                "lines": len(lines),
                "content": "\n".join(lines[-50:]),
            }
        else:  # full
            lines = content.split("\n")
            return {
                "source": log_path,
                "lines": len(lines),
                "content": "\n".join(lines[-200:]),
            }

    def _find_log_path(self, source: str, project_path: str) -> str | None:
        """Find the appropriate Unity log file path."""
        if source == "editor":
            # Standard Unity Editor log location on Windows
            local_appdata = os.environ.get("LOCALAPPDATA", "")
            if local_appdata:
                path = os.path.join(local_appdata, "Unity", "Editor", "Editor.log")
                if os.path.isfile(path):
                    return path

            # Fallback: try common locations
            for base in [
                os.path.expandvars(r"%LOCALAPPDATA%\Unity\Editor"),
                os.path.expanduser("~/.config/unity3d"),
                os.path.expanduser("~/Library/Logs/Unity"),
            ]:
                path = os.path.join(base, "Editor.log")
                if os.path.isfile(path):
                    return path

        elif source == "project":
            # Project-level logs
            logs_dir = os.path.join(project_path, "Logs")
            if os.path.isdir(logs_dir):
                # Find the most recent log file
                log_files = sorted(
                    [f for f in os.listdir(logs_dir) if f.endswith(".log")],
                    key=lambda f: os.path.getmtime(os.path.join(logs_dir, f)),
                    reverse=True,
                )
                if log_files:
                    return os.path.join(logs_dir, log_files[0])

        return None

    def _extract_errors(self, content: str, log_path: str) -> dict:
        """Extract only errors and warnings from log content."""
        errors = []
        warnings = []

        for line in content.split("\n"):
            line_stripped = line.strip()
            if not line_stripped:
                continue

            for pattern in self._ERROR_PATTERNS:
                if pattern.search(line_stripped):
                    errors.append(line_stripped)
                    break

            for pattern in self._WARNING_PATTERNS:
                if pattern.search(line_stripped):
                    warnings.append(line_stripped)
                    break

        # Deduplicate while preserving order
        errors = list(dict.fromkeys(errors))[:30]
        warnings = list(dict.fromkeys(warnings))[:10]

        return {
            "source": log_path,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "errors": errors,
            "warnings": warnings,
            "clean": len(errors) == 0,
        }

    @staticmethod
    def _read_tail(filepath: str, max_lines: int = 500) -> str:
        """Read the last N lines of a file efficiently."""
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                # For large files, seek to approximate position near end
                f.seek(0, 2)
                file_size = f.tell()

                if file_size > 500_000:
                    # Seek to last ~500KB
                    f.seek(max(0, file_size - 500_000))
                    f.readline()  # Skip partial line
                else:
                    f.seek(0)

                lines = f.readlines()
                return "".join(lines[-max_lines:])
        except Exception:
            # Fallback: read all
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
                return "".join(lines[-max_lines:])
