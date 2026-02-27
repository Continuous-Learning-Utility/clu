"""DelegateTool: allows the agent to enqueue sub-tasks for other agent roles.

The running agent can delegate work to specialized roles (coder, reviewer, tester)
by enqueuing sub-tasks in the task queue.
"""

from tools.base import BaseTool


class DelegateTool(BaseTool):
    """Tool that lets the agent delegate sub-tasks to specialized agent roles."""

    def __init__(self):
        self._queue = None  # Set externally by runner/dispatcher

    @property
    def name(self) -> str:
        return "delegate"

    @property
    def description(self) -> str:
        return (
            "Delegate a sub-task to a specialized agent role. "
            "The sub-task will be enqueued and executed by an agent with the specified role. "
            "Roles: 'coder' (full read/write), 'reviewer' (read-only, produces report), "
            "'tester' (writes test files only). "
            "Use this when a task is too complex to do alone or requires a different specialization."
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Detailed description of the sub-task to delegate.",
                },
                "role": {
                    "type": "string",
                    "enum": ["coder", "reviewer", "tester"],
                    "description": "The agent role to delegate to.",
                },
                "priority": {
                    "type": "integer",
                    "description": "Priority (higher = more important). Default: 10.",
                    "default": 10,
                },
                "context": {
                    "type": "string",
                    "description": "Additional context for the sub-task (file paths, findings, etc.).",
                },
            },
            "required": ["task", "role"],
        }

    def execute(self, args: dict, project_path: str, sandbox, backup) -> dict:
        task = args.get("task", "")
        role = args.get("role", "coder")
        priority = args.get("priority", 10)
        context = args.get("context", "")

        if not task:
            return {"error": "Task description is required"}

        if role not in ("coder", "reviewer", "tester"):
            return {"error": f"Invalid role '{role}'. Must be: coder, reviewer, tester"}

        if not self._queue:
            return {
                "error": "Task queue not available. Delegation requires the daemon to be running.",
                "hint": "Describe what you need done and the user can run it manually.",
            }

        # Build the full task text with role prefix
        full_task = f"[Role: {role}] {task}"
        if context:
            full_task += f"\n\nContext:\n{context}"

        try:
            task_id = self._queue.enqueue(
                task_text=full_task,
                project_path=project_path,
                priority=priority,
                task_type="manual",
                metadata={
                    "role": role,
                    "delegated": True,
                    "parent_context": "agent_delegation",
                },
            )
            return {
                "ok": True,
                "task_id": task_id,
                "role": role,
                "message": f"Sub-task delegated to '{role}' agent (task #{task_id}). "
                           f"It will be executed when the daemon processes it.",
            }
        except Exception as e:
            return {"error": f"Failed to enqueue sub-task: {e}"}
