"""Agent event types for streaming progress from AgentRunner."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentEvent:
    """Base event emitted by AgentRunner during execution."""
    type: str
    data: dict = field(default_factory=dict)


def agent_start(task: str, project: str, session_id: str,
                max_iterations: int, provider: str, model: str) -> AgentEvent:
    return AgentEvent("agent_start", {
        "task": task, "project": project, "session_id": session_id,
        "max_iterations": max_iterations, "provider": provider, "model": model,
    })


def iteration(current: int, max_iter: int, tokens: int, max_tokens: int) -> AgentEvent:
    return AgentEvent("iteration", {
        "current": current, "max": max_iter,
        "tokens": tokens, "max_tokens": max_tokens,
    })


def tool_call(name: str, arguments: Any) -> AgentEvent:
    return AgentEvent("tool_call", {"name": name, "arguments": arguments})


def tool_result(name: str, result: Any) -> AgentEvent:
    return AgentEvent("tool_result", {"name": name, "result": result})


def agent_response(content: str) -> AgentEvent:
    return AgentEvent("agent_response", {"content": content})


def agent_done(success: bool, session_id: str, iterations: int, tokens: int,
               files_modified: list[str], error: str | None = None) -> AgentEvent:
    return AgentEvent("agent_done", {
        "success": success, "session_id": session_id,
        "iterations": iterations, "tokens": tokens,
        "files_modified": files_modified, "error": error,
    })


def warning(message: str) -> AgentEvent:
    return AgentEvent("warning", {"message": message})


def error(message: str) -> AgentEvent:
    return AgentEvent("error", {"message": message})


def info(message: str) -> AgentEvent:
    return AgentEvent("info", {"message": message})
