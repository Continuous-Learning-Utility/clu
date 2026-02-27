"""Abstract base class for all agent tools."""

from abc import ABC, abstractmethod


class BaseTool(ABC):
    """
    Base class for all tools exposed to the LLM.

    Each tool must define:
    - name: The function name used in tool calls.
    - description: Human-readable description for the LLM.
    - parameters_schema: JSON Schema for the tool's parameters.
    - execute(): The implementation.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name as used in OpenAI function calling."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Description shown to the LLM."""
        ...

    @property
    @abstractmethod
    def parameters_schema(self) -> dict:
        """JSON Schema for the tool's parameters."""
        ...

    @abstractmethod
    def execute(self, args: dict, project_path: str, sandbox, backup) -> dict:
        """
        Execute the tool.

        Args:
            args: Parsed JSON arguments from the LLM.
            project_path: Absolute path to the Unity project root.
            sandbox: PathValidator instance for path validation.
            backup: BackupManager instance for file backups.

        Returns:
            Dict with the tool result (will be JSON-serialized for the LLM).
        """
        ...

    def to_openai_schema(self) -> dict:
        """Return the tool definition in OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }
