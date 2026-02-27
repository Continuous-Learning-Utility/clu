"""Tests for manage_schedules tool."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.manage_schedules import ManageSchedulesTool
from daemon.scheduler import TaskScheduler
from daemon.task_queue import TaskQueue
from sandbox.path_validator import PathValidator
from sandbox.backup_manager import BackupManager


class TestManageSchedulesTool(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        self.queue = TaskQueue(db_path=self.db_path)
        self.sched_path = os.path.join(self.tmp, "schedules.yaml")
        self.scheduler = TaskScheduler(
            queue=self.queue, config_path=self.sched_path
        )
        self.tool = ManageSchedulesTool()
        self.tool._scheduler = self.scheduler
        self.sandbox = PathValidator()
        self.backup = BackupManager(os.path.join(self.tmp, "backups"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _exec(self, args):
        return self.tool.execute(args, "/project", self.sandbox, self.backup)

    def test_no_scheduler_returns_error(self):
        tool = ManageSchedulesTool()
        result = tool.execute({"action": "list"}, "/p", self.sandbox, self.backup)
        self.assertIn("error", result)

    def test_list_empty(self):
        result = self._exec({"action": "list"})
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["schedules"], [])

    def test_create_schedule(self):
        result = self._exec({
            "action": "create",
            "schedule_id": "daily_review",
            "cron": "0 9 * * *",
            "task_template": "code_review",
            "description": "Daily code review",
        })
        self.assertTrue(result["ok"])
        self.assertEqual(result["schedule"]["id"], "daily_review")
        self.assertEqual(result["schedule"]["cron"], "0 9 * * *")

    def test_create_missing_fields(self):
        result = self._exec({"action": "create", "schedule_id": "test"})
        self.assertIn("error", result)

    def test_create_duplicate(self):
        self._exec({
            "action": "create",
            "schedule_id": "dup",
            "cron": "* * * * *",
            "task_template": "test",
        })
        result = self._exec({
            "action": "create",
            "schedule_id": "dup",
            "cron": "* * * * *",
            "task_template": "test",
        })
        self.assertIn("error", result)

    def test_list_after_create(self):
        self._exec({
            "action": "create",
            "schedule_id": "s1",
            "cron": "0 */6 * * *",
            "task_template": "auto_fix_compile",
        })
        result = self._exec({"action": "list"})
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["schedules"][0]["id"], "s1")

    def test_update_schedule(self):
        self._exec({
            "action": "create",
            "schedule_id": "s1",
            "cron": "0 9 * * *",
            "task_template": "code_review",
        })
        result = self._exec({
            "action": "update",
            "schedule_id": "s1",
            "cron": "0 12 * * *",
            "priority": 5,
        })
        self.assertTrue(result["ok"])
        self.assertEqual(result["schedule"]["cron"], "0 12 * * *")
        self.assertEqual(result["schedule"]["priority"], 5)

    def test_update_nonexistent(self):
        result = self._exec({
            "action": "update",
            "schedule_id": "nope",
            "cron": "* * * * *",
        })
        self.assertIn("error", result)

    def test_delete_schedule(self):
        self._exec({
            "action": "create",
            "schedule_id": "s1",
            "cron": "* * * * *",
            "task_template": "test",
        })
        result = self._exec({"action": "delete", "schedule_id": "s1"})
        self.assertTrue(result["ok"])

        result = self._exec({"action": "list"})
        self.assertEqual(result["total"], 0)

    def test_delete_nonexistent(self):
        result = self._exec({"action": "delete", "schedule_id": "nope"})
        self.assertIn("error", result)

    def test_toggle_schedule(self):
        self._exec({
            "action": "create",
            "schedule_id": "s1",
            "cron": "* * * * *",
            "task_template": "test",
            "enabled": True,
        })
        result = self._exec({"action": "toggle", "schedule_id": "s1"})
        self.assertTrue(result["ok"])
        self.assertFalse(result["enabled"])

        # Toggle back
        result = self._exec({"action": "toggle", "schedule_id": "s1"})
        self.assertTrue(result["enabled"])

    def test_toggle_nonexistent(self):
        result = self._exec({"action": "toggle", "schedule_id": "nope"})
        self.assertIn("error", result)

    def test_unknown_action(self):
        result = self._exec({"action": "invalid"})
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
