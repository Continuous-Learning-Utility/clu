"""Tests for the LLM provider abstraction layer."""

import os
import sys
import json
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from orchestrator.providers.base import LLMResponse, LLMProvider
from orchestrator.providers.factory import create_provider, PROVIDER_TYPES


class TestLLMResponse:

    def test_defaults(self):
        r = LLMResponse()
        assert r.content is None
        assert r.tool_calls is None
        assert r.prompt_tokens == 0
        assert r.completion_tokens == 0

    def test_with_content(self):
        r = LLMResponse(content="hello", prompt_tokens=100, completion_tokens=50)
        assert r.content == "hello"
        assert r.prompt_tokens == 100
        assert r.completion_tokens == 50

    def test_with_tool_calls(self):
        tc = [{"id": "call_1", "name": "read_file", "arguments": '{"path": "test.cs"}'}]
        r = LLMResponse(tool_calls=tc)
        assert r.tool_calls is not None
        assert len(r.tool_calls) == 1
        assert r.tool_calls[0]["name"] == "read_file"


class TestFactory:

    def test_known_types(self):
        assert "openai_compat" in PROVIDER_TYPES
        assert "anthropic" in PROVIDER_TYPES
        assert "google" in PROVIDER_TYPES

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown provider type"):
            create_provider("nonexistent", model="test")

    def test_create_openai_compat(self):
        provider = create_provider(
            "openai_compat",
            base_url="http://localhost:1234/v1",
            api_key="",
            model="test-model",
        )
        assert provider.provider_name == "OpenAI-compatible"
        assert provider.model_name == "test-model"


class TestOpenAICompatProvider:

    def test_provider_name(self):
        provider = create_provider("openai_compat", base_url="http://localhost:1234/v1", model="test")
        assert provider.provider_name == "OpenAI-compatible"

    def test_model_name(self):
        provider = create_provider("openai_compat", base_url="http://localhost:1234/v1", model="qwen/qwen3")
        assert provider.model_name == "qwen/qwen3"

    @patch("orchestrator.providers.openai_compat.openai.OpenAI")
    def test_chat_completion_no_tools(self, mock_openai_cls):
        """Test chat completion returns normalized LLMResponse."""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_message = MagicMock()
        mock_message.content = "Hello world"
        mock_message.tool_calls = None

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 100
        mock_usage.completion_tokens = 20

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=mock_message)]
        mock_response.usage = mock_usage

        mock_client.chat.completions.create.return_value = mock_response

        from orchestrator.providers.openai_compat import OpenAICompatProvider
        provider = OpenAICompatProvider("http://localhost:1234/v1", "test-key", "test-model")

        result = provider.chat_completion(
            messages=[{"role": "user", "content": "hi"}],
        )

        assert isinstance(result, LLMResponse)
        assert result.content == "Hello world"
        assert result.tool_calls is None
        assert result.prompt_tokens == 100
        assert result.completion_tokens == 20

    @patch("orchestrator.providers.openai_compat.openai.OpenAI")
    def test_chat_completion_with_tools(self, mock_openai_cls):
        """Test that tool calls are properly normalized."""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_tc = MagicMock()
        mock_tc.id = "call_abc"
        mock_tc.function.name = "read_file"
        mock_tc.function.arguments = '{"path": "test.cs"}'

        mock_message = MagicMock()
        mock_message.content = None
        mock_message.tool_calls = [mock_tc]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=mock_message)]
        mock_response.usage = MagicMock(prompt_tokens=50, completion_tokens=10)

        mock_client.chat.completions.create.return_value = mock_response

        from orchestrator.providers.openai_compat import OpenAICompatProvider
        provider = OpenAICompatProvider("http://localhost:1234/v1", "", "test-model")

        result = provider.chat_completion(
            messages=[{"role": "user", "content": "test"}],
            tools=[{"type": "function", "function": {"name": "read_file"}}],
        )

        assert result.tool_calls is not None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["id"] == "call_abc"
        assert result.tool_calls[0]["name"] == "read_file"
        assert result.tool_calls[0]["arguments"] == '{"path": "test.cs"}'

    @patch("orchestrator.providers.openai_compat.openai.OpenAI")
    def test_test_connection(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_model = MagicMock()
        mock_model.id = "test-model"
        mock_client.models.list.return_value = MagicMock(data=[mock_model])

        from orchestrator.providers.openai_compat import OpenAICompatProvider
        provider = OpenAICompatProvider("http://localhost:1234/v1", "", "test-model")

        result = provider.test_connection()
        assert result["ok"] is True
        assert "test-model" in result["models"]


class TestMessageHistoryCompatibility:
    """Ensure the new add_assistant_tool_call signature works."""

    def test_new_signature(self):
        from orchestrator.message_history import MessageHistory
        h = MessageHistory()
        h.set_system("system")
        h.add_user("task")

        # New signature: (content, tool_calls_list_of_dicts)
        h.add_assistant_tool_call(
            "thinking...",
            [{"id": "call_1", "name": "read_file", "arguments": '{"path": "test.cs"}'}]
        )

        msgs = h.messages
        assert len(msgs) == 3  # system, user, assistant
        assistant_msg = msgs[2]
        assert assistant_msg["role"] == "assistant"
        assert assistant_msg["content"] == "thinking..."
        assert len(assistant_msg["tool_calls"]) == 1
        tc = assistant_msg["tool_calls"][0]
        assert tc["id"] == "call_1"
        assert tc["function"]["name"] == "read_file"
        assert tc["function"]["arguments"] == '{"path": "test.cs"}'


class TestToolDispatcherCompat:
    """Ensure tool dispatcher works with dict tool calls."""

    def test_dispatch_dict_format(self):
        from orchestrator.tool_dispatcher import ToolDispatcher

        mock_registry = MagicMock()
        mock_tool = MagicMock()
        mock_tool.execute.return_value = {"status": "ok"}
        mock_registry.get.return_value = mock_tool

        dispatcher = ToolDispatcher(mock_registry, MagicMock(), MagicMock())

        tool_call = {
            "id": "call_1",
            "name": "think",
            "arguments": '{"reasoning": "test"}',
        }

        result = dispatcher.dispatch(tool_call, "/project")
        assert "ok" in result
        mock_registry.get.assert_called_with("think")
