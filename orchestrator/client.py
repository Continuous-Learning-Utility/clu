"""LM Studio client wrapper using the OpenAI-compatible API."""

import time
import logging

import openai

from orchestrator.exceptions import LMStudioError

logger = logging.getLogger(__name__)


class LMStudioClient:
    """
    Thin wrapper around openai.OpenAI targeting LM Studio.

    CRITICAL: stream MUST be False for tool calling to work with LM Studio.
    """

    def __init__(self, api_base: str, model: str):
        self.client = openai.OpenAI(
            base_url=api_base,
            api_key="not-needed",
        )
        self.model = model

    def chat_completion(self, messages: list, tools: list | None = None, **kwargs):
        """
        Call chat completions with retry logic.

        Args:
            messages: Conversation history in OpenAI format.
            tools: Tool definitions in OpenAI function calling format.
            **kwargs: Additional parameters (temperature, seed, max_tokens, etc.)

        Returns:
            The ChatCompletion response object.

        Raises:
            LMStudioError: If LM Studio is unreachable after 3 attempts.
        """
        max_retries = 3

        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=tools if tools else openai.NOT_GIVEN,
                    stream=False,
                    **kwargs,
                )
                return response

            except openai.APIConnectionError as e:
                logger.warning(
                    "LM Studio connection failed (attempt %d/%d): %s",
                    attempt + 1, max_retries, e,
                )
                if attempt == max_retries - 1:
                    raise LMStudioError(
                        f"LM Studio unreachable after {max_retries} attempts: {e}"
                    ) from e
                time.sleep(2 ** attempt)

            except openai.APIStatusError as e:
                logger.warning(
                    "LM Studio API error (attempt %d/%d): %s",
                    attempt + 1, max_retries, e,
                )
                if attempt == max_retries - 1:
                    raise LMStudioError(
                        f"LM Studio API error after {max_retries} attempts: {e}"
                    ) from e
                time.sleep(2 ** attempt)

    def test_connection(self) -> bool:
        """Test if LM Studio is reachable and the model is loaded."""
        try:
            models = self.client.models.list()
            available = [m.id for m in models.data]
            logger.info("LM Studio models available: %s", available)
            return len(available) > 0
        except Exception as e:
            logger.error("LM Studio connection test failed: %s", e)
            return False
