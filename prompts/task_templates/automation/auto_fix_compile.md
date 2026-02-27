## Automated Task: Fix Build Errors

You are running as an automated scheduled task. Your goal is to detect and fix any compilation/build errors in the project.

Steps:
1. Use the available tools to check for build errors or compile diagnostics
2. If no errors are found, respond with "No build errors detected" and stop
3. For each error found:
   a. Read the file and line indicated by the error
   b. Understand the root cause (missing reference, typo, API change, etc.)
   c. Apply a minimal, targeted fix
   d. Validate the fix if a validation tool is available
4. Log what you fixed using the `memory` tool (action: "log")

Important:
- Only fix clear compilation/build errors
- Do not refactor or "improve" code beyond what's needed to compile
- If unsure about a fix, log the issue instead of guessing
- Prefer the simplest correct fix
