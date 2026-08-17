# FINAL SYSTEM REPORT — updated 2026-08-15 (post-authentication + benchmarking)

## SYSTEM STATUS: LIVE — 2 of 3 legs authenticated, routing on real benchmark data

Superseded the original bootstrap-day report (0 providers authenticated).
Since then: OpenCode Go got authenticated, 9 of its models were spot-tested
with real tasks, the router now actually selects models instead of blocking
every tier, cost/usage logging is wired into real execution (not dormant),
and a test-isolation bug (tests polluting production health state) was found
and fixed.

## EXACT COUNTS (current)

**Agents:** 301 discovered (164 live, 137 offline). 163 synced to OpenCode, confirmed via `opencode agent list`.

**Skills:** 3,812 discovered (265 live, 3,547 offline). Live skills OpenCode-native by default; offline ones promoted on-demand via junction (smart_route.py), not en masse.

**Providers — real auth status, verified by actually running each CLI's own status command:**
- **Claude** (`anthropic`): authenticated via Claude Code CLI (this session). NOT usable inside OpenCode — Anthropic's subscription OAuth is scoped to the Claude Code client only; OpenCode's own Anthropic login wants a separate paid API key.
- **OpenCode Go** (`opencode-go`): **AUTHENTICATED** — 1 credential confirmed via `opencode auth list`, 26 models confirmed via `opencode models`.
- **GPT/Codex** (`openai`): Codex CLI installed, NOT logged in (`codex login status` → "Not logged in"). Waiting on user to run `codex login`.

**Models benchmarked with real tasks (9 of 26 OpenCode Go/Zen models), judged against `fixtures/benchmark_tasks.json` pass criteria:**
| Tier | Models |
|---|---|
| A | `kimi-k3`, `qwen3.8-max` |
| B | `qwen3.7-plus`, `kimi-k2.7-code` |
| C | `mimo-v2.5`, `mimo-v2.5-pro`, `glm-5.1` |
| UNKNOWN (real failures found, not just untested) | `deepseek-v4-flash` (blocked — China-hosted, needs opt-in), `deepseek-v4-flash-free` (times out even at 150s — unreliable) |
| Untested | remaining 17 |

Full detail: `reports/BENCHMARK_RESULTS.md`. Re-extend anytime with `scripts/run_benchmark.py <model_id>`.

**Router verified live:** all four capability tiers (A/B/C/D) now route to a real, tested model instead of blocking — confirmed by running `router/model_selector.py` against each floor.

**Tests:** 11/11 passing. Test-isolation bug fixed (tests were writing simulated provider health into production `health/state.json` — now uses `CONTROL_PLANE_HEALTH_PATH` override).

**Execution wiring:** `adapters/cli_dispatch.py` now actually calls `claude -p` / `codex exec` / `opencode run -m <model>`, logs every real (non-dry-run) call to `logs/usage.jsonl` via `orchestrator/usage_logger.py`, and updates task state. Verified end-to-end with a live dispatch (real `opencode run` call, logged with real latency).

**Verification wiring:** `orchestrator/verify.py` detects real project type (package.json/pyproject.toml+uv.lock/requirements.txt/go.mod/Cargo.toml) and runs the actual lint/test command — no longer a stub. Found and fixed a real bug testing it: uv-managed Python projects need `uv run pytest`, not bare `python -m pytest`.

## Unresolved / explicitly deferred

- Budget Manager bars still show `?` (no cap set) — needs real numbers from you in `config/budget_caps.json`; no API exposes this automatically for subscription plans.
- 17 of 26 OpenCode Go/Zen models still unbenchmarked — correctly excluded from routing.
- GPT/Codex leg not yet online — waiting on `codex login`.
- Token/cost figures in usage log are null (OpenCode's CLI doesn't expose them) — latency is real, cost isn't yet.
- 244 duplicate skill names, 70 heuristic security-scan flags — both reviewed at a sample level, not resolved individually (judgment calls, not automatable).

## Rollback

Unchanged from original — everything is additive and self-contained under `C:\AI\control-plane` and `C:\AI\bootstrap`. See `OPERATIONS.md`.
