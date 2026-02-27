## Automated Task: Generate Documentation

You are running as an automated scheduled task. Add documentation to public APIs that are missing it.

Steps:
1. Use `search` to find public classes and methods without documentation
2. Prioritize:
   - Public classes without any doc comment
   - Public methods without parameter/return documentation
   - Public properties without description
3. For each undocumented item:
   - Read the surrounding code to understand its purpose
   - Add concise, accurate documentation
   - Follow the project's documentation conventions
4. Log what you documented using the `memory` tool (action: "log")

Important:
- Only add docs where they're missing — don't rewrite existing ones
- Keep descriptions concise (1-2 sentences)
- Document parameters and return values
- Don't add docs to private/internal members
