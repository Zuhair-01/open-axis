# OpenCode Handoff — updated 2026-08-15 post-authentication

## What's live right now

- OpenCode v1.18.18, config at `~/.config/opencode/opencode.jsonc`, 163 agents synced (`opencode agent list` confirms them).
- **OpenCode Go is authenticated** — real subscription, confirmed via `opencode auth list` (1 credential) and `opencode models` (26 models: 7 free `opencode/*` + 19 `opencode-go/*`).
- **9 of those 26 models benchmarked with real tasks**, tier-rated from actual output (see `reports/BENCHMARK_RESULTS.md`): Tier A = `kimi-k3`, `qwen3.8-max`; Tier B = `qwen3.7-plus`, `kimi-k2.7-code`; Tier C = `mimo-v2.5`, `mimo-v2.5-pro`, `glm-5.1`. Two real failures found: `deepseek-v4-flash` needs an explicit China-hosting opt-in (compliance decision, not done for you), `deepseek-v4-flash-free` times out unreliably.
- Router confirmed live: all four tiers (A/B/C/D) route to a real model, tested end-to-end with an actual `opencode run` dispatch that logged real latency to `logs/usage.jsonl`.

## Your three subscriptions — clarified with real test results

- **Claude Code Pro**: works — this session, right now. Cannot be used inside OpenCode; Anthropic's subscription OAuth is scoped to the Claude Code client only. Confirmed by OpenCode's Anthropic login prompting for a separate paid API key instead of subscription login.
- **ChatGPT+**: separate from OpenAI's API. The real path is OpenAI's own **Codex CLI**, which does support "Sign in with ChatGPT" (verified via OpenAI's docs). Codex CLI is already installed on this machine — just not logged in yet (`codex login status` → "Not logged in").
- **OpenCode Go**: this was the one that actually worked as a direct login — confirmed authenticated, 26 models live.

## Remaining action for you

```
codex login
```
Choose "Sign in with ChatGPT" when prompted. Then tell me — I'll verify with `codex login status` and wire the third leg into `providers.json`/`model_registry.json`, same as was just done for OpenCode Go.

## Optional, whenever you want it

Fill in real numbers in `config/budget_caps.json` (your plan's request/token limits per rolling window) so the Model Budget Manager's bars show real percentages instead of `?`. No provider API exposes this automatically for subscription plans — it has to come from you.
