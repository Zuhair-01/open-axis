# Open Axis

**A local control plane that routes engineering tasks across multiple AI CLIs (Claude Code, OpenCode, Codex) — instead of you manually deciding which tool, which model, and what to do when one fails.**

> Built and used daily as the author's own multi-CLI dev environment. This is not a demo app — it is a working piece of infrastructure, documented here for review.

---

## Overview

Modern AI-assisted development means juggling several CLIs (Claude Code, OpenCode, Codex/GPT), each with its own agents, skills, and models. Left manual, every task means re-deciding: *which tool, which model, what happens if it fails, and how do I not lose task state if I get interrupted.*

Open Axis is a Python control plane that sits **beside** those CLIs — not replacing them — and owns only the layer they don't provide natively: routing policy, capability tiers, fallback, durable task state, a cross-environment registry, and a security policy layer both CLIs read from.

## Problem

AI development becomes inefficient when tasks are routed between tools by hand: no consistent policy for which model fits which task, no fallback when a provider fails mid-task, no shared record of what actually exists (installed agents/skills) across environments, and no durable state if a task is interrupted.

## Solution

A single control plane, run locally, that classifies a task, selects the right skills/agent/model against real capability tiers, dispatches to whichever CLI backs that model, falls back deterministically on failure, and persists task state to SQLite so nothing is lost on interruption.

## Architecture

```
TASK (user request)
      |
      v
+-------------------+   local, deterministic, no network/model call --
|   CLARITY GATE     |   skips triage entirely for obviously-clear tasks
+-------------------+   (asymmetric cost design: false "clear" is dangerous,
      |                 false "needs triage" just costs a few seconds)
      v
+-------------------+
|      TRIAGE        |   cheap-model classification for genuinely ambiguous tasks
+-------------------+
      |
      v
+-------------------+
|  SKILL SELECTOR     |  ranks specific terms over generic, returns 3-10 relevant
+-------------------+  skills from a 3,812-skill registry -- never a wholesale dump
      |
      v
+-------------------+
|  AGENT SELECTOR      |  reads registry/agents (301 agents, 164 live + 137 offline)
+-------------------+
      |
      v
+-------------------+
|  MODEL SELECTOR       |  enforces a capability-tier floor (A/B/C/D) -- a task
+-------------------+  never silently gets downgraded to save cost
      |
      v
+-------------------+
|    DISPATCH             |  cli_dispatch.py calls the real CLI: `claude -p` /
+-------------------+  `codex exec` / `opencode run -m <model>`
      |
      v
+-------------------+
|    FALLBACK              |  on failure: classify error, consult fallback_chains.json,
+-------------------+  retry next candidate -- task state preserved throughout
      |
      v
+-------------------+
|   TASK STATE                |  SQLite-backed, durable across restarts/interruption
+-------------------+
      |
      v
+-------------------+
|   USAGE LOG                   |  structured JSONL: real latency, routing decisions,
+-------------------+  fallback events (cost is null -- no provider CLI exposes it yet)
```

