# Benchmark Results — real data, spot-tested 2026-08-15

Method: each model run once against a task from `fixtures/benchmark_tasks.json`
matching its candidate tier, output judged by hand against that task's
`pass_criteria`. Single-probe evidence per model — real, not simulated, but
not a full statistical suite. Re-run `scripts/run_benchmark.py <model>` for
more coverage/confidence any time.

| Model | Task tested | Tier | Verdict |
|---|---|---|---|
| `opencode-go/qwen3.8-max` | a1_hard_reasoning | **A** | PASS — correct bytecode-level explanation, correct fix, extra real nuance (RLock, free-threaded 3.13) |
| `opencode-go/kimi-k3` | a1_hard_reasoning | **A** | PASS — matched/exceeded qwen3.8-max, included working demo + `__iadd__` nuance unprompted |
| `opencode-go/qwen3.7-plus` | c1_routine_implementation | **B** | PASS — correctly handled unsorted input + touching intervals without being told to |
| `opencode-go/kimi-k2.7-code` | b1_debugging | **B** | PASS — replaced silent failure with a proper explicit exception |
| `opencode-go/mimo-v2.5` | d1_simple_edit | **C** | PASS — correct, idiomatic |
| `opencode-go/mimo-v2.5-pro` | d1_simple_edit | **C** | PASS — same task/difficulty as base mimo-v2.5, no harder-task evidence yet despite "-pro" name, so NOT assumed higher |
| `opencode-go/glm-5.1` | d2_formatting | **C** | PASS — thorough, added doctest examples unprompted, quality clearly exceeds a D-tier bar |
| `opencode-go/qwen3.7-max` | b2_refactor | **B** | PASS — dispatch table + dependency injection for testability, explicit error handling. Quality suggests possible A, rated conservatively at the level actually tested |
| `opencode-go/deepseek-v4-flash` | (blocked) | UNKNOWN | BLOCKED — China-hosted, requires explicit opt-in (data residency notice). Not tested — this is a compliance decision, not a routing one. |
| `opencode/deepseek-v4-flash-free` | d2_formatting | UNKNOWN | **FAIL** — timed out twice (60s, then 150s) on a trivial task. Real reliability failure, not just untested. |

**Untested (15 models):** `opencode-go/deepseek-v4-pro`, `glm-5.2/5.3`,
`gpt-5.6-luna`, `grok-4.5`, `hy3`, `kimi-k2.6`, `minimax-m2.7/m3`,
`qwen3.6-plus`, and 6 of the 7 free `opencode/*` models. All correctly
excluded from routing (`capability_tier: UNKNOWN`) until tested — run
`scripts/run_benchmark.py <model_id>` to extend coverage.

## Recommended routing table (from confirmed data only)

| Task type | Route to | Why |
|---|---|---|
| ARCHITECTURE, SECURITY, DIFFICULT_DEBUGGING (Tier A) | Claude (this session) or `kimi-k3` / `qwen3.8-max` | Both A-tier confirmed; Claude for anything you want maximum trust on, the OpenCode Go pair as a real fallback/second-opinion, not a downgrade |
| IMPLEMENTATION, DEBUGGING, REFACTOR (Tier B) | `qwen3.7-plus` or `kimi-k2.7-code` (code-specialist naming matched observed behavior — prefer it for pure code tasks) | Confirmed B-tier, free of the premium-brain cost |
| ROUTINE_IMPLEMENTATION, SIMPLE_EDIT, DOCUMENTATION (Tier C/D) | `mimo-v2.5` | Confirmed C-tier, cheapest tested option that's actually verified (not just assumed cheap) |
| GPT/Codex-preferred tasks (second opinion, independent review) | pending `codex login` | Not yet authenticated |

## Fallback logic this enables right now

```
Tier A task, Claude rate-limited/unavailable
  -> kimi-k3 (confirmed A) -> qwen3.8-max (confirmed A) -> BLOCKED (never downgrade to untested/lower)

Tier B task
  -> qwen3.7-plus / kimi-k2.7-code -> Claude (if B task and A-tier is idle, fine to use, just costlier)

Tier C/D task
  -> mimo-v2.5 -> mimo-v2.5-pro -> BLOCKED until more C/D models are benchmarked
```

This is genuinely usable now for the two authenticated legs (Claude + OpenCode
Go). Extend it by running more of the 18 untested models through
`run_benchmark.py` when you have real tasks that need them, or want broader
coverage before relying on it more heavily.
