"""Tests for daemon/cron_parser.py and daemon/scheduler.py."""

import os
import shutil
import tempfile
import time
import unittest
from datetime import datetime

from daemon.cron_parser import CronExpression, CronParseError, _parse_field
from daemon.scheduler import TaskScheduler, Schedule
from daemon.task_queue import TaskQueue


# ---- CronExpression parsing ----

class TestCronParseField(unittest.TestCase):

    def test_star(self):
        result = _parse_field("*", 0, 59)
        self.assertEqual(result, set(range(0, 60)))

    def test_exact_value(self):
        result = _parse_field("5", 0, 59)
        self.assertEqual(result, {5})

    def test_step(self):
        result = _parse_field("*/15", 0, 59)
        self.assertEqual(result, {0, 15, 30, 45})

    def test_range(self):
        result = _parse_field("1-5", 0, 6)
        self.assertEqual(result, {1, 2, 3, 4, 5})

    def test_range_with_step(self):
        result = _parse_field("0-10/3", 0, 59)
        self.assertEqual(result, {0, 3, 6, 9})

    def test_list(self):
        result = _parse_field("1,3,5", 0, 6)
        self.assertEqual(result, {1, 3, 5})

    def test_combined_list_and_range(self):
        result = _parse_field("1,3-5", 0, 6)
        self.assertEqual(result, {1, 3, 4, 5})

    def test_out_of_bounds_raises(self):
        with self.assertRaises(CronParseError):
            _parse_field("99", 0, 59)

    def test_invalid_step_raises(self):
        with self.assertRaises(CronParseError):
            _parse_field("*/abc", 0, 59)

    def test_invalid_range_raises(self):
        with self.assertRaises(CronParseError):
            _parse_field("5-2", 0, 59)


class TestCronExpression(unittest.TestCase):

    def test_every_minute(self):
        cron = CronExpression("* * * * *")
        # Should match any datetime
        self.assertTrue(cron.matches(datetime(2026, 2, 27, 10, 30)))

    def test_specific_time(self):
        cron = CronExpression("30 9 * * *")
        self.assertTrue(cron.matches(datetime(2026, 2, 27, 9, 30)))
        self.assertFalse(cron.matches(datetime(2026, 2, 27, 9, 31)))
        self.assertFalse(cron.matches(datetime(2026, 2, 27, 10, 30)))

    def test_every_5_minutes(self):
        cron = CronExpression("*/5 * * * *")
        self.assertTrue(cron.matches(datetime(2026, 2, 27, 10, 0)))
        self.assertTrue(cron.matches(datetime(2026, 2, 27, 10, 5)))
        self.assertFalse(cron.matches(datetime(2026, 2, 27, 10, 3)))

    def test_weekdays_only(self):
        # 0-4 = Monday-Friday
        cron = CronExpression("0 9 * * 0-4")
        # 2026-02-27 is a Friday (weekday=4)
        self.assertTrue(cron.matches(datetime(2026, 2, 27, 9, 0)))
        # 2026-03-01 is a Sunday (weekday=6)
        self.assertFalse(cron.matches(datetime(2026, 3, 1, 9, 0)))

    def test_specific_day_of_month(self):
        cron = CronExpression("0 0 1 * *")
        self.assertTrue(cron.matches(datetime(2026, 3, 1, 0, 0)))
        self.assertFalse(cron.matches(datetime(2026, 3, 2, 0, 0)))

    def test_specific_month(self):
        cron = CronExpression("0 0 * 12 *")
        self.assertTrue(cron.matches(datetime(2026, 12, 25, 0, 0)))
        self.assertFalse(cron.matches(datetime(2026, 11, 25, 0, 0)))

    def test_wrong_field_count_raises(self):
        with self.assertRaises(CronParseError):
            CronExpression("* * *")

    def test_next_run(self):
        cron = CronExpression("0 * * * *")  # Every hour on the hour
        after = datetime(2026, 2, 27, 10, 30)
        nxt = cron.next_run(after=after)
        self.assertIsNotNone(nxt)
        self.assertEqual(nxt.hour, 11)
        self.assertEqual(nxt.minute, 0)

    def test_next_run_soon(self):
        cron = CronExpression("*/5 * * * *")
        after = datetime(2026, 2, 27, 10, 1)
        nxt = cron.next_run(after=after)
        self.assertIsNotNone(nxt)
        self.assertEqual(nxt.minute, 5)

    def test_describe(self):
        cron = CronExpression("*/5 * * * *")
        desc = cron.describe()
        self.assertIn("5 minutes", desc)


# ---- Schedule ----