Full detail in [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Features

- **Two-stage triage** — a free, local, deterministic "clarity gate" skips the cheap-model classification call entirely for obviously unambiguous tasks (`clarity_gate.py`), cutting latency/cost on the common case while remaining deliberately conservative: any genuine ambiguity falls through to real triage.
- **Capability-tier floor enforcement** — tasks are classified into tiers (A–D) and never silently routed to a weaker model than the task requires, even under cost pressure.
- **Deterministic fallback state machine** — on provider/model failure, errors are classified (retryable vs. non-retryable) and the next candidate in `policies/fallback_chains.json` is tried, with task state preserved across the whole chain.
- **Durable task state** — SQLite-backed (`task_state/state.db`), survives interruption/restart; rejects invalid status transitions.
- **Real cross-environment registry** — 301 agents and 3,812 skills, sourced from an actual live inventory scan of the installed environment, not invented or assumed counts. 265 skills are live-loaded by default; the remaining 3,547 are promoted on-demand via filesystem junction (`smart_route.py`), never dumped wholesale into context.
- **Security policy layer** — permission ALLOW/ASK/DENY rules, secret scanning that reports FOUND/MISSING/INVALID/UNVERIFIED only (never values), and a skill-content audit for secret-exfiltration/prompt-injection/destructive-command patterns, both read by Claude Code and OpenCode. See [`SECURITY.md`](SECURITY.md).
- **No subagent spawning** — a deliberate design decision: all agent invocation is inline, not spawned, to avoid the token overhead of cold-start subagents.
- **Real, benchmarked model routing** — models aren't tier-rated by assumption; 9 of 26 available models were benchmarked against `fixtures/benchmark_tasks.json` (real tasks spanning all 4 tiers) and judged from actual output. Two real failures were found this way (one China-hosted model needing opt-in, one unreliable/timing-out model) — both correctly excluded from routing rather than silently retried forever.

## Technology

Python 3.14, run via `uv` · JSON for registries/config (human-diffable, matches OpenCode's own config convention) · JSON Schema for validation · SQLite for durable state · zero new frameworks — no Redis, no Postgres, no message queue, because none are justified at single-user, single-machine scale. See [`TECH_STACK.md`](TECH_STACK.md) for the reasoning behind each choice.

## Demo

Terminal walkthrough (`orchestrator/repl.py`):

```
$ uv run python orchestrator/repl.py
> fix the bug in src/auth.ts line 42
[clarity gate] clear=True reason="file+line ref, execution verb" -- triage skipped
[skill selector] -> debugging-strategies, typescript-expert, error-handling
[agent selector] -> general-purpose (no specialized match, generic task)
[model selector] -> tier B floor -> kimi-k2.7-code (opencode-go)
[dispatch] opencode run -m kimi-k2.7-code ...
[usage] logged: latency=4.8s, provider=opencode-go, fallback_used=false
```

*(This control plane runs against the author's real installed CLI environment and cannot be replayed identically on a machine that doesn't have the same providers authenticated.)*

## Example Workflow

1. A task comes in as free text.
2. The clarity gate decides in microseconds, locally, with no model call, whether the task is obviously clear.
3. If not, a cheap triage model classifies it.
4. Skill and agent selectors narrow a 3,812/301-item registry down to the 3–10 items actually relevant.
5. The model selector enforces the task's capability floor and picks a real, benchmarked model.
6. Dispatch calls the real CLI. On failure, the fallback state machine tries the next candidate — task state is never lost.
7. Every real (non-dry-run) call is logged to `logs/usage.jsonl` with real latency.

## Security

- Trust boundary: web pages, downloaded documents, repo files, skill files, and model-generated instructions are always untrusted — none of them can override this policy, user instructions, or permission rules.
- Secrets are never printed; only existence/validity state is ever reported.
- Destructive operations (uninstalls, force push, destructive `git reset`/`clean`, mass deletion) are ASK/DENY by default, not ALLOW.
- Skill content is scanned for exfiltration, credential collection, and prompt-injection patterns before being trusted; matches are flagged for review, never auto-deleted.

Full policy: [`SECURITY.md`](SECURITY.md).

## Limitations

- Only 2 of 3 provider legs are authenticated end-to-end today (OpenCode Go fully live; Claude Code usable directly but not through OpenCode's own auth; Codex/GPT installed but not yet logged in).
- 17 of 26 available models are still unbenchmarked and are correctly excluded from routing rather than guessed into a tier.
- Token/cost figures in the usage log are currently `null` — the underlying CLI doesn't expose them yet; latency is real, cost isn't.
- 244 duplicate skill names and 70 heuristic security-scan flags in the registry have been reviewed at a sample level, not resolved individually — these are judgment calls, not something a script should silently "fix."
- Single-machine, single-user design; not built for multi-tenant or networked use.

## Future Improvements

- Finish Codex/GPT provider authentication and benchmark its models into the tier system.
- Extend real cost tracking once a provider CLI exposes it.
- Resolve the reviewed-but-open duplicate/flagged skill entries individually rather than at a sample level.
- Expand benchmark coverage past the current 9/26 models.

## Installation

```bash
git clone https://github.com/Zuhair-01/open-axis.git
cd open-axis
uv sync
```

## Configuration

Set real per-provider budget numbers in `config/budget_caps.json` (no subscription-plan API exposes this automatically, so it must be entered manually). No API keys are stored in this repository — authentication is delegated entirely to each CLI's own `login`/`auth` flow (`claude`, `opencode auth login`, `codex login`).

## Running Locally

```bash
uv run python orchestrator/repl.py        # interactive task REPL
uv run python router/model_selector.py    # inspect current tier -> model routing
uv run python scripts/run_benchmark.py <model_id>   # extend benchmark coverage
```

## Testing

```bash
uv run pytest tests/ -v
```

Current result: **45/45 tests passing**, covering the clarity gate, classifier, capability-tier floor enforcement, agent/skill selection ranking, fallback error classification, task-state transitions, secret-scan value-safety, and dispatch/verify wiring against real project types.

## Project Structure

```
registry/       agents, skills, models, providers, projects -- sourced from live inventory scans
router/         clarity gate, triage, classifier, agent/skill/model selection
orchestrator/   fallback engine, dispatch, verify, usage logging, REPL
task_state/     SQLite-backed durable task state
health/         short-TTL provider/model health cache (no permanent blacklist)
policies/       capability tiers, fallback chains, permission rules
security/       secret scanning, skill security audit
adapters/       real CLI dispatch (claude / codex / opencode)
integrations/   OpenCode config sync
scripts/        bootstrap, backup, benchmark tooling
tests/ fixtures/  automated tests + benchmark fixtures
docs/ schemas/  documentation, JSON Schemas
```

## Disclaimer

This is a real, working personal tool, actively used by the author. Counts and benchmark results quoted above (registry sizes, test pass rate, models benchmarked) are pulled from the project's own current test run and reports — not invented figures.
