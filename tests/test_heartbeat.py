"""Tests for heartbeat checks and HeartbeatManager."""

import os
import tempfile
import time
import unittest

from daemon.checks.base import CheckResult
from daemon.checks import unity_compile, todo_markers, large_files, new_files
from daemon.heartbeat import HeartbeatManager, HeartbeatConfig
from daemon.task_queue import TaskQueue, TaskType


class TestUnityCompileCheck(unittest.TestCase):

    def test_no_editor_log(self):
        """Should return ok=True when Editor.log is not found."""
        result = unity_compile.run("/nonexistent")
        self.assertTrue(result.ok)
        self.assertEqual(result.check_name, "unity_compile")

    def test_parse_errors(self):
        """Test the regex against sample Editor.log content."""
        import re
        sample = (
            "Assets/Scripts/Player.cs(42,10): error CS1002: ; expected\n"
            "Assets/Scripts/Enemy.cs(15,5): error CS0246: The type or namespace name 'Foo' could not be found\n"
            "Some other log line\n"
            "Assets/Scripts/Player.cs(42,10): error CS1002: ; expected\n"  # duplicate
        )
        errors = []
        seen = set()
        for match in unity_compile._ERROR_RE.finditer(sample):
            file_path, line, col, code, message = match.groups()
            key = (file_path, code, line)
            if key in seen:
                continue
            seen.add(key)
            errors.append({"file": file_path, "code": code})

        self.assertEqual(len(errors), 2)
        self.assertEqual(errors[0]["file"], "Assets/Scripts/Player.cs")
        self.assertEqual(errors[0]["code"], "CS1002")
        self.assertEqual(errors[1]["file"], "Assets/Scripts/Enemy.cs")