class TestSchedule(unittest.TestCase):

    def test_is_due_matches(self):
        sched = Schedule("test", "*/5 * * * *", "my_template")
        # Minute 0 matches */5
        self.assertTrue(sched.is_due(datetime(2026, 2, 27, 10, 0)))

    def test_is_due_not_matching(self):
        sched = Schedule("test", "*/5 * * * *", "my_template")
        self.assertFalse(sched.is_due(datetime(2026, 2, 27, 10, 3)))

    def test_is_due_disabled(self):
        sched = Schedule("test", "* * * * *", "my_template", enabled=False)
        self.assertFalse(sched.is_due(datetime(2026, 2, 27, 10, 0)))

    def test_no_double_fire_same_minute(self):
        sched = Schedule("test", "* * * * *", "my_template")
        now = datetime(2026, 2, 27, 10, 0)
        self.assertTrue(sched.is_due(now))
        # Simulate having just run
        sched.last_run = now.timestamp()
        self.assertFalse(sched.is_due(now))

    def test_to_dict(self):
        sched = Schedule("test", "0 9 * * *", "code_review", priority=5)
        d = sched.to_dict()
        self.assertEqual(d["id"], "test")
        self.assertEqual(d["cron"], "0 9 * * *")
        self.assertEqual(d["priority"], 5)
        self.assertIn("next_run", d)


# ---- TaskScheduler ----

