"""Factory for creating LLM providers."""

import logging

from orchestrator.providers.base import LLMProvider

logger = logging.getLogger(__name__)

# Provider type constants
OPENAI_COMPAT = "openai_compat"
ANTHROPIC = "anthropic"
GOOGLE = "google"

PROVIDER_TYPES = [OPENAI_COMPAT, ANTHROPIC, GOOGLE]


def create_provider(
    provider_type: str,
    base_url: str = "",
    api_key: str = "",
    model: str = "",
    **kwargs,
) -> LLMProvider:
    """
    Create an LLM provider instance.

    Args:
        provider_type: One of 'openai_compat', 'anthropic', 'google'.
        base_url: API base URL (used by openai_compat).
        api_key: API key (empty = use env var or 'not-needed' for local).
        model: Model name.
        **kwargs: Additional provider-specific args.

    Returns:
        Configured LLMProvider instance.
    """
    if provider_type == OPENAI_COMPAT:
        from orchestrator.providers.openai_compat import OpenAICompatProvider
        return OpenAICompatProvider(
            base_url=base_url or "http://localhost:1234/v1",
            api_key=api_key,
            model=model,
        )

    elif provider_type == ANTHROPIC:
        from orchestrator.providers.anthropic_provider import AnthropicProvider
        return AnthropicProvider(
            api_key=api_key,
            model=model or "claude-sonnet-4-6",
        )

    elif provider_type == GOOGLE:
        from orchestrator.providers.google_provider import GoogleProvider
        return GoogleProvider(
            api_key=api_key,
            model=model or "gemini-2.5-flash",
        )

    else:
        raise ValueError(
            f"Unknown provider type: {provider_type!r}. "
            f"Supported: {PROVIDER_TYPES}"
        )