class TestTodoMarkersCheck(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.assets = os.path.join(self.tmp, "Assets", "Scripts")
        os.makedirs(self.assets)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_finds_markers(self):
        with open(os.path.join(self.assets, "Test.cs"), "w") as f:
            f.write("// TODO: fix this\n")
            f.write("int x = 1;\n")
            f.write("// FIXME: broken\n")
            f.write("// HACK: workaround\n")

        result = todo_markers.run(self.tmp)
        self.assertTrue(result.ok)  # Markers are advisory
        self.assertEqual(result.issue_count, 3)
        markers = [m["marker"] for m in result.issues]
        self.assertIn("TODO", markers)
        self.assertIn("FIXME", markers)
        self.assertIn("HACK", markers)

    def test_no_markers(self):
        with open(os.path.join(self.assets, "Clean.cs"), "w") as f:
            f.write("public class Clean {}\n")

        result = todo_markers.run(self.tmp)
        self.assertEqual(result.issue_count, 0)

    def test_no_assets_dir(self):
        result = todo_markers.run("/nonexistent")
        self.assertTrue(result.ok)


class TestLargeFilesCheck(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.assets = os.path.join(self.tmp, "Assets")
        os.makedirs(self.assets)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_detects_large_file(self):
        with open(os.path.join(self.assets, "Big.cs"), "w") as f:
            for i in range(500):
                f.write(f"// line {i}\n")

        result = large_files.run(self.tmp, threshold=300)
        self.assertEqual(result.issue_count, 1)
        self.assertEqual(result.issues[0]["lines"], 500)
        self.assertEqual(result.issues[0]["over_by"], 200)

    def test_small_files_ok(self):
        with open(os.path.join(self.assets, "Small.cs"), "w") as f:
            f.write("class Small {}\n")

        result = large_files.run(self.tmp, threshold=300)
        self.assertEqual(result.issue_count, 0)


class TestNewFilesCheck(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.assets = os.path.join(self.tmp, "Assets")
        os.makedirs(self.assets)
        # Override state file to temp
        self._orig_state = new_files._STATE_FILE
        new_files._STATE_FILE = os.path.join(self.tmp, "state.json")

    def tearDown(self):
        new_files._STATE_FILE = self._orig_state
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_detects_new_files(self):
        # First run sets the baseline
        result1 = new_files.run(self.tmp)
        # All files are "new" since last_check was 0
        # Create a file after first run
        time.sleep(0.1)
        with open(os.path.join(self.assets, "New.cs"), "w") as f:
            f.write("class New {}\n")

        result2 = new_files.run(self.tmp)
        self.assertEqual(result2.issue_count, 1)
        self.assertIn("New.cs", result2.issues[0]["file"])

    def test_no_changes(self):
        # First run
        new_files.run(self.tmp)
        time.sleep(0.1)
        # Second run with no new files
        result = new_files.run(self.tmp)
        self.assertEqual(result.issue_count, 0)


class TestHeartbeatManager(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        self.queue = TaskQueue(db_path=self.db_path)
        # Override state file for new_files check
        self._orig_state = new_files._STATE_FILE
        new_files._STATE_FILE = os.path.join(self.tmp, "state.json")

    def tearDown(self):
        new_files._STATE_FILE = self._orig_state
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_should_tick_initial(self):
        hb = HeartbeatManager(queue=self.queue)
        self.assertTrue(hb.should_tick())

    def test_should_tick_respects_interval(self):
        config = HeartbeatConfig(interval=9999)
        hb = HeartbeatManager(queue=self.queue, config=config)
        hb._status.last_tick = time.time()
        self.assertFalse(hb.should_tick())

    def test_should_tick_disabled(self):
        config = HeartbeatConfig(enabled=False)
        hb = HeartbeatManager(queue=self.queue, config=config)
        self.assertFalse(hb.should_tick())

    def test_tick_runs_all_checks(self):
        project = tempfile.mkdtemp()
        os.makedirs(os.path.join(project, "Assets"), exist_ok=True)

        hb = HeartbeatManager(queue=self.queue)
        results = hb.tick(project)

        self.assertEqual(len(results), 4)
        check_names = [r.check_name for r in results]
        self.assertIn("unity_compile", check_names)
        self.assertIn("new_files", check_names)
        self.assertIn("todo_markers", check_names)
        self.assertIn("large_files", check_names)

        import shutil
        shutil.rmtree(project, ignore_errors=True)

    def test_tick_increments_counter(self):
        project = tempfile.mkdtemp()
        os.makedirs(os.path.join(project, "Assets"), exist_ok=True)

        hb = HeartbeatManager(queue=self.queue)
        hb.tick(project)
        hb.tick(project)

        self.assertEqual(hb._status.total_ticks, 2)
        self.assertIsNotNone(hb._status.last_tick)

        import shutil
        shutil.rmtree(project, ignore_errors=True)

    def test_status_dict(self):
        hb = HeartbeatManager(queue=self.queue)
        status = hb.status
        self.assertIn("enabled", status)
        self.assertIn("interval", status)
        self.assertIn("total_ticks", status)

    def test_auto_enqueue_compile_errors(self):
        """Heartbeat should auto-enqueue a task when compile errors are detected."""
        config = HeartbeatConfig(auto_fix_compile_errors=True)
        hb = HeartbeatManager(queue=self.queue, config=config)

        # Simulate compile error result
        fake_result = CheckResult(
            check_name="unity_compile",
            ok=False,
            issues=[{
                "file": "Assets/Scripts/Test.cs",
                "line": 10, "column": 5,
                "code": "CS1002", "message": "; expected",
            }],
            summary="1 error",
        )
        hb._auto_enqueue([fake_result], "/project")

        self.assertEqual(self.queue.pending_count(), 1)
        task = self.queue.dequeue()
        self.assertIn("CS1002", task.payload["task"])
        self.assertEqual(task.task_type, TaskType.HEARTBEAT)
        self.assertEqual(task.priority, 10)

    def test_rate_limit(self):
        """Should stop auto-enqueuing after max_auto_tasks_per_hour."""
        config = HeartbeatConfig(max_auto_tasks_per_hour=2)
        hb = HeartbeatManager(queue=self.queue, config=config)

        fake_result = CheckResult(
            check_name="unity_compile", ok=False,
            issues=[{"file": "F.cs", "line": 1, "column": 1, "code": "CS1", "message": "err"}],
        )

        hb._auto_enqueue([fake_result], "/p")
        hb._auto_enqueue([fake_result], "/p")
        hb._auto_enqueue([fake_result], "/p")  # Should be rate-limited

        self.assertEqual(self.queue.pending_count(), 2)

    def test_invalid_project_path(self):
        hb = HeartbeatManager(queue=self.queue)
        results = hb.tick("/nonexistent")
        self.assertEqual(len(results), 0)

    def test_subset_checks(self):
        """Heartbeat should only run checks listed in config."""
        project = tempfile.mkdtemp()
        os.makedirs(os.path.join(project, "Assets"), exist_ok=True)

        config = HeartbeatConfig(checks=["todo_markers", "large_files"])
        hb = HeartbeatManager(queue=self.queue, config=config)
        results = hb.tick(project)

        self.assertEqual(len(results), 2)
        check_names = [r.check_name for r in results]
        self.assertIn("todo_markers", check_names)
        self.assertIn("large_files", check_names)
        self.assertNotIn("unity_compile", check_names)
        self.assertNotIn("new_files", check_names)

        import shutil
        shutil.rmtree(project, ignore_errors=True)

    def test_auto_fix_on_error_disabled(self):
        """Should not auto-enqueue when auto_fix_on_error is False."""
        config = HeartbeatConfig(auto_fix_on_error=False)
        hb = HeartbeatManager(queue=self.queue, config=config)

        fake_result = CheckResult(
            check_name="unity_compile", ok=False,
            issues=[{"file": "F.cs", "line": 1, "column": 1, "code": "CS1", "message": "err"}],
        )
        hb._auto_enqueue([fake_result], "/project")

        self.assertEqual(self.queue.pending_count(), 0)

    def test_custom_source_dir_and_extensions(self):
        """Heartbeat checks should use custom source_dir and file_extensions."""
        project = tempfile.mkdtemp()
        src_dir = os.path.join(project, "src")
        os.makedirs(src_dir)
        with open(os.path.join(src_dir, "app.py"), "w") as f:
            f.write("# TODO: fix this\n")

        config = HeartbeatConfig(
            checks=["todo_markers"],
            source_dir="src",
            file_extensions=[".py"],
        )
        hb = HeartbeatManager(queue=self.queue, config=config)
        results = hb.tick(project)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].check_name, "todo_markers")
        self.assertEqual(results[0].issue_count, 1)

        import shutil
        shutil.rmtree(project, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
