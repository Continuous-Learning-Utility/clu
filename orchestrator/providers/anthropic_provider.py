"""Anthropic (Claude) provider."""

import os
import logging
import uuid

from orchestrator.providers.base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


def _openai_to_anthropic_tools(tools: list[dict]) -> list[dict]:
    """Translate OpenAI function calling schemas to Anthropic tool format."""
    result = []
    for tool in tools:
        func = tool.get("function", {})
        result.append({
            "name": func.get("name", ""),
            "description": func.get("description", ""),
            "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
        })
    return result


def _openai_to_anthropic_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    """
    Translate OpenAI message format to Anthropic format.

    Returns:
        (system_prompt, messages) where system is extracted separately.
    """
    system_prompt = ""
    anthropic_messages = []

    for msg in messages:
        role = msg.get("role", "")

        if role == "system":
            system_prompt = msg.get("content", "")
            continue

        if role == "assistant":
            content = msg.get("content")
            tool_calls = msg.get("tool_calls")

            if tool_calls:
                # Assistant message with tool use
                blocks = []
                if content:
                    blocks.append({"type": "text", "text": content})
                for tc in tool_calls:
                    func = tc.get("function", tc)
                    import json
                    try:
                        input_data = json.loads(func.get("arguments", "{}"))
                    except (json.JSONDecodeError, TypeError):
                        input_data = {}
                    blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", f"toolu_{uuid.uuid4().hex[:12]}"),
                        "name": func.get("name", ""),
                        "input": input_data,
                    })
                anthropic_messages.append({"role": "assistant", "content": blocks})
            elif content:
                anthropic_messages.append({"role": "assistant", "content": content})

        elif role == "tool":
            # Tool result → Anthropic tool_result block
            tool_call_id = msg.get("tool_call_id", "")
            content = msg.get("content", "")
            anthropic_messages.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "content": content,
                }],
            })

        elif role == "user":
            content = msg.get("content", "")
            if content:
                anthropic_messages.append({"role": "user", "content": content})

    # Anthropic requires alternating user/assistant messages.
    # Merge consecutive same-role messages.
    merged = []
    for m in anthropic_messages:
        if merged and merged[-1]["role"] == m["role"]:
            prev_content = merged[-1]["content"]
            curr_content = m["content"]
            # Normalize to list
            if isinstance(prev_content, str):
                prev_content = [{"type": "text", "text": prev_content}]
            if isinstance(curr_content, str):
                curr_content = [{"type": "text", "text": curr_content}]
            merged[-1]["content"] = prev_content + curr_content
        else:
            merged.append(m)

    return system_prompt, merged


class AnthropicProvider(LLMProvider):
    """Provider for Anthropic Claude models."""

    def __init__(self, api_key: str, model: str, **kwargs):
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "anthropic package required. Install with: pip install anthropic"
            )

        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not self._api_key:
            raise ValueError("Anthropic API key required (config or ANTHROPIC_API_KEY env var)")
        self._model = model
        self.client = anthropic.Anthropic(api_key=self._api_key)

    @property
    def provider_name(self) -> str:
        return "Anthropic"

    @property
    def model_name(self) -> str:
        return self._model

    def chat_completion(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> LLMResponse:
        system_prompt, anthropic_messages = _openai_to_anthropic_messages(messages)

        params = {
            "model": self._model,
            "messages": anthropic_messages,
            "max_tokens": kwargs.get("max_tokens", 4096),
        }

        if system_prompt:
            params["system"] = system_prompt

        if tools:
            params["tools"] = _openai_to_anthropic_tools(tools)

        temp = kwargs.get("temperature")
        if temp is not None:
            params["temperature"] = temp

        try:
            response = self.client.messages.create(**params)
        except Exception as e:
            raise ConnectionError(f"Anthropic API error: {e}") from e

        # Parse response
        content = None
        tool_calls = None

        for block in response.content:
            if block.type == "text":
                content = (content or "") + block.text
            elif block.type == "tool_use":
                if tool_calls is None:
                    tool_calls = []
                import json
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "arguments": json.dumps(block.input),
                })

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
        )

    def test_connection(self) -> dict:
        try:
            models = []
            page = self.client.models.list(limit=100)
            models.extend(m.id for m in page.data)
            while page.has_more:
                page = page.get_next_page()
                models.extend(m.id for m in page.data)
            return {"ok": True, "models": models}
        except Exception as e:
            logger.error("Anthropic connection test failed: %s", e)
            return {"ok": False, "error": str(e)}

    def list_models(self) -> list[str]:
        result = self.test_connection()
        return result.get("models", []) if result.get("ok") else []
