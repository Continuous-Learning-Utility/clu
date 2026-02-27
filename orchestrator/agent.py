"""Synchronous Agent wrapper around the unified AgentRunner.

This is a thin CLI-friendly wrapper. The canonical loop lives in runner.py.
"""

import asyncio
import logging
import os

from orchestrator.config import AgentConfig
from orchestrator.budget import BudgetTracker
from orchestrator.providers.factory import create_provider
from orchestrator.runner import AgentRunner, AgentResult
from sandbox.backup_manager import BackupManager

logger = logging.getLogger(__name__)

__all__ = ["Agent", "AgentResult"]


class Agent:
    """Synchronous CLI wrapper around AgentRunner."""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.provider = create_provider(
            config.provider, config.api_base, config.api_key, config.model
        )
        self._backup_dir = os.path.join(
            os.path.dirname(__file__), "..", config.backup_dir
        )
        # Standalone backup for --rollback without a run
        self.backup = BackupManager(self._backup_dir)
        self.budget = BudgetTracker(
            max_iterations=config.max_iterations,
            max_total_tokens=config.max_total_tokens,
            max_context_tokens=config.max_context_tokens,
        )

    def run(self, task: str, project_path: str) -> AgentResult:
        """Execute a task synchronously. Delegates to AgentRunner."""
        runner = AgentRunner(
            config=self.config,
            provider=self.provider,
            project_path=project_path,
        )

        async def log_event(event):
            msg = event.data.get("message", "")
            if event.type == "warning":
                logger.warning("%s", msg)
            elif event.type == "error":
                logger.error("%s", msg)
            elif event.type == "tool_call":
                logger.info(
                    "Tool: %s(%s)",
                    event.data.get("name"),
                    str(event.data.get("arguments", ""))[:100],
                )
            elif event.type == "iteration":
                logger.info(
                    "Iteration %d/%d",
                    event.data.get("current", 0),
                    event.data.get("max", 0),
                )

        result = asyncio.run(runner.run(task=task, on_event=log_event))

        # Expose runner internals for backwards compat (CLI prints budget info)
        self.backup = runner.backup
        self.budget = runner.budget

        return result
