"""Google Gemini provider (using google-genai SDK)."""

import os
import json
import logging
import uuid

from orchestrator.providers.base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


def _clean_schema(schema: dict) -> dict:
    """Remove unsupported JSON Schema keys for Gemini."""
    cleaned = {}
    for k, v in schema.items():
        if k in ("additionalProperties",):
            continue
        if isinstance(v, dict):
            cleaned[k] = _clean_schema(v)
        elif isinstance(v, list):
            cleaned[k] = [_clean_schema(i) if isinstance(i, dict) else i for i in v]
        else:
            cleaned[k] = v
    return cleaned


def _openai_to_gemini_tools(tools: list[dict]) -> list:
    """Translate OpenAI function calling schemas to Gemini tool format."""
    from google.genai import types

    declarations = []
    for tool in tools:
        func = tool.get("function", {})
        params = func.get("parameters", {})
        cleaned = _clean_schema(params)

        declarations.append(types.FunctionDeclaration(
            name=func.get("name", ""),
            description=func.get("description", ""),
            parameters_json_schema=cleaned,
        ))

    return [types.Tool(function_declarations=declarations)]


def _openai_to_gemini_contents(messages: list[dict]) -> tuple[str, list]:
    """
    Translate OpenAI messages to Gemini content format.

    Returns:
        (system_instruction, contents) where contents is a list of
        types.Content objects for generate_content().
    """
    from google.genai import types

    system_instruction = ""
    contents = []

    for msg in messages:
        role = msg.get("role", "")

        if role == "system":
            system_instruction = msg.get("content", "")

        elif role == "user":
            content = msg.get("content", "")
            if content:
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=content)],
                ))

        elif role == "assistant":
            content = msg.get("content")
            tool_calls = msg.get("tool_calls")
            parts = []
            if content:
                parts.append(types.Part.from_text(text=content))
            if tool_calls:
                for tc in tool_calls:
                    func = tc.get("function", tc)
                    try:
                        args = json.loads(func.get("arguments", "{}"))
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                    parts.append(types.Part.from_function_call(
                        name=func.get("name", ""),
                        args=args,
                    ))
            if parts:
                contents.append(types.Content(role="model", parts=parts))

        elif role == "tool":
            tool_content = msg.get("content", "")
            tool_name = msg.get("name", "tool")
            try:
                result_data = json.loads(tool_content)
            except (json.JSONDecodeError, TypeError):
                result_data = {"result": tool_content}
            contents.append(types.Content(
                role="user",
                parts=[types.Part.from_function_response(
                    name=tool_name,
                    response=result_data,
                )],
            ))

    return system_instruction, contents


class GoogleProvider(LLMProvider):
    """Provider for Google Gemini models."""

    def __init__(self, api_key: str, model: str, **kwargs):
        try:
            from google import genai
            from google.genai import types  # noqa: F401
        except ImportError:
            raise ImportError(
                "google-genai package required. Install with: pip install google-genai"
            )

        self._api_key = api_key or os.environ.get("GOOGLE_API_KEY", "")
        if not self._api_key:
            raise ValueError("Google API key required (config or GOOGLE_API_KEY env var)")
        self._model = model
        self.client = genai.Client(api_key=self._api_key)

    @property
    def provider_name(self) -> str:
        return "Google Gemini"

    @property
    def model_name(self) -> str:
        return self._model

    def chat_completion(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> LLMResponse:
        from google.genai import types

        system_instruction, contents = _openai_to_gemini_contents(messages)

        config_args = {}
        if system_instruction:
            config_args["system_instruction"] = system_instruction

        temp = kwargs.get("temperature")
        if temp is not None:
            config_args["temperature"] = temp

        max_tokens = kwargs.get("max_tokens")
        if max_tokens:
            config_args["max_output_tokens"] = max_tokens

        if tools:
            config_args["tools"] = _openai_to_gemini_tools(tools)
            # Disable automatic function calling — we handle tool calls ourselves
            config_args["automatic_function_calling"] = (
                types.AutomaticFunctionCallingConfig(disable=True)
            )

        config = types.GenerateContentConfig(**config_args) if config_args else None

        try:
            response = self.client.models.generate_content(
                model=self._model,
                contents=contents,
                config=config,
            )
        except Exception as e:
            raise ConnectionError(f"Gemini API error: {e}") from e

        # Parse response
        content = None
        tool_calls = None

        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts:
                if part.text:
                    content = (content or "") + part.text
                elif part.function_call:
                    if tool_calls is None:
                        tool_calls = []
                    fc = part.function_call
                    tool_calls.append({
                        "id": f"call_{uuid.uuid4().hex[:12]}",
                        "name": fc.name,
                        "arguments": json.dumps(dict(fc.args)) if fc.args else "{}",
                    })

        # Token usage
        prompt_tokens = 0
        completion_tokens = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            meta = response.usage_metadata
            prompt_tokens = getattr(meta, "prompt_token_count", 0) or 0
            completion_tokens = getattr(meta, "candidates_token_count", 0) or 0

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    def test_connection(self) -> dict:
        try:
            models = []
            for m in self.client.models.list():
                name = m.name or ""
                # Strip "models/" prefix if present
                clean_name = name.replace("models/", "") if name.startswith("models/") else name
                if clean_name:
                    models.append(clean_name)
            return {"ok": True, "models": models}
        except Exception as e:
            logger.error("Google connection test failed: %s", e)
            return {"ok": False, "error": str(e)}

    def list_models(self) -> list[str]:
        result = self.test_connection()
        return result.get("models", []) if result.get("ok") else []
