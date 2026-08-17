# Operations

## Rebuild registries (safe, read-only against sources)
```
uv run C:\AI\control-plane\scripts\build_agent_registry.py
uv run C:\AI\control-plane\scripts\build_skill_registry.py
```

## Run tests
```
uv run pytest C:\AI\control-plane\tests -q
```

## Inspect health
Read `health/state.json` (short-TTL provider/model health cache).

## Inspect routing/usage
Read `logs/*.jsonl` and `reports/routing_summary.md`, `reports/usage_summary.md`.

## Recover / rollback
Nothing in `~/.claude` was modified. To roll back any OpenCode config change made
by `integrations/opencode_sync.py`, restore `~/.config/opencode/opencode.jsonc`
from the pre-change copy it writes to `C:\AI\control-plane\logs\opencode_config_history\`.
To remove the control plane entirely: delete `C:\AI\control-plane` and
`C:\AI\bootstrap` (both are self-contained; nothing outside them was altered).
