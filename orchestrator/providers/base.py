"""Base classes for LLM providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class LLMResponse:
    """Normalized response from any LLM provider."""

    content: str | None = None
    tool_calls: list[dict] | None = None  # [{id, name, arguments}]
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class ToolCall:
    """Normalized tool call."""

    id: str
    name: str
    arguments: str  # JSON string


class LLMProvider(ABC):
    """Abstract base for all LLM providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name (e.g. 'OpenAI', 'Anthropic')."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Currently configured model name."""
        ...

    @abstractmethod
    def chat_completion(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        **kwargs,
    ) -> LLMResponse:
        """
        Send a chat completion request.

        Args:
            messages: Conversation in OpenAI format [{role, content, ...}].
            tools: Tool schemas in OpenAI function calling format.
            **kwargs: Provider-specific params (temperature, seed, max_tokens).

        Returns:
            Normalized LLMResponse.
        """
        ...

    @abstractmethod
    def test_connection(self) -> dict:
        """
        Test provider connectivity.

        Returns:
            {"ok": bool, "models": list[str] | None, "error": str | None}
        """
        ...

    def list_models(self) -> list[str]:
        """List available models. Default: return empty list."""
        result = self.test_connection()
        return result.get("models", []) if result.get("ok") else []
