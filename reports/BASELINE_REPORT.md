# BASELINE REPORT — 2026-08-15

Real, measured, not guessed. Every number below was produced by running a command.

## Runtime
- Python: 3.14.4
- Claude Code CLI: 2.1.233
- Codex CLI: 0.147.0
- OpenCode CLI: 1.18.18 (stable; no `opencode2` binary present on this machine — beta/V2 is not a concern here)

## Provider auth (verified via each CLI's own status check, not assumed)
| Provider | Status |
|---|---|
| anthropic (Claude) | LIKELY_AUTHENTICATED |
| opencode-go | LIKELY_AUTHENTICATED |
| opencode-zen (free tier) | LIKELY_AUTHENTICATED (no credential needed) |
| openai (Codex) | NOT_AUTHENTICATED — CLI healthy, `codex login` not yet run |

## Registries
- Agents: 301 (164 live, 137 offline library)
- Skills: 3,812 (265 live, 3,547 offline library)
- Models registered: 25
- Models with real benchmark data (capability_tier != UNKNOWN): 11 of 25 (44%)
- Models unbenchmarked, correctly excluded from routing: 14

## Tests
- 20/20 passing (`tests/test_control_plane.py`)

## Current routing policy (as implemented, not as originally spec'd)
- Hard capability-floor filter (never crossed)
- Health/budget filter (skip DEGRADED/UNAVAILABLE/AUTH_FAILURE providers, short TTL, never permanent)
- Priority-by-tier: A→Claude first, B→GPT/Codex first (currently falls through to Claude since GPT has 0 model entries — not authenticated), C/D→OpenCode Go workhorse first
- Cost is a tiebreak within the same priority level, not primary driver

## Current fallback policy
- Real dispatch failure (non-zero exit / ERROR / TIMEOUT) marks that provider DEGRADED (120s TTL) and re-plans once against next-best candidate at the same-or-higher floor
- Never silently downgrades below the required floor
- Explicit `/model` pin disables auto-fallback-redirect (user's explicit choice is respected, failure reported not rerouted)

## Known architecture facts relevant to this spec's assumptions
- **Capability tiers are already per-MODEL, not per-provider** (`registry/models/model_registry.json` stores `capability_tier` on each model entry individually — e.g. `opencode-go/kimi-k3` = A, `opencode-go/mimo-v2.5` = C, both under the same provider). Spec Step 13's concern ("Tier A == Claude permanently") does not match the actual implementation — this was already correct.
- Triage (`router/triage.py`) is a REAL model call on every task with no text-obvious fast path yet — this is the one clear, valid gap this spec's Step 8 (Clarity Gate) identifies correctly.
- Session continuation (`/continue`, `claude -c`) only implemented for the Claude leg.
- Cost/token fields are structurally null (CLIs don't expose them in a capturable way) — never fabricated.
