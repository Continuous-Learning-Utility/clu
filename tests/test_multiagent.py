"""Tests for orchestrator/decomposer.py, tools/delegate_tool.py, and role integration."""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from orchestrator.decomposer import TaskDecomposer, SubTask, DECOMPOSE_PROMPT
from orchestrator.providers.base import LLMProvider, LLMResponse
from tools.delegate_tool import DelegateTool
from daemon.task_queue import TaskQueue


# ---- Mock provider ----

class MockDecomposeProvider(LLMProvider):
    """Provider that returns a pre-set JSON response for decomposition."""

    def __init__(self, response_json: str):
        self._response = response_json

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-model"

    def chat_completion(self, messages, tools=None, **kwargs) -> LLMResponse:
        return LLMResponse(content=self._response, prompt_tokens=100, completion_tokens=50)

    def test_connection(self) -> dict:
        return {"ok": True}


class FailingProvider(LLMProvider):
    @property
    def provider_name(self) -> str:
        return "failing"

    @property
    def model_name(self) -> str:
        return "fail"

    def chat_completion(self, messages, tools=None, **kwargs) -> LLMResponse:
        raise ConnectionError("LLM down")

    def test_connection(self) -> dict:
        return {"ok": False}


# ---- TaskDecomposer ----

class TestTaskDecomposer(unittest.TestCase):

    def test_decompose_simple_response(self):
        response = json.dumps([
            {"title": "Read files", "description": "Read the target files", "role": "coder", "priority": 10},
            {"title": "Review code", "description": "Review for issues", "role": "reviewer", "priority": 5},
        ])
        provider = MockDecomposeProvider(response)
        decomposer = TaskDecomposer(provider)
        result = decomposer.decompose("Refactor PlayerController")

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].title, "Read files")
        self.assertEqual(result[0].role, "coder")
        self.assertEqual(result[1].role, "reviewer")
        self.assertEqual(result[1].priority, 5)

    def test_decompose_with_markdown_code_block(self):
        response = '```json\n[{"title": "Fix bug", "description": "Fix it", "role": "coder", "priority": 10}]\n```'
        provider = MockDecomposeProvider(response)
        decomposer = TaskDecomposer(provider)
        result = decomposer.decompose("Fix a bug")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].title, "Fix bug")

    def test_decompose_invalid_json_fallback(self):
        provider = MockDecomposeProvider("This is not JSON at all")
        decomposer = TaskDecomposer(provider)
        result = decomposer.decompose("Do something complex")

        # Should fallback to single task
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].role, "coder")
        self.assertIn("Do something complex", result[0].description)

    def test_decompose_empty_array_fallback(self):
        provider = MockDecomposeProvider("[]")
        decomposer = TaskDecomposer(provider)
        result = decomposer.decompose("Empty task")

        self.assertEqual(len(result), 1)

    def test_decompose_invalid_role_corrected(self):
        response = json.dumps([
            {"title": "Task", "description": "Do it", "role": "hacker", "priority": 10},
        ])
        provider = MockDecomposeProvider(response)
        decomposer = TaskDecomposer(provider)
        result = decomposer.decompose("Task")

        self.assertEqual(result[0].role, "coder")  # Invalid role → coder

    def test_decompose_llm_failure_fallback(self):
        provider = FailingProvider()
        decomposer = TaskDecomposer(provider)
        result = decomposer.decompose("Task when LLM is down")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].role, "coder")

    def test_decompose_all_roles(self):
        response = json.dumps([
            {"title": "Implement", "description": "Write code", "role": "coder", "priority": 20},
            {"title": "Write tests", "description": "Test it", "role": "tester", "priority": 10},
            {"title": "Review", "description": "Check quality", "role": "reviewer", "priority": 5},
        ])
        provider = MockDecomposeProvider(response)
        decomposer = TaskDecomposer(provider)
        result = decomposer.decompose("Full workflow")

        roles = [s.role for s in result]
        self.assertEqual(roles, ["coder", "tester", "reviewer"])

    def test_subtask_dataclass(self):
        st = SubTask(title="Test", description="Test desc", role="tester", priority=15)
        self.assertEqual(st.title, "Test")
        self.assertEqual(st.depends_on, [])


