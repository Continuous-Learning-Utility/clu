"""Tests for orchestrator/memory.py and tools/memory_tool.py."""

import os
import shutil
import tempfile
import time
import unittest

from orchestrator.memory import MemoryManager, CATEGORIES
from tools.memory_tool import MemoryTool


class TestMemoryManager(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.mem = MemoryManager(memory_dir=self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---- Daily logs ----

    def test_log_activity(self):
        self.mem.log_activity("Fix bug", "Fixed null reference in Player.cs")
        log = self.mem.get_daily_log()
        self.assertIn("Fix bug", log)
        self.assertIn("Fixed null reference", log)

    def test_log_activity_with_files(self):
        self.mem.log_activity(
            "Refactor", "Extracted class",
            files_modified=["Assets/Scripts/Player.cs"],
            session_id="20260227_120000",
        )
        log = self.mem.get_daily_log()
        self.assertIn("Player.cs", log)
        self.assertIn("20260227_120000", log)

    def test_get_daily_log_empty(self):
        self.assertEqual(self.mem.get_daily_log(), "")

    def test_list_daily_logs(self):
        self.mem.log_activity("Task 1", "Done")
        logs = self.mem.list_daily_logs()
        self.assertEqual(len(logs), 1)

    # ---- Knowledge base ----

    def test_write_and_read_knowledge(self):
        self.mem.write_knowledge("conventions", "Use PascalCase for public methods")
        content = self.mem.read_knowledge("conventions")
        self.assertIn("PascalCase", content)

    def test_append_knowledge(self):
        self.mem.write_knowledge("known_issues", "Initial")
        self.mem.append_knowledge("known_issues", "Unity 6 broke serialization")
        content = self.mem.read_knowledge("known_issues")
        self.assertIn("Initial", content)
        self.assertIn("Unity 6 broke serialization", content)

    def test_read_empty_knowledge(self):
        self.assertEqual(self.mem.read_knowledge("conventions"), "")

    def test_invalid_category(self):
        result = self.mem.read_knowledge("invalid")
        self.assertIn("Unknown category", result)
        self.assertFalse(self.mem.write_knowledge("invalid", "x"))

    # ---- Context for system prompt ----

    def test_get_context_empty(self):
        ctx = self.mem.get_context_for_task("Do something")
        self.assertEqual(ctx, "")

    def test_get_context_with_data(self):
        self.mem.write_knowledge("conventions", "Always use [SerializeField]")
        self.mem.log_activity("Previous task", "Done")

        ctx = self.mem.get_context_for_task("New task")
        self.assertIn("Agent Memory", ctx)
        self.assertIn("SerializeField", ctx)
        self.assertIn("Previous task", ctx)

    def test_context_includes_summary(self):
        # Write a summary file directly
        summary_path = os.path.join(self.tmp, "context", "last_summary.md")
        with open(summary_path, "w") as f:
            f.write("Yesterday I refactored PlayerController")

        ctx = self.mem.get_context_for_task("task")
        self.assertIn("PlayerController", ctx)

    # ---- Compaction ----

    def test_compact_old_logs(self):
        # Create a fake old log
        old_date = "2020-01-01"
        old_path = os.path.join(self.tmp, "daily", f"{old_date}.md")
        with open(old_path, "w") as f:
            f.write("## Old task\nDid something\n")

        # Also create today's log (should NOT be compacted)
        self.mem.log_activity("Today", "Current work")

        result = self.mem.compact_old_logs(days_to_keep=7)
        self.assertIsNotNone(result)
        self.assertIn("Old task", result)

        # Old file should be deleted
        self.assertFalse(os.path.exists(old_path))

        # Today's file should still exist
        self.assertTrue(len(self.mem.list_daily_logs()) >= 1)

    def test_compact_nothing_to_compact(self):
        result = self.mem.compact_old_logs()
        self.assertIsNone(result)


class TestMemoryTool(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tool = MemoryTool()
        self.tool._memory = MemoryManager(memory_dir=self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_tool_name(self):
        self.assertEqual(self.tool.name, "memory")

    def test_tool_schema(self):
        schema = self.tool.to_openai_schema()
        self.assertEqual(schema["function"]["name"], "memory")
        self.assertIn("action", schema["function"]["parameters"]["properties"])

    def test_read_empty(self):
        result = self.tool.execute(
            {"action": "read", "category": "conventions"},
            "/project", None, None,
        )
        self.assertIn("(empty)", result["content"])

    def test_write_then_read(self):
        self.tool.execute(
            {"action": "write", "category": "conventions", "content": "Use events"},
            "/project", None, None,
        )
        result = self.tool.execute(
            {"action": "read", "category": "conventions"},
            "/project", None, None,
        )
        self.assertIn("Use events", result["content"])

    def test_append(self):
        self.tool.execute(
            {"action": "append", "category": "known_issues", "content": "Bug #1"},
            "/project", None, None,
        )
        result = self.tool.execute(
            {"action": "read", "category": "known_issues"},
            "/project", None, None,
        )
        self.assertIn("Bug #1", result["content"])

    def test_log(self):
        result = self.tool.execute(
            {"action": "log", "content": "Noticed pattern X"},
            "/project", None, None,
        )
        self.assertTrue(result["ok"])

    def test_today(self):
        self.tool.execute(
            {"action": "log", "content": "Activity"},
            "/project", None, None,
        )
        result = self.tool.execute(
            {"action": "today"},
            "/project", None, None,
        )
        self.assertIn("Activity", result["content"])

    def test_read_missing_category(self):
        result = self.tool.execute(
            {"action": "read"},
            "/project", None, None,
        )
        self.assertIn("error", result)

    def test_unknown_action(self):
        result = self.tool.execute(
            {"action": "delete"},
            "/project", None, None,
        )
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
