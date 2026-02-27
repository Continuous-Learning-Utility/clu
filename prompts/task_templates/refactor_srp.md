## Task: Refactor for Single Responsibility Principle

Target file: {{file_path}}

Analyze the target file and identify SRP violations. For each violation:
1. Read the current file
2. Search for all references to the class across the project
3. Extract each additional responsibility into its own class
4. Update the original class to use composition
5. Update all references to use the new structure
6. Validate all modified files compile correctly

Do NOT change any public API signatures unless absolutely necessary.
Preserve all existing behavior.