# ---- DelegateTool ----

class TestDelegateTool(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "tasks.db")
        self.queue = TaskQueue(db_path=self.db_path)
        self.tool = DelegateTool()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_tool_name(self):
        self.assertEqual(self.tool.name, "delegate")

    def test_tool_schema(self):
        schema = self.tool.to_openai_schema()
        self.assertEqual(schema["function"]["name"], "delegate")
        params = schema["function"]["parameters"]["properties"]
        self.assertIn("task", params)
        self.assertIn("role", params)

    def test_delegate_without_queue(self):
        """Without a queue, delegation should return an error."""
        result = self.tool.execute(
            {"task": "Fix bug", "role": "coder"},
            "/project", None, None,
        )
        self.assertIn("error", result)
        self.assertIn("not available", result["error"])

    def test_delegate_with_queue(self):
        self.tool._queue = self.queue
        result = self.tool.execute(
            {"task": "Fix the null reference bug", "role": "coder", "priority": 15},
            "/fake/project", None, None,
        )
        self.assertTrue(result["ok"])
        self.assertIn("task_id", result)
        self.assertEqual(result["role"], "coder")

        # Verify task is in queue
        tasks = self.queue.list_tasks()
        self.assertEqual(len(tasks), 1)
        self.assertIn("[Role: coder]", tasks[0].payload.get("task", ""))
        self.assertEqual(tasks[0].priority, 15)
        self.assertTrue(tasks[0].metadata.get("delegated"))

    def test_delegate_with_context(self):
        self.tool._queue = self.queue
        result = self.tool.execute(
            {"task": "Review code", "role": "reviewer",
             "context": "Focus on PlayerController.cs"},
            "/fake/project", None, None,
        )
        self.assertTrue(result["ok"])

        task = self.queue.get(result["task_id"])
        self.assertIn("PlayerController.cs", task.payload.get("task", ""))

    def test_delegate_empty_task(self):
        self.tool._queue = self.queue
        result = self.tool.execute(
            {"task": "", "role": "coder"},
            "/project", None, None,
        )
        self.assertIn("error", result)

    def test_delegate_invalid_role(self):
        self.tool._queue = self.queue
        result = self.tool.execute(
            {"task": "Do something", "role": "admin"},
            "/project", None, None,
        )
        self.assertIn("error", result)

    def test_delegate_role_in_metadata(self):
        self.tool._queue = self.queue
        self.tool.execute(
            {"task": "Write tests", "role": "tester"},
            "/fake/project", None, None,
        )
        tasks = self.queue.list_tasks()
        self.assertEqual(tasks[0].metadata.get("role"), "tester")


# ---- Role integration ----

class TestRoleTools(unittest.TestCase):
    """Test that role-specific tool restrictions work correctly."""

    def test_role_tools_mapping(self):
        from orchestrator.runner import AgentRunner
        # Coder has all tools (None = no restriction)
        self.assertIsNone(AgentRunner.ROLE_TOOLS["coder"])

        # Reviewer cannot write
        reviewer_tools = AgentRunner.ROLE_TOOLS["reviewer"]
        self.assertNotIn("write_file", reviewer_tools)
        self.assertNotIn("validate_csharp", reviewer_tools)
        self.assertIn("read_file", reviewer_tools)
        self.assertIn("think", reviewer_tools)

        # Tester can write (for test files) but has restricted scope via prompt
        tester_tools = AgentRunner.ROLE_TOOLS["tester"]
        self.assertIn("write_file", tester_tools)
        self.assertIn("read_file", tester_tools)

    def test_role_prompts_exist(self):
        roles_dir = os.path.join(os.path.dirname(__file__), "..", "prompts", "roles")
        for role in ["coder", "reviewer", "tester"]:
            path = os.path.join(roles_dir, f"{role}.md")
            self.assertTrue(os.path.isfile(path), f"Missing role prompt: {path}")

            with open(path, "r") as f:
                content = f.read()
            self.assertIn(f"Role: {role.capitalize()}", content)


if __name__ == "__main__":
    unittest.main()
