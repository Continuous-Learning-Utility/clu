"""think tool: forces the LLM to plan before acting."""

from tools.base import BaseTool


class ThinkTool(BaseTool):
    """
    A no-op tool that forces the LLM to articulate its reasoning.

    This is critical for models like Qwen Coder that tend to
    chain tool calls mechanically without planning. By requiring
    a think() call before each action, the agent is forced to:
    - Track what it has done
    - Plan its next step
    - Avoid repeating actions
    """

    @property
    def name(self) -> str:
        return "think"

    @property
    def description(self) -> str:
        return (
            "Plan your next action. You MUST call this before every other tool. "
            "State what you know, what remains to do, and what your next action is. "
            "This helps you avoid loops and track progress."
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "reasoning": {
                    "type": "string",
                    "description": (
                        "Your step-by-step reasoning: "
                        "1) What have I done so far? "
                        "2) What do I still need to do? "
                        "3) What is my next concrete action and why?"
                    ),
                },
            },
            "required": ["reasoning"],
        }

    def execute(self, args: dict, project_path: str, sandbox, backup) -> dict:
        reasoning = args.get("reasoning", "")
        # No-op: the value is in forcing the LLM to articulate
        return {
            "status": "ok",
            "note": "Continue with your planned action.",
        }
