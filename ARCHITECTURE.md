# Architecture

## Boundary rule

OpenCode (v1.18.18, installed) already natively provides: providers, models, agents,
subagents, skills, permissions, commands, project configuration, MCP/tool integration.
This control plane does **not** re-implement any of those. It provides only what
OpenCode's native system does not:

- cross-provider **routing policy** (which model for which task, cost-aware)
- **capability classification** (tier floors, never silently downgraded)
- **fallback state machine** (provider/model failure -> next candidate, task state preserved)
- **task state persistence** across fallback/interruption (SQLite)
- **cross-environment registry** (agents/skills/providers/models as data, sourced from
  real inventory, not invented)
- **security policy layer** (permission ALLOW/ASK/DENY, secret handling, skill
  suspicious-pattern scanning) that both Claude Code and OpenCode read from
- **observability** (structured logs, usage/routing/fallback summaries)
- **testing/validation harness**

## Relationship to existing assets

- `~/.claude` (Claude Code) is left untouched and fully preserved. It already has its
  own OVERSEER/OmniRoute bundle system (`~/.claude/overseer`) which is a
  Claude-Code-specific skill router — this control plane treats it as a separate,
  preserved asset, not something to merge into. See `docs/OVERSEER-RELATIONSHIP.md`.
- `~/.config/opencode/opencode.jsonc` is OpenCode's native config. This control plane
  writes to it only through `integrations/opencode_sync.py`, which validates against
  the installed OpenCode version's actual schema before writing, and only adds keys
  OpenCode's docs confirm exist.

## Data flow

```
TASK (user request)
  -> router/classifier.py       (deterministic + heuristic task classification)
  -> router/agent_selector.py   (reads registry/agents/agent_registry.json)
  -> router/model_selector.py   (reads registry/models + registry/providers,
                                  enforces capability floor from policies/capability_tiers.json)
  -> orchestrator/fallback.py   (on failure: classify error, consult policies/fallback_chains.json,
                                  persist to task_state/state.db, retry next candidate)
  -> health/provider_health.py  (short-TTL health cache, never permanent blacklist)
```

## Non-duplication checklist

- [x] No custom skill-loading engine that duplicates OpenCode's native skill discovery
- [x] No custom agent execution engine — agents still run inside Claude Code or OpenCode
- [x] No custom permission enforcement inside OpenCode — we only *author* OpenCode's
      native permission config; enforcement stays native
