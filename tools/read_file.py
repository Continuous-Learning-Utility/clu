"""read_file tool: reads a file's contents with line numbers."""

import os

from tools.base import BaseTool
from orchestrator.exceptions import SandboxViolation


class ReadFileTool(BaseTool):

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "Read the contents of a file with line numbers. "
            "Path is relative to the project root and must be within the allowed source directory."
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path from project root, e.g. 'Assets/Scripts/Player.cs'.",
                },
            },
            "required": ["path"],
        }

    def execute(self, args: dict, project_path: str, sandbox, backup) -> dict:
        path = args.get("path", "")
        full_path = os.path.join(project_path, path)

        try:
            sandbox.validate(full_path, project_path)
        except SandboxViolation as e:
            return {"error": str(e)}

        if not os.path.isfile(full_path):
            return {"error": f"File not found: {path}"}

        size = os.path.getsize(full_path)
        if size > 100_000:
            return {"error": f"File too large ({size} bytes). Max 100KB."}

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            return {"error": f"Cannot read binary file: {path}"}

        numbered = "\n".join(
            f"{i + 1:4d} | {line.rstrip()}" for i, line in enumerate(lines)
        )

        return {
            "path": path,
            "size": size,
            "lines": len(lines),
            "content": numbered,
        }
