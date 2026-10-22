# Working in this repo

## Subagents
- Don't spawn subagents unless the user asks or the work clearly can't be done inline. Prefer doing searches, reads and test runs directly; never spawn several for one task when one (or none) will do.
- When a subagent is warranted:
  - Simple lookups ("where is X", "find usages of Y"): use the `lookup` agent (Haiku).
  - Searching across files, summarizing logs/docs, running tests: use the `researcher` agent (Sonnet).
  - Other subagents default to Sonnet (`CLAUDE_CODE_SUBAGENT_MODEL` in `.claude/settings.json`).
- Keep design work and code changes in the main session.
