"""Tests for the agent loop components."""

import os
import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from orchestrator.budget import BudgetTracker
from orchestrator.message_history import MessageHistory


class TestBudgetTracker:

    def test_initial_state(self):
        b = BudgetTracker(max_iterations=10, max_total_tokens=1000)
        assert not b.exhausted
        assert b.iteration == 0
        assert b.total_tokens == 0

    def test_iteration_exhaustion(self):
        b = BudgetTracker(max_iterations=3, max_total_tokens=100_000)
        b.tick()
        b.tick()
        b.tick()
        assert b.exhausted

    def test_token_exhaustion(self):
        b = BudgetTracker(max_iterations=100, max_total_tokens=1000)
        b.add_usage(prompt_tokens=500, completion_tokens=1000)
        assert b.exhausted

    def test_only_completion_tokens_count(self):
        """Prompt tokens should NOT count toward budget limit."""
        b = BudgetTracker(max_iterations=100, max_total_tokens=1000)
        # Simulate 10 turns with big prompts but small completions
        for _ in range(10):
            b.add_usage(prompt_tokens=5000, completion_tokens=50)
        # 10 * 50 = 500 completion tokens < 1000 limit
        assert not b.exhausted
        assert b.total_tokens == 500
        assert b.total_prompt_tokens == 50_000

    def test_warning_zone_at_80_percent(self):
        b = BudgetTracker(max_iterations=10, max_total_tokens=100_000)
        for _ in range(8):
            b.tick()
        assert b.warning_zone

    def test_status(self):
        b = BudgetTracker(max_iterations=30, max_total_tokens=100_000)
        b.tick()
        b.add_usage(prompt_tokens=3000, completion_tokens=5000)
        status = b.status()
        assert status["iteration"] == "1/30"
        assert status["remaining_iterations"] == 29
        assert status["remaining_tokens"] == 95_000


class TestMessageHistory:

    def test_basic_messages(self):
        h = MessageHistory(max_tokens=100_000)
        h.set_system("You are a bot.")
        h.add_user("Hello")
        h.add_assistant("Hi there!")

        msgs = h.messages
        assert len(msgs) == 3
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert msgs[2]["role"] == "assistant"

    def test_tool_result_truncation(self):
        h = MessageHistory(max_tokens=100_000)
        h.set_system("system")
        h.add_user("task")

        # Very large result
        large_result = "x" * 20_000
        h.add_tool_result("call_1", large_result)

        tool_msg = [m for m in h.messages if m["role"] == "tool"][0]
        assert len(tool_msg["content"]) < 16_000

    def test_loop_detection(self):
        h = MessageHistory()
        h.set_system("system")
        h.add_user("task")

        # Simulate 3 identical tool calls
        for _ in range(3):
            h._messages.append({
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path": "Assets/Scripts/Test.cs"}',
                    },
                }],
            })
            h._messages.append({
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "file content",
            })

        calls = h.last_n_tool_calls(3)
        assert len(calls) == 3
        assert calls[0] == calls[1] == calls[2]

    def test_detect_loop_identical(self):
        """detect_loop catches 3 identical calls."""
        h = MessageHistory()
        h.set_system("system")
        h.add_user("task")

        for _ in range(3):
            h._messages.append({
                "role": "assistant", "content": "",
                "tool_calls": [{"id": "c1", "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "A.cs"}'}}],
            })
            h._messages.append({"role": "tool", "tool_call_id": "c1", "content": "ok"})

        assert h.detect_loop() == "identical_calls"

    def test_detect_loop_cycle(self):
        """detect_loop catches repeating cycles like A-B-A-B."""
        h = MessageHistory()
        h.set_system("system")
        h.add_user("task")

        # Create A-B-A-B-A-B pattern (cycle of 2, repeated 3 times)
        for _ in range(3):
            h._messages.append({
                "role": "assistant", "content": "",
                "tool_calls": [{"id": "c1", "type": "function",
                    "function": {"name": "list_files", "arguments": '{"path": "Assets/"}'}}],
            })
            h._messages.append({"role": "tool", "tool_call_id": "c1", "content": "ok"})
            h._messages.append({
                "role": "assistant", "content": "",
                "tool_calls": [{"id": "c2", "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "A.cs"}'}}],
            })
            h._messages.append({"role": "tool", "tool_call_id": "c2", "content": "ok"})

        result = h.detect_loop()
        assert result is not None
        assert "cycle" in result

    def test_detect_loop_read_only_spinning(self):
        """detect_loop catches read-only spinning (no writes)."""
        h = MessageHistory()
        h.set_system("system")
        h.add_user("task")

        tools = ["think", "list_files", "read_file", "search_in_files",
                 "think", "read_file", "think", "list_files", "read_file", "think"]
        for i, name in enumerate(tools):
            h._messages.append({
                "role": "assistant", "content": "",
                "tool_calls": [{"id": f"c{i}", "type": "function",
                    "function": {"name": name, "arguments": f'{{"x": {i}}}'}}],
            })
            h._messages.append({"role": "tool", "tool_call_id": f"c{i}", "content": "ok"})

        assert h.detect_loop() == "read_only_spinning"

    def test_detect_loop_no_loop(self):
        """detect_loop returns None when there is no loop."""
        h = MessageHistory()
        h.set_system("system")
        h.add_user("task")

        # A productive sequence: think, list, read, think, write
        tools = [
            ("think", '{"reasoning": "planning"}'),
            ("list_files", '{"path": "Assets/"}'),
            ("read_file", '{"path": "A.cs"}'),
            ("think", '{"reasoning": "now write"}'),
            ("write_file", '{"path": "A.cs", "content": "code"}'),
        ]
        for i, (name, args) in enumerate(tools):
            h._messages.append({
                "role": "assistant", "content": "",
                "tool_calls": [{"id": f"c{i}", "type": "function",
                    "function": {"name": name, "arguments": args}}],
            })
            h._messages.append({"role": "tool", "tool_call_id": f"c{i}", "content": "ok"})

        assert h.detect_loop() is None
