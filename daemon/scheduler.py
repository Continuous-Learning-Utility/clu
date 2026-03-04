"""TaskScheduler: cron-like scheduler that enqueues tasks on schedule.

Reads schedule definitions from YAML config. On each tick, checks which
schedules are due and enqueues the corresponding tasks.

Usage:
    scheduler = TaskScheduler(queue, config_path="config/schedules.yaml")
    # In daemon loop:
    if scheduler.should_tick():
        scheduler.tick(project_path)
"""

import logging
import os
import time

import yaml

from daemon.cron_parser import CronExpression, CronParseError
from daemon.task_queue import TaskQueue, TaskType
from datetime import datetime

logger = logging.getLogger(__name__)

DEFAULT_SCHEDULES_PATH = os.path.join(
    os.path.dirname(__file__), "..", "config", "schedules.yaml"
)
DEFAULT_TEMPLATES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "prompts", "task_templates", "automation"
)


class Schedule:
    """A single schedule definition."""

    def __init__(
        self,
        schedule_id: str,
        cron: str,
        task_template: str,
        enabled: bool = True,
        priority: int = 0,
        description: str = "",
        params: dict | None = None,
    ):
        self.id = schedule_id
        self.cron_expr = cron
        self.cron = CronExpression(cron)
        self.task_template = task_template
        self.enabled = enabled
        self.priority = priority
        self.description = description or self.cron.describe()
        self.params = params or {}

        # Tracking
        self.last_run: float | None = None
        self.run_count: int = 0
        self.last_error: str | None = None

    def is_due(self, now: datetime | None = None) -> bool:
        """Check if this schedule should fire now."""
        if not self.enabled:
            return False
        if now is None:
            now = datetime.now()

        # Don't fire twice in the same minute
        if self.last_run:
            last_dt = datetime.fromtimestamp(self.last_run)
            if (last_dt.year == now.year and last_dt.month == now.month
                    and last_dt.day == now.day and last_dt.hour == now.hour
                    and last_dt.minute == now.minute):
                return False

        return self.cron.matches(now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "cron": self.cron_expr,
            "task_template": self.task_template,
            "enabled": self.enabled,
            "priority": self.priority,
            "description": self.description,
            "params": self.params,
            "last_run": self.last_run,
            "run_count": self.run_count,
            "last_error": self.last_error,
            "next_run": self.cron.next_run().isoformat() if self.enabled else None,
        }


