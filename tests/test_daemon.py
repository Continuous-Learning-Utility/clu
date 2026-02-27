"""Tests for daemon/task_queue.py and daemon/daemon.py."""

import asyncio
import os
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from daemon.task_queue import TaskQueue, TaskStatus, TaskType


class TestTaskQueue(unittest.TestCase):
    """Test SQLite task queue operations."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test_tasks.db")
        self.queue = TaskQueue(db_path=self.db_path)

    def tearDown(self):
        try:
            os.remove(self.db_path)
            # WAL/SHM files
            for ext in ("-wal", "-shm"):
                p = self.db_path + ext
                if os.path.exists(p):
                    os.remove(p)
            os.rmdir(self.tmp)
        except OSError:
            pass

    def test_enqueue_returns_id(self):
        tid = self.queue.enqueue("Test task", "/project")
        self.assertIsInstance(tid, int)
        self.assertGreater(tid, 0)

    def test_enqueue_and_get(self):
        tid = self.queue.enqueue("Fix bug", "/project", priority=5)
        task = self.queue.get(tid)
        self.assertIsNotNone(task)
        self.assertEqual(task.status, TaskStatus.PENDING)
        self.assertEqual(task.priority, 5)
        self.assertEqual(task.payload["task"], "Fix bug")
        self.assertEqual(task.payload["project"], "/project")

    def test_dequeue_returns_highest_priority(self):
        self.queue.enqueue("Low priority", "/p", priority=0)
        self.queue.enqueue("High priority", "/p", priority=10)
        self.queue.enqueue("Medium priority", "/p", priority=5)

        task = self.queue.dequeue()
        self.assertIsNotNone(task)
        self.assertEqual(task.payload["task"], "High priority")
        self.assertEqual(task.status, TaskStatus.RUNNING)
        self.assertEqual(task.attempts, 1)

    def test_dequeue_empty_returns_none(self):
        self.assertIsNone(self.queue.dequeue())

    def test_dequeue_skips_running(self):
        self.queue.enqueue("Task 1", "/p")
        task = self.queue.dequeue()  # Claims task 1
        self.assertIsNotNone(task)
        self.assertIsNone(self.queue.dequeue())  # No more pending

    def test_complete(self):
        tid = self.queue.enqueue("Task", "/p")
        self.queue.dequeue()
        self.queue.complete(tid, result={"response": "Done"})

        task = self.queue.get(tid)
        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertIsNotNone(task.completed_at)
        self.assertEqual(task.result["response"], "Done")

    def test_fail_auto_retries(self):
        tid = self.queue.enqueue("Flaky task", "/p", max_attempts=3)
        self.queue.dequeue()
        self.queue.fail(tid, "Connection error")

        task = self.queue.get(tid)
        # Should be requeued (attempt 1 < max 3)
        self.assertEqual(task.status, TaskStatus.PENDING)
        self.assertEqual(task.error, "Connection error")

    def test_fail_permanent_after_max_attempts(self):
        tid = self.queue.enqueue("Doomed task", "/p", max_attempts=1)
        self.queue.dequeue()
        self.queue.fail(tid, "Fatal error")

        task = self.queue.get(tid)
        self.assertEqual(task.status, TaskStatus.FAILED)

    def test_cancel_pending(self):
        tid = self.queue.enqueue("Cancel me", "/p")
        self.assertTrue(self.queue.cancel(tid))
        task = self.queue.get(tid)
        self.assertEqual(task.status, TaskStatus.CANCELLED)

    def test_cancel_running_fails(self):
        tid = self.queue.enqueue("Running", "/p")
        self.queue.dequeue()
        self.assertFalse(self.queue.cancel(tid))

    def test_retry_failed(self):
        tid = self.queue.enqueue("Retry me", "/p", max_attempts=1)
        self.queue.dequeue()
        self.queue.fail(tid, "Oops")
        self.assertEqual(self.queue.get(tid).status, TaskStatus.FAILED)

        self.assertTrue(self.queue.retry(tid))
        self.assertEqual(self.queue.get(tid).status, TaskStatus.PENDING)

    def test_cleanup_stale(self):
        tid = self.queue.enqueue("Stale", "/p")
        self.queue.dequeue()
        # Manually backdate started_at
        with self.queue._connect() as conn:
            conn.execute(
                "UPDATE tasks SET started_at = ? WHERE id = ?",
                (time.time() - 9999, tid),
            )

        count = self.queue.cleanup_stale(timeout_seconds=60)
        self.assertEqual(count, 1)
        self.assertEqual(self.queue.get(tid).status, TaskStatus.PENDING)

    def test_list_tasks(self):
        self.queue.enqueue("A", "/p")
        self.queue.enqueue("B", "/p")
        self.queue.enqueue("C", "/p")

        tasks = self.queue.list_tasks()
        self.assertEqual(len(tasks), 3)

        pending = self.queue.list_tasks(status=TaskStatus.PENDING)
        self.assertEqual(len(pending), 3)

    def test_stats(self):
        self.queue.enqueue("A", "/p")
        self.queue.enqueue("B", "/p")
        self.queue.dequeue()

        stats = self.queue.stats()
        self.assertEqual(stats["pending"], 1)
        self.assertEqual(stats["running"], 1)
        self.assertEqual(stats["total"], 2)

    def test_pending_count(self):
        self.queue.enqueue("A", "/p")
        self.queue.enqueue("B", "/p")
        self.assertEqual(self.queue.pending_count(), 2)

    def test_task_types(self):
        tid = self.queue.enqueue("Heartbeat check", "/p", task_type=TaskType.HEARTBEAT)
        task = self.queue.get(tid)
        self.assertEqual(task.task_type, TaskType.HEARTBEAT)

    def test_parent_id(self):
        parent = self.queue.enqueue("Parent", "/p")
        child = self.queue.enqueue("Child", "/p", parent_id=parent)
        task = self.queue.get(child)
        self.assertEqual(task.parent_id, parent)

    def test_priority_ordering_fifo_for_same_priority(self):
        """Same priority tasks should be FIFO."""
        id1 = self.queue.enqueue("First", "/p", priority=0)
        id2 = self.queue.enqueue("Second", "/p", priority=0)

        task = self.queue.dequeue()
        self.assertEqual(task.id, id1)


class TestAgentDaemon(unittest.TestCase):
    """Test AgentDaemon logic."""

    def test_daemon_status_initial(self):
        from daemon.daemon import AgentDaemon
        from orchestrator.config import AgentConfig

        config = AgentConfig()
        queue = TaskQueue(db_path=os.path.join(tempfile.mkdtemp(), "test.db"))
        daemon = AgentDaemon(config=config, queue=queue)

        status = daemon.status
        self.assertFalse(status["running"])
        self.assertEqual(status["tasks_completed"], 0)
        self.assertEqual(status["tasks_failed"], 0)

    def test_daemon_execute_task_invalid_project(self):
        """Tasks with invalid project paths should fail gracefully."""
        from daemon.daemon import AgentDaemon
        from orchestrator.config import AgentConfig

        tmp = tempfile.mkdtemp()
        config = AgentConfig()
        queue = TaskQueue(db_path=os.path.join(tmp, "test.db"))
        daemon = AgentDaemon(config=config, queue=queue)

        tid = queue.enqueue("Fix bug", "/nonexistent/path")
        task = queue.dequeue()

        asyncio.run(daemon._execute_task(task))

        result = queue.get(tid)
        # Should be requeued or failed due to invalid path
        self.assertIn(result.status, [TaskStatus.PENDING, TaskStatus.FAILED])
        self.assertIn("Invalid project path", result.error)


class TestDaemonService(unittest.TestCase):
    """Test daemon service management."""

    def test_status_when_not_running(self):
        from daemon.service import status
        result = status()
        # May or may not be running — just check structure
        self.assertIn("running", result)
        self.assertIn("pid", result)


if __name__ == "__main__":
    unittest.main()
