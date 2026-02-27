"""Detect source files exceeding a line count threshold (SRP violation heuristic)."""

import os
import logging

from daemon.checks.base import CheckResult

logger = logging.getLogger(__name__)

name = "large_files"

DEFAULT_THRESHOLD = 300  # lines


def run(
    project_path: str,
    threshold: int = DEFAULT_THRESHOLD,
    source_dir: str = "Assets",
    file_extensions: list[str] | None = None,
) -> CheckResult:
    """Find source files longer than the threshold."""
    if file_extensions is None:
        file_extensions = [".cs"]

    scan_dir = os.path.join(project_path, source_dir)
    if not os.path.isdir(scan_dir):
        return CheckResult(check_name=name, ok=True, summary=f"No {source_dir}/ directory")

    large = []
    for root, dirs, files in os.walk(scan_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fname in files:
            if not any(fname.endswith(ext) for ext in file_extensions):
                continue
            full = os.path.join(root, fname)
            try:
                with open(full, "r", encoding="utf-8", errors="ignore") as f:
                    line_count = sum(1 for _ in f)
            except OSError:
                continue

            if line_count > threshold:
                rel = os.path.relpath(full, project_path).replace("\\", "/")
                large.append({
                    "file": rel,
                    "lines": line_count,
                    "over_by": line_count - threshold,
                })

    ext_label = "/".join(file_extensions)
    if large:
        large.sort(key=lambda x: x["lines"], reverse=True)
        return CheckResult(
            check_name=name,
            ok=True,  # Large files are advisory, not errors
            issues=large,
            summary=f"{len(large)} file(s) exceed {threshold} lines",
        )

    return CheckResult(
        check_name=name,
        ok=True,
        summary=f"All {ext_label} files under {threshold} lines",
    )