class TestTaskScheduler(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "tasks.db")
        self.config_path = os.path.join(self.tmp, "schedules.yaml")
        self.templates_dir = os.path.join(self.tmp, "templates")
        os.makedirs(self.templates_dir, exist_ok=True)

        self.queue = TaskQueue(db_path=self.db_path)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_config(self, yaml_content: str):
        with open(self.config_path, "w") as f:
            f.write(yaml_content)

    def _write_template(self, name: str, content: str):
        with open(os.path.join(self.templates_dir, f"{name}.md"), "w") as f:
            f.write(content)

    def test_loads_schedules_from_yaml(self):
        self._write_config("""
schedules:
  - id: test1
    cron: "*/5 * * * *"
    task_template: fix_stuff
  - id: test2
    cron: "0 9 * * 0-4"
    task_template: review
    enabled: false
""")
        sched = TaskScheduler(self.queue, config_path=self.config_path,
                              templates_dir=self.templates_dir)
        self.assertEqual(len(sched.schedules), 2)
        self.assertEqual(sched.schedules[0].id, "test1")
        self.assertFalse(sched.schedules[1].enabled)

    def test_no_config_file_is_ok(self):
        sched = TaskScheduler(self.queue, config_path=self.config_path,
                              templates_dir=self.templates_dir)
        self.assertEqual(len(sched.schedules), 0)

    def test_invalid_cron_skipped(self):
        self._write_config("""
schedules:
  - id: bad
    cron: "not a cron"
    task_template: foo
  - id: good
    cron: "* * * * *"
    task_template: bar
""")
        sched = TaskScheduler(self.queue, config_path=self.config_path,
                              templates_dir=self.templates_dir)
        self.assertEqual(len(sched.schedules), 1)
        self.assertEqual(sched.schedules[0].id, "good")

    def test_tick_enqueues_due_tasks(self):
        self._write_config("""
schedules:
  - id: every_minute
    cron: "* * * * *"
    task_template: do_stuff
""")
        sched = TaskScheduler(self.queue, config_path=self.config_path,
                              templates_dir=self.templates_dir)
        enqueued = sched.tick("/fake/project")
        self.assertEqual(len(enqueued), 1)

        # Verify task is in queue
        tasks = self.queue.list_tasks()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].task_type, "scheduled")
        self.assertIn("every_minute", tasks[0].metadata.get("schedule_id", ""))

    def test_tick_skips_disabled(self):
        self._write_config("""
schedules:
  - id: off
    cron: "* * * * *"
    task_template: foo
    enabled: false
""")
        sched = TaskScheduler(self.queue, config_path=self.config_path,
                              templates_dir=self.templates_dir)
        enqueued = sched.tick("/fake/project")
        self.assertEqual(len(enqueued), 0)

    def test_tick_no_double_fire(self):
        self._write_config("""
schedules:
  - id: once
    cron: "* * * * *"
    task_template: foo
""")
        sched = TaskScheduler(self.queue, config_path=self.config_path,
                              templates_dir=self.templates_dir)

        enqueued1 = sched.tick("/fake/project")
        self.assertEqual(len(enqueued1), 1)

        # Second tick in same minute should not fire again
        enqueued2 = sched.tick("/fake/project")
        self.assertEqual(len(enqueued2), 0)

    def test_template_resolution(self):
        self._write_template("greet", "Hello {{name}}, fix {{thing}}!")
        self._write_config("""
schedules:
  - id: greet_task
    cron: "* * * * *"
    task_template: greet
    params:
      name: Alice
      thing: the bug
""")
        sched = TaskScheduler(self.queue, config_path=self.config_path,
                              templates_dir=self.templates_dir)
        enqueued = sched.tick("/fake/project")
        self.assertEqual(len(enqueued), 1)

        task = self.queue.get(enqueued[0])
        task_text = task.payload.get("task", "")
        self.assertIn("Hello Alice", task_text)
        self.assertIn("fix the bug", task_text)

    def test_template_fallback_no_file(self):
        self._write_config("""
schedules:
  - id: no_template
    cron: "* * * * *"
    task_template: nonexistent_template
""")
        sched = TaskScheduler(self.queue, config_path=self.config_path,
                              templates_dir=self.templates_dir)
        enqueued = sched.tick("/fake/project")
        self.assertEqual(len(enqueued), 1)

        task = self.queue.get(enqueued[0])
        self.assertIn("nonexistent_template", task.payload.get("task", ""))

    def test_add_schedule(self):
        sched = TaskScheduler(self.queue, config_path=self.config_path,
                              templates_dir=self.templates_dir)
        s = sched.add_schedule("new_one", "0 12 * * *", "my_template")
        self.assertEqual(s.id, "new_one")
        self.assertEqual(len(sched.schedules), 1)

        # Config file should exist now
        self.assertTrue(os.path.isfile(self.config_path))

    def test_add_duplicate_raises(self):
        sched = TaskScheduler(self.queue, config_path=self.config_path,
                              templates_dir=self.templates_dir)
        sched.add_schedule("dup", "0 0 * * *", "template")
        with self.assertRaises(ValueError):
            sched.add_schedule("dup", "0 0 * * *", "template")

    def test_update_schedule(self):
        sched = TaskScheduler(self.queue, config_path=self.config_path,
                              templates_dir=self.templates_dir)
        sched.add_schedule("upd", "0 0 * * *", "template")
        result = sched.update_schedule("upd", cron="*/10 * * * *", enabled=False)
        self.assertIsNotNone(result)
        self.assertEqual(result.cron_expr, "*/10 * * * *")
        self.assertFalse(result.enabled)

    def test_update_nonexistent(self):
        sched = TaskScheduler(self.queue, config_path=self.config_path,
                              templates_dir=self.templates_dir)
        self.assertIsNone(sched.update_schedule("nope", enabled=False))

    def test_delete_schedule(self):
        sched = TaskScheduler(self.queue, config_path=self.config_path,
                              templates_dir=self.templates_dir)
        sched.add_schedule("del_me", "0 0 * * *", "template")
        self.assertTrue(sched.delete_schedule("del_me"))
        self.assertEqual(len(sched.schedules), 0)
        self.assertFalse(sched.delete_schedule("del_me"))

    def test_reload(self):
        self._write_config("""
schedules:
  - id: initial
    cron: "0 0 * * *"
    task_template: foo
""")
        sched = TaskScheduler(self.queue, config_path=self.config_path,
                              templates_dir=self.templates_dir)
        self.assertEqual(len(sched.schedules), 1)

        # Update config file
        self._write_config("""
schedules:
  - id: initial
    cron: "0 0 * * *"
    task_template: foo
  - id: new_one
    cron: "*/10 * * * *"
    task_template: bar
""")
        sched.reload()
        self.assertEqual(len(sched.schedules), 2)

    def test_should_tick(self):
        sched = TaskScheduler(self.queue, config_path=self.config_path,
                              templates_dir=self.templates_dir)
        # First call should be true (no previous tick)
        self.assertTrue(sched.should_tick())
        sched._last_tick = time.time()
        # Right after a tick, should be false
        self.assertFalse(sched.should_tick())

    def test_status(self):
        self._write_config("""
schedules:
  - id: s1
    cron: "0 0 * * *"
    task_template: t1
  - id: s2
    cron: "0 12 * * *"
    task_template: t2
    enabled: false
""")
        sched = TaskScheduler(self.queue, config_path=self.config_path,
                              templates_dir=self.templates_dir)
        status = sched.status
        self.assertEqual(status["total_schedules"], 2)
        self.assertEqual(status["active_schedules"], 1)
        self.assertEqual(len(status["schedules"]), 2)

    def test_priority_passed_to_queue(self):
        self._write_config("""
schedules:
  - id: high_pri
    cron: "* * * * *"
    task_template: urgent
    priority: 100
""")
        sched = TaskScheduler(self.queue, config_path=self.config_path,
                              templates_dir=self.templates_dir)
        sched.tick("/fake/project")
        tasks = self.queue.list_tasks()
        self.assertEqual(tasks[0].priority, 100)


if __name__ == "__main__":
    unittest.main()
