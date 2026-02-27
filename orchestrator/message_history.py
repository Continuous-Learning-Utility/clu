"""Conversation history management with token-aware trimming."""


class MessageHistory:
    """
    Manages conversation history in OpenAI message format.

    When approaching the token limit, compresses older messages
    while keeping the system prompt and the last N exchanges intact.
    """

    def __init__(self, max_tokens: int = 32_000):
        self.max_tokens = max_tokens
        self._messages: list[dict] = []
        self._system: str | None = None

    @property
    def messages(self) -> list[dict]:
        """Return messages in OpenAI format."""
        result = []
        if self._system:
            result.append({"role": "system", "content": self._system})
        result.extend(self._messages)
        return result

    def set_system(self, content: str):
        self._system = content

    def add_user(self, content: str):
        self._messages.append({"role": "user", "content": content})
        self._maybe_trim()

    def add_assistant(self, content: str):
        self._messages.append({"role": "assistant", "content": content})

    def add_assistant_tool_call(self, content: str | None, tool_calls: list[dict]):
        """
        Add assistant message containing tool_calls.

        Args:
            content: Optional text content from the assistant.
            tool_calls: List of normalized dicts [{id, name, arguments}].
        """
        msg = {
            "role": "assistant",
            "content": content or "",
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments"],
                    },
                }
                for tc in tool_calls
            ],
        }
        self._messages.append(msg)

    def add_tool_result(self, tool_call_id: str, result: str):
        """Add a tool result message with smart truncation."""
        result = self._smart_truncate_result(result)

        self._messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result,
        })
        self._maybe_trim()

    def last_n_tool_calls(self, n: int) -> list[str]:
        """
        Return the last N tool call signatures (name + args) for loop detection.
        """
        calls = []
        for msg in reversed(self._messages):
            if msg.get("role") == "assistant" and "tool_calls" in msg:
                for tc in msg["tool_calls"]:
                    sig = f"{tc['function']['name']}:{tc['function']['arguments']}"
                    calls.append(sig)
                    if len(calls) >= n:
                        break
            if len(calls) >= n:
                break
        calls.reverse()
        return calls

    def last_n_tool_names(self, n: int) -> list[str]:
        """Return the last N tool call names (without args) for cycle detection."""
        names = []
        for msg in reversed(self._messages):
            if msg.get("role") == "assistant" and "tool_calls" in msg:
                for tc in msg["tool_calls"]:
                    names.append(tc["function"]["name"])
                    if len(names) >= n:
                        break
            if len(names) >= n:
                break
        names.reverse()
        return names

    def detect_loop(self) -> str | None:
        """
        Detect various loop patterns. Returns a description of the loop or None.

        Detects:
        1. Three identical tool calls (same name + args)
        2. Cyclic patterns (e.g., A-B-C-A-B-C) over last 12 calls
        3. Excessive reads without any writes (read-only spinning)
        """
        # 1. Three identical calls
        recent = self.last_n_tool_calls(3)
        if len(recent) >= 3 and recent[0] == recent[1] == recent[2]:
            return "identical_calls"

        # 2. Cycle detection: check if last 12 calls contain a repeating cycle
        sigs = self.last_n_tool_calls(12)
        if len(sigs) >= 6:
            # Try cycle lengths 2-6
            for cycle_len in range(2, 7):
                if len(sigs) >= cycle_len * 2:
                    tail = sigs[-cycle_len:]
                    prev = sigs[-cycle_len * 2 : -cycle_len]
                    if tail == prev:
                        return f"cycle_{cycle_len}"

        # 3. Read-only spinning: last 8+ tool calls are all read/list/search with no write
        names = self.last_n_tool_names(10)
        if len(names) >= 8:
            read_only = [n for n in names if n in ("read_file", "list_files", "search_in_files", "think")]
            if len(read_only) == len(names):
                return "read_only_spinning"

        return None

    def _maybe_trim(self):
        """
        If estimated token count exceeds 80% of max, compress older exchanges.
        Keeps: first user message (the task) + last 6 messages.
        Replaces the middle with a summary.
        """
        estimated = self._estimate_tokens()
        if estimated < self.max_tokens * 0.8:
            return
        if len(self._messages) <= 8:
            return

        keep_start = self._messages[:1]
        keep_end = self._messages[-6:]
        middle = self._messages[1:-6]

        summary = self._summarize_middle(middle)

        self._messages = keep_start + [
            {"role": "user", "content": f"[CONTEXT SUMMARY of prior work]\n{summary}"}
        ] + keep_end

    @staticmethod
    def _summarize_middle(messages: list[dict]) -> str:
        """Create a textual summary of tool calls and their results."""
        lines = []
        for msg in messages:
            if msg.get("role") == "assistant" and "tool_calls" in msg:
                for tc in msg["tool_calls"]:
                    args_preview = tc["function"]["arguments"][:100]
                    lines.append(f"- Called {tc['function']['name']}({args_preview})")
            elif msg.get("role") == "tool":
                content = msg.get("content", "")[:200]
                lines.append(f"  Result: {content}")
        return "\n".join(lines) if lines else "Previous exchanges trimmed."

    @staticmethod
    def _smart_truncate_result(result: str, max_chars: int = 8_000) -> str:
        """
        Truncate tool results intelligently:
        - For file contents: keep first and last portions
        - For search results: keep first N matches
        - General: hard cap with ellipsis
        """
        if len(result) <= max_chars:
            return result

        # Try to parse as JSON for smarter truncation
        try:
            import json
            data = json.loads(result)

            # File content: keep first 150 + last 50 lines
            if "content" in data and isinstance(data["content"], str):
                lines = data["content"].split("\n")
                if len(lines) > 200:
                    kept = lines[:150] + [f"\n... [{len(lines) - 200} lines omitted] ...\n"] + lines[-50:]
                    data["content"] = "\n".join(kept)
                    return json.dumps(data)

            # Search results: limit matches
            if "matches" in data and isinstance(data["matches"], list):
                if len(data["matches"]) > 10:
                    data["matches"] = data["matches"][:10]
                    data["truncated"] = True
                    return json.dumps(data)

            # File listing: limit entries
            if "files" in data and isinstance(data["files"], list):
                if len(data["files"]) > 50:
                    data["files"] = data["files"][:50]
                    data["truncated"] = True
                    return json.dumps(data)

            # Generic JSON: re-serialize (may be shorter)
            compact = json.dumps(data)
            if len(compact) <= max_chars:
                return compact

        except (json.JSONDecodeError, TypeError, KeyError):
            pass

        # Fallback: keep beginning + end
        half = max_chars // 2
        return result[:half] + f"\n... [{len(result) - max_chars} chars omitted] ...\n" + result[-half:]

    def _estimate_tokens(self) -> int:
        """Rough token estimate: ~4 chars per token."""
        total_chars = sum(len(str(m.get("content", ""))) for m in self.messages)
        return total_chars // 4
