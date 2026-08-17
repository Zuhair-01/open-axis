# Tech Stack Decision

Based on Phase 0 discovery (`C:\AI\bootstrap\discovery\tools.json`):

| Tool | Installed | Version |
|---|---|---|
| Python | yes | 3.14.4 |
| Node.js | yes | 24.15.0 |
| uv | yes | 0.5.9 |
| Git | yes | 2.54.0 |
| Docker | yes | 29.6.2 |
| Ollama | yes (daemon not running) | - |

## Decision

- **Orchestration / control-plane logic: Python 3.14**, run via `uv` (already installed, fast, no global site-packages pollution).
- **Config / registries: JSON** (human-diffable, matches OpenCode's own `opencode.jsonc` convention, no YAML parser dependency needed since none was already present).
- **Schema validation: JSON Schema** (`schemas/*.schema.json`), validated with Python's `jsonschema` if available, otherwise a hand-rolled minimal validator (avoid adding a new dependency merely for this).
- **State persistence: SQLite** (`task_state/state.db`) via Python's built-in `sqlite3` — no server process, no new dependency, durable across process restarts.
- **No new frameworks introduced.** No Redis, no Postgres, no message queue — none justified at this scale (single-user, single-machine control plane).

This keeps the stack to things already on disk. Nothing here duplicates OpenCode's native provider/agent/skill/permission systems (see ARCHITECTURE.md) — this stack exists only for the orchestration layer OpenCode does not provide natively.
