# Changelog

## 2026-08-15 — Bootstrap
- Phase 0: read-only discovery completed (`C:\AI\bootstrap\discovery\`).
- Phase 1: full backup of `~/.claude` critical assets to `C:\AI\bootstrap\backups\20260815_000737\`.
- Phase 2-3: control-plane scaffold created, tech stack decided (Python + JSON + SQLite).
- Phase 4-6: real agent (301) and skill (3,812) registries built from live scan, not assumed counts.
- Phase 9-16, 22-27, 31-35: providers/models registry, router, fallback engine, permissions, OpenCode integration (163 agents synced, verified live in `opencode agent list`).
- Model Budget Manager + full routing pipeline (capability floor -> quota -> cost -> latency) built.
- Smart skill/agent selection (task -> 3-10 skills -> 1 agent persona, no wholesale dump) built and tested against real queries.
- No-subagent policy adopted (user decision) - all agent invocation is INLINE, spawning removed entirely.

## 2026-08-15 (later same day) — Real provider onboarding + hardening
- OpenCode Go authenticated (real subscription) - 26 models confirmed live via `opencode models`.
- 9 of 26 models benchmarked with real representative tasks, tier-rated from actual judged output - not guessed. 2 real failures found (China-hosting opt-in required; unreliable timeout).
- Reusable benchmark infrastructure built: `fixtures/benchmark_tasks.json` (8 tasks spanning all 4 tiers) + `scripts/run_benchmark.py` for extending coverage anytime.
- Router verified live: all four capability tiers now route to a real, tested model.
- `adapters/cli_dispatch.py` built - dispatches real work to `claude -p` / `codex exec` / `opencode run -m`, wired into `usage_logger` so cost/latency tracking is live, not dormant.
- Found and fixed a real test-isolation bug: the test suite was writing simulated provider health into production `health/state.json`; added `CONTROL_PLANE_HEALTH_PATH` override.
- `orchestrator/verify.py` built (generic lint/test runner by detected project type). Found and fixed a real bug testing it against a live uv-managed project: needed `uv run pytest`, not bare `python -m pytest`.
- GPT/Codex leg: Codex CLI confirmed installed, not yet logged in - waiting on user's `codex login`.