class TaskScheduler:
    """Manages scheduled tasks and enqueues them on their cron schedule."""

    def __init__(
        self,
        queue: TaskQueue,
        config_path: str | None = None,
        templates_dir: str | None = None,
    ):
        self.queue = queue
        self.config_path = config_path or DEFAULT_SCHEDULES_PATH
        self.templates_dir = templates_dir or DEFAULT_TEMPLATES_DIR

        # Runtime changes are saved to .local.yaml to avoid polluting git-tracked config
        base, ext = os.path.splitext(self.config_path)
        self._local_path = f"{base}.local{ext}"

        self.schedules: list[Schedule] = []
        self._last_tick: float = 0
        self._tick_interval = 60  # Check every 60s (cron is minute-resolution)

        self._load_config()

    def _load_config(self):
        """Load schedule definitions from YAML.

        Loads the base config (git-tracked template), then merges with
        the local config (runtime overrides, gitignored). Local schedules
        override base schedules with the same ID.
        """
        base_items = self._load_yaml(self.config_path)
        local_items = self._load_yaml(self._local_path)

        # Merge: local overrides base by ID
        merged = {item["id"]: item for item in base_items}
        for item in local_items:
            merged[item["id"]] = item

        self.schedules = []
        for item in merged.values():
            try:
                sched = Schedule(
                    schedule_id=item["id"],
                    cron=item["cron"],
                    task_template=item["task_template"],
                    enabled=item.get("enabled", True),
                    priority=item.get("priority", 0),
                    description=item.get("description", ""),
                    params=item.get("params"),
                )
                self.schedules.append(sched)
                logger.info(
                    "Loaded schedule '%s': %s → %s",
                    sched.id, sched.cron_expr, sched.task_template,
                )
            except (KeyError, CronParseError) as e:
                logger.error("Invalid schedule definition %s: %s", item.get("id", "?"), e)

    @staticmethod
    def _load_yaml(path: str) -> list[dict]:
        """Load a schedules YAML file and return the list of schedule dicts."""
        if not os.path.isfile(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return data.get("schedules", [])
        except Exception as e:
            logger.error("Failed to load schedules from %s: %s", path, e)
            return []

    def reload(self):
        """Reload schedules from config file."""
        self._load_config()
        logger.info("Scheduler reloaded: %d schedules", len(self.schedules))

    def should_tick(self) -> bool:
        """Check if enough time has passed since last tick."""
        return time.time() - self._last_tick >= self._tick_interval

    def tick(self, project_path: str) -> list[int]:
        """Check all schedules and enqueue due tasks.

        Returns list of enqueued task IDs.
        """
        self._last_tick = time.time()
        now = datetime.now()
        enqueued = []

        for sched in self.schedules:
            if sched.is_due(now):
                try:
                    task_text = self._resolve_template(sched)
                    task_id = self.queue.enqueue(
                        task_text=task_text,
                        project_path=project_path,
                        priority=sched.priority,
                        task_type=TaskType.SCHEDULED,
                        metadata={
                            "schedule_id": sched.id,
                            "template": sched.task_template,
                        },
                    )
                    sched.last_run = time.time()
                    sched.run_count += 1
                    sched.last_error = None
                    enqueued.append(task_id)
                    logger.info(
                        "Schedule '%s' fired → task #%d", sched.id, task_id
                    )
                except Exception as e:
                    sched.last_error = str(e)
                    logger.error("Schedule '%s' failed to enqueue: %s", sched.id, e)

        return enqueued

    def _resolve_template(self, sched: Schedule) -> str:
        """Load and render a task template with parameters."""
        template_path = os.path.join(
            self.templates_dir, f"{sched.task_template}.md"
        )

        if os.path.isfile(template_path):
            with open(template_path, "r", encoding="utf-8") as f:
                template = f.read()

            # Simple {{param}} substitution
            for key, value in sched.params.items():
                template = template.replace(f"{{{{{key}}}}}", str(value))

            return template
        else:
            # No template file — use template name as task description
            task = f"[Scheduled: {sched.id}] {sched.task_template}"
            if sched.params:
                task += f" (params: {sched.params})"
            return task

    # ---- CRUD for schedules ----

    def get_schedule(self, schedule_id: str) -> Schedule | None:
        for s in self.schedules:
            if s.id == schedule_id:
                return s
        return None

    def add_schedule(
        self,
        schedule_id: str,
        cron: str,
        task_template: str,
        enabled: bool = True,
        priority: int = 0,
        description: str = "",
        params: dict | None = None,
    ) -> Schedule:
        """Add a new schedule at runtime and persist to config."""
        if self.get_schedule(schedule_id):
            raise ValueError(f"Schedule '{schedule_id}' already exists")

        sched = Schedule(
            schedule_id=schedule_id,
            cron=cron,
            task_template=task_template,
            enabled=enabled,
            priority=priority,
            description=description,
            params=params,
        )
        self.schedules.append(sched)
        self._save_config()
        return sched

    def update_schedule(self, schedule_id: str, **kwargs) -> Schedule | None:
        """Update an existing schedule."""
        sched = self.get_schedule(schedule_id)
        if not sched:
            return None

        if "cron" in kwargs:
            sched.cron_expr = kwargs["cron"]
            sched.cron = CronExpression(kwargs["cron"])
        if "task_template" in kwargs:
            sched.task_template = kwargs["task_template"]
        if "enabled" in kwargs:
            sched.enabled = kwargs["enabled"]
        if "priority" in kwargs:
            sched.priority = kwargs["priority"]
        if "description" in kwargs:
            sched.description = kwargs["description"]
        if "params" in kwargs:
            sched.params = kwargs["params"]

        self._save_config()
        return sched

    def delete_schedule(self, schedule_id: str) -> bool:
        """Delete a schedule."""
        sched = self.get_schedule(schedule_id)
        if not sched:
            return False
        self.schedules.remove(sched)
        self._save_config()
        return True

    def _save_config(self):
        """Persist current schedules to the local YAML config (gitignored).

        The base config (schedules.yaml) is never modified at runtime.
        All runtime changes go to schedules.local.yaml.
        """
        data = {
            "schedules": [
                {
                    "id": s.id,
                    "cron": s.cron_expr,
                    "task_template": s.task_template,
                    "enabled": s.enabled,
                    "priority": s.priority,
                    "description": s.description,
                    **({"params": s.params} if s.params else {}),
                }
                for s in self.schedules
            ]
        }

        os.makedirs(os.path.dirname(self._local_path), exist_ok=True)
        with open(self._local_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        logger.info("Saved %d schedules to %s", len(self.schedules), self._local_path)

    @property
    def status(self) -> dict:
        return {
            "total_schedules": len(self.schedules),
            "active_schedules": sum(1 for s in self.schedules if s.enabled),
            "schedules": [s.to_dict() for s in self.schedules],
            "last_tick": self._last_tick,
        }
