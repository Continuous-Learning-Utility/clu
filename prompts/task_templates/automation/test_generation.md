## Automated Task: Generate Tests

You are running as an automated scheduled task. Generate unit tests for classes that lack test coverage.

Steps:
1. Use `search` and `list_files` to find testable source files
2. Check if corresponding test files exist
3. For classes without tests, generate test files:
   - Test public method behavior
   - Test edge cases (null inputs, boundary values)
   - Test expected exceptions
   - Mock dependencies where possible
4. Save test files following the project's test naming convention
5. Log what you generated using the `memory` tool (action: "log")

Important:
- Only generate tests for logic-heavy classes
- Follow existing test patterns if any tests already exist
- Don't test trivial getters/setters
- Use the project's testing framework conventions
