"""Path sandboxing: ensures all file operations stay within allowed directories."""

import os

from orchestrator.exceptions import SandboxViolation


class PathValidator:
    """
    Enforces that all file operations stay within allowed paths.

    Security model:
    - Only the configured source directory is writable/readable by tools
    - No directory traversal (..)
    - No symlink following
    - Explicit blocklist for dangerous directories
    """

    DEFAULT_BLOCKED = [
        "library", "packages", "projectsettings", "usersettings",
        "temp", "obj", "logs", ".git", ".vs", ".vscode",
    ]

    def __init__(
        self,
        allowed_roots: list[str] | None = None,
        allowed_prefix: str = "assets",
        blocked_prefixes: list[str] | None = None,
    ):
        self.allowed_roots = [
            os.path.normpath(r).lower() for r in (allowed_roots or [])
        ]
        self.allowed_prefix = allowed_prefix.lower().strip("/").strip("\\") if allowed_prefix else ""
        self.blocked_prefixes = [
            p.lower().strip("/").strip("\\")
            for p in (blocked_prefixes if blocked_prefixes is not None else self.DEFAULT_BLOCKED)
        ]

    def validate(self, full_path: str, project_root: str) -> bool:
        """
        Validate that full_path is within allowed boundaries.

        Args:
            full_path: Absolute path to validate.
            project_root: Absolute path to the project root.

        Returns:
            True if path is valid.

        Raises:
            SandboxViolation: If path violates any rule.
        """
        normalized = os.path.normpath(os.path.abspath(full_path)).lower()
        project_normalized = os.path.normpath(os.path.abspath(project_root)).lower()

        # Must be under project root
        if not normalized.startswith(project_normalized + os.sep) and normalized != project_normalized:
            raise SandboxViolation(f"Path escapes project root: {full_path}")

        # Get relative path from project root
        relative = os.path.relpath(normalized, project_normalized)

        # Check for directory traversal
        if ".." in relative.split(os.sep):
            raise SandboxViolation(f"Directory traversal detected: {full_path}")

        # Normalize separators for prefix checks
        parts = relative.replace("\\", "/").split("/")

        # Must start with configured prefix (if set)
        if self.allowed_prefix and parts[0] != self.allowed_prefix:
            raise SandboxViolation(
                f"Path must be under {self.allowed_prefix}/: {full_path} (got '{parts[0]}')"
            )

        # Check blocklist
        rel_path = "/".join(parts)
        for prefix in self.blocked_prefixes:
            if rel_path == prefix or rel_path.startswith(prefix + "/"):
                raise SandboxViolation(f"Access to {prefix}/ is blocked")

        # Check for symlinks
        if os.path.exists(full_path) and os.path.islink(full_path):
            raise SandboxViolation(f"Symlinks are not allowed: {full_path}")

        return True

    def validate_relative(self, relative_path: str, project_root: str) -> str:
        """
        Validate a relative path and return the absolute path.

        Args:
            relative_path: Path relative to project root.
            project_root: Absolute path to the project root.

        Returns:
            The resolved absolute path.

        Raises:
            SandboxViolation: If path violates any rule.
        """
        full_path = os.path.join(project_root, relative_path)
        self.validate(full_path, project_root)
        return os.path.normpath(full_path)
