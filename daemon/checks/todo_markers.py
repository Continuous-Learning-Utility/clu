"""Scan source files for TODO, FIXME, HACK, and XXX markers."""

import os
import re
import logging

from daemon.checks.base import CheckResult

logger = logging.getLogger(__name__)

name = "todo_markers"

_MARKER_RE = re.compile(
    r"(?://|#)\s*(TODO|FIXME|HACK|XXX)\b[:\s]*(.*)",
    re.IGNORECASE,
)


def run(
    project_path: str,
    source_dir: str = "Assets",
    file_extensions: list[str] | None = None,
) -> CheckResult:
    """Scan source files for marker comments."""
    if file_extensions is None:
        file_extensions = [".cs"]

    scan_dir = os.path.join(project_path, source_dir)
    if not os.path.isdir(scan_dir):
        return CheckResult(check_name=name, ok=True, summary=f"No {source_dir}/ directory")

    markers = []
    for root, dirs, files in os.walk(scan_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fname in files:
            if not any(fname.endswith(ext) for ext in file_extensions):
                continue
            full = os.path.join(root, fname)
            try:
                with open(full, "r", encoding="utf-8", errors="ignore") as f:
                    for line_num, line in enumerate(f, 1):
                        match = _MARKER_RE.search(line)
                        if match:
                            rel = os.path.relpath(full, project_path).replace("\\", "/")
                            markers.append({
                                "file": rel,
                                "line": line_num,
                                "marker": match.group(1).upper(),
                                "text": match.group(2).strip()[:100],
                            })
            except OSError:
                continue

    if markers:
        by_type = {}
        for m in markers:
            by_type[m["marker"]] = by_type.get(m["marker"], 0) + 1
        parts = [f"{count} {typ}" for typ, count in sorted(by_type.items())]
        return CheckResult(
            check_name=name,
            ok=True,  # Markers aren't errors
            issues=markers,
            summary=f"{len(markers)} marker(s): {', '.join(parts)}",
        )

    return CheckResult(check_name=name, ok=True, summary="No TODO/FIXME markers")
