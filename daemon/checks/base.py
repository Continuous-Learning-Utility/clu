"""Base class for heartbeat checks."""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class CheckResult:
    """Result of a single heartbeat check."""
    check_name: str
    ok: bool
    issues: list[dict] = field(default_factory=list)
    summary: str = ""

    @property
    def issue_count(self) -> int:
        return len(self.issues)


class HeartbeatCheck(Protocol):
    """Protocol for heartbeat checks. Each check must implement run()."""

    name: str

    def run(self, project_path: str) -> CheckResult:
        """Run the check against the project. Must be cheap (no LLM calls)."""
        ...
