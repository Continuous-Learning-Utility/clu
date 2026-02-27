"""Persistent memory system for the agent.

Layered file-based memory:
  memory/daily/YYYY-MM-DD.md    — activity logs per day
  memory/knowledge/*.md          — learned conventions, patterns, known issues
  memory/context/last_summary.md — compacted summary of old logs
"""

import logging
import os
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Default memory root relative to project root
DEFAULT_MEMORY_DIR = os.path.join(os.path.dirname(__file__), "..", "memory")

# Knowledge categories the agent can read/write
CATEGORIES = ["conventions", "known_issues", "project_patterns"]


class MemoryManager:
    """Manages persistent memory across agent sessions.

    Three layers:
    1. Daily logs — append-only activity record
    2. Knowledge base — editable category files (conventions, issues, patterns)
    3. Context summary — compacted old logs for long-term context
    """

    def __init__(self, memory_dir: str | None = None):
        self.memory_dir = memory_dir or DEFAULT_MEMORY_DIR
        self._daily_dir = os.path.join(self.memory_dir, "daily")
        self._knowledge_dir = os.path.join(self.memory_dir, "knowledge")
        self._context_dir = os.path.join(self.memory_dir, "context")

        for d in (self._daily_dir, self._knowledge_dir, self._context_dir):
            os.makedirs(d, exist_ok=True)

    # ---- Daily logs ----

    def log_activity(self, task: str, result_summary: str,
                     files_modified: list[str] | None = None,
                     session_id: str | None = None):
        """Append an activity entry to today's log."""
        today = datetime.now().strftime("%Y-%m-%d")
        path = os.path.join(self._daily_dir, f"{today}.md")
        timestamp = datetime.now().strftime("%H:%M:%S")

        entry_lines = [
            f"## [{timestamp}] Task",
            f"**Task:** {task[:200]}",
            f"**Result:** {result_summary[:500]}",
        ]
        if session_id:
            entry_lines.append(f"**Session:** {session_id}")
        if files_modified:
            entry_lines.append(f"**Files modified:** {', '.join(files_modified[:20])}")
        entry_lines.append("")

        entry = "\n".join(entry_lines) + "\n"

        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(entry)
        except OSError as e:
            logger.error("Failed to write daily log: %s", e)

    def get_daily_log(self, date: str | None = None) -> str:
        """Read a daily log. Defaults to today."""
        date = date or datetime.now().strftime("%Y-%m-%d")
        path = os.path.join(self._daily_dir, f"{date}.md")
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    def list_daily_logs(self) -> list[str]:
        """List available daily log dates, newest first."""
        try:
            files = sorted(os.listdir(self._daily_dir), reverse=True)
            return [f.replace(".md", "") for f in files if f.endswith(".md")]
        except OSError:
            return []

    # ---- Knowledge base ----

    def read_knowledge(self, category: str) -> str:
        """Read a knowledge category file."""
        if category not in CATEGORIES:
            return f"Unknown category: {category}. Available: {', '.join(CATEGORIES)}"
        path = os.path.join(self._knowledge_dir, f"{category}.md")
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    def write_knowledge(self, category: str, content: str) -> bool:
        """Overwrite a knowledge category file."""
        if category not in CATEGORIES:
            return False
        path = os.path.join(self._knowledge_dir, f"{category}.md")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except OSError as e:
            logger.error("Failed to write knowledge '%s': %s", category, e)
            return False

    def append_knowledge(self, category: str, entry: str) -> bool:
        """Append an entry to a knowledge category."""
        if category not in CATEGORIES:
            return False
        path = os.path.join(self._knowledge_dir, f"{category}.md")
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"\n- {entry}\n")
            return True
        except OSError as e:
            logger.error("Failed to append to knowledge '%s': %s", category, e)
            return False

    # ---- Context for system prompt ----

    def get_context_for_task(self, task: str) -> str:
        """Build memory context to inject into the system prompt.

        Includes: last summary, today's log, all knowledge files.
        Kept concise to avoid blowing up context window.
        """
        sections = []

        # Last summary (compacted old logs)
        summary = self._read_context_summary()
        if summary:
            sections.append(f"### Previous Activity Summary\n{summary[:1000]}")

        # Today's log (last 5 entries)
        today_log = self.get_daily_log()
        if today_log:
            # Take last ~1000 chars
            trimmed = today_log[-1000:] if len(today_log) > 1000 else today_log
            sections.append(f"### Today's Activity\n{trimmed}")

        # Knowledge base
        for category in CATEGORIES:
            content = self.read_knowledge(category)
            if content:
                trimmed = content[:500] if len(content) > 500 else content
                title = category.replace("_", " ").title()
                sections.append(f"### {title}\n{trimmed}")

        if not sections:
            return ""

        return "## Agent Memory\n\n" + "\n\n".join(sections) + "\n"

    def _read_context_summary(self) -> str:
        path = os.path.join(self._context_dir, "last_summary.md")
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    # ---- Compaction ----

    def compact_old_logs(self, days_to_keep: int = 7) -> str | None:
        """Merge old daily logs into a summary file.

        Logs older than days_to_keep are concatenated into context/last_summary.md
        and the original files are deleted.

        Returns the summary content or None if nothing to compact.
        """
        cutoff = datetime.now() - timedelta(days=days_to_keep)
        cutoff_str = cutoff.strftime("%Y-%m-%d")

        old_logs = []
        old_files = []

        for date_str in self.list_daily_logs():
            if date_str < cutoff_str:
                content = self.get_daily_log(date_str)
                if content:
                    old_logs.append(f"# {date_str}\n{content}")
                old_files.append(
                    os.path.join(self._daily_dir, f"{date_str}.md")
                )

        if not old_logs:
            return None

        # Merge with existing summary
        existing = self._read_context_summary()
        merged = existing + "\n\n" + "\n\n".join(old_logs) if existing else "\n\n".join(old_logs)

        # Truncate if too large (keep last 5000 chars)
        if len(merged) > 5000:
            merged = "...(truncated)...\n" + merged[-5000:]

        # Write summary
        summary_path = os.path.join(self._context_dir, "last_summary.md")
        try:
            with open(summary_path, "w", encoding="utf-8") as f:
                f.write(merged)
        except OSError as e:
            logger.error("Failed to write summary: %s", e)
            return None

        # Delete old logs
        for path in old_files:
            try:
                os.remove(path)
            except OSError:
                pass

        logger.info("Compacted %d old daily logs", len(old_files))
        return merged
