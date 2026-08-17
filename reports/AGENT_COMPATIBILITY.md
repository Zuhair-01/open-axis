# AGENT COMPATIBILITY

All agents currently live under Claude Code's agent format (YAML frontmatter + markdown system prompt). None have been verified against OpenCode's native agent schema yet (that requires inspecting installed OpenCode v1.18.18's actual agent config format, done in Phase 33/scripts/opencode_agent_check.py). Until that check runs, classify all as CLAUDE_SPECIFIC pending verification — do not assume portability.
