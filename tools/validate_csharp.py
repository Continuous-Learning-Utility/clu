"""validate_csharp tool: validates C# syntax via dotnet build."""

from tools.base import BaseTool


class ValidateCSharpTool(BaseTool):

    _validator = None

    @property
    def name(self) -> str:
        return "validate_csharp"

    @property
    def description(self) -> str:
        return (
            "Validate C# code for syntax and type errors using the Unity project's DLL references. "
            "Returns validation results with any errors found."
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "C# source code to validate.",
                },
            },
            "required": ["code"],
        }

    def execute(self, args: dict, project_path: str, sandbox, backup) -> dict:
        code = args.get("code", "")

        if not code.strip():
            return {"error": "Empty code provided"}

        from validation.csharp_validator import CSharpValidator

        if ValidateCSharpTool._validator is None:
            ValidateCSharpTool._validator = CSharpValidator(
                unity_dll_path="C:/Program Files/Unity/Hub/Editor/6000.0.58f2/Editor/Data/Managed/UnityEngine",
            )

        return ValidateCSharpTool._validator.validate(code, project_path)
