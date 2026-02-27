## Automated Task: Code Review

You are running as an automated scheduled task. Review recently modified source files for potential issues.

Steps:
1. Use `search` to find source files modified recently
2. For each modified file, read it and check for:
   - Potential null reference or runtime error issues
   - Missing error handling
   - Large methods (>50 lines) that could be split
   - Magic numbers that should be constants
   - Missing or incorrect documentation on public APIs
3. Save your findings using the `memory` tool:
   - action: "append", category: "known_issues" for bugs found
   - action: "log" for general observations
4. Summarize findings in your final response

Important:
- Be concise — flag real issues, not style nitpicks
- Don't modify any files — this is a read-only review
- Focus on bugs and maintainability, not formatting
