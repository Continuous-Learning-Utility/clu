"""Budget tracking: iteration count and token usage."""


class BudgetTracker:
    """
    Tracks iteration count and token usage with limits.

    IMPORTANT: We track completion_tokens only (actual LLM output),
    NOT total_tokens which includes prompt re-sent every turn.
    This prevents the budget from being consumed by context re-sending.
    """

    def __init__(
        self,
        max_iterations: int = 50,
        max_total_tokens: int = 500_000,
        max_context_tokens: int = 32_000,
    ):
        self.max_iterations = max_iterations
        self.max_total_tokens = max_total_tokens
        self.max_context_tokens = max_context_tokens
        self.iteration = 0
        self.total_tokens = 0          # cumulative completion tokens
        self.prompt_tokens_last = 0    # prompt tokens of the last call (for context tracking)
        self.total_prompt_tokens = 0   # informational only

    @property
    def exhausted(self) -> bool:
        return (
            self.iteration >= self.max_iterations
            or self.total_tokens >= self.max_total_tokens
        )

    @property
    def warning_zone(self) -> bool:
        """True if we're at 80% of any limit."""
        return (
            self.iteration >= self.max_iterations * 0.8
            or self.total_tokens >= self.max_total_tokens * 0.8
        )

    def tick(self):
        self.iteration += 1

    def add_usage(self, prompt_tokens: int, completion_tokens: int):
        """
        Record token usage from a single API call.

        Only completion_tokens count toward the budget limit.
        Prompt tokens are tracked for context window monitoring.
        """
        self.total_tokens += completion_tokens
        self.prompt_tokens_last = prompt_tokens
        self.total_prompt_tokens += prompt_tokens

    @property
    def context_usage_pct(self) -> float:
        """How full is the context window based on last prompt size."""
        if self.max_context_tokens <= 0:
            return 0
        return (self.prompt_tokens_last / self.max_context_tokens) * 100

    def status(self) -> dict:
        return {
            "iteration": f"{self.iteration}/{self.max_iterations}",
            "completion_tokens": f"{self.total_tokens}/{self.max_total_tokens}",
            "context_usage": f"{self.prompt_tokens_last}/{self.max_context_tokens} ({self.context_usage_pct:.0f}%)",
            "remaining_iterations": self.max_iterations - self.iteration,
            "remaining_tokens": self.max_total_tokens - self.total_tokens,
        }
