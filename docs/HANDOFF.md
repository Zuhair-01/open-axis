# Open Axis — Handoff / Continuity

**If you're a fresh Claude session reading this because the user said
"continue openaxis": read this file, then `docs/OPEN_AXIS_COMPLETE_REFERENCE.md`
for full architecture, then check `reports/` for the latest state. Don't
re-derive from scratch — everything below is real, verified state.**

## What Open Axis is (one paragraph)

A control plane that routes engineering tasks across 4 real AI legs
(Claude, Codex/GPT, OpenCode Go, Ollama) dispatched through each provider's
own official CLI (not API keys — those don't work with consumer
subscriptions). Frontend is a REPL (`openaxis` command, global on PATH).
Full pipeline: clarity gate → triage (real model call, classifies +
prompt-engineers) → skill/agent selection → capability-floor-gated model
selection → dispatch → fallback → task_state (SQLite) → usage log.

## Current real state (last verified 2026-08-15)

- **All 4 legs live and authenticated**: Claude (`claude -p`), Codex
  (`codex exec --skip-git-repo-check`, model `gpt-5.6-terra`), OpenCode Go
  (`opencode run -m`, 26 models), Ollama (`ollama run`, 5 local models).
- **45/45 tests passing** (`tests/test_control_plane.py` = 32,
  `tests/test_clarity_gate.py` = 13). Run both before believing anything
  works — don't take this file's word for it if time has passed.
- **13 of 31 models benchmarked** with real judged tasks.
- Desktop shortcut `Open Axis.lnk` + global `openaxis` command both work.
- **Frontend (Task #17) shipped**: Esc-to-interrupt (real mid-flight
  subprocess kill, not just a UI flag) and type-ahead task queueing (type
  your next task while one is still dispatching; it queues and auto-runs
  after, processed serially) — both live in `orchestrator/repl.py`'s
  `_spin()`, which is the sole writer to its terminal line, so keystroke
  capture there doesn't collide with any other output. See "Just-fixed"
  below for the design reasoning and the real cwd bug fixed alongside it.

## Just-fixed, verify still holds

A real bug was found LIVE (user reported a 323-second hang on "understanding
task"): root cause was `subprocess.Popen` never closing stdin, so a child
CLI (confirmed: Codex prints "Reading additional input from stdin...") could
block forever waiting for input that would never come. Fixed with
`stdin=subprocess.DEVNULL` in `adapters/cli_dispatch.py`, plus a proper
short timeout (60s) for the quick classification-style calls (triage,
anti-loop check, judge) instead of the 1800s execution-timeout default, plus
actually killing the child process on timeout (Python doesn't do this
automatically). Verified: same failing task now completes in 15.8s.
**If you see another multi-minute hang, check this pattern first** —
`stdin=subprocess.DEVNULL` and an appropriately short `timeout=` param on
any new dispatch() call site you add.

## Just-fixed #2, verify still holds

Live-reported by the user (screenshot): a "test my systems" task ran for
348s on `opencode-go/glm-5.1`, and the model's own output said the paths
triage referenced (`C:\AI\control-plane\tests\test_control_plane.py` etc.)
didn't exist. They DO exist — the model was correctly skeptical and
verified, but it verified against the wrong directory. Root cause:
`repl()` defaulted `cwd = "."`, which resolves to wherever the shell was
when the global `openaxis` command was typed (the user's home dir in that
screenshot), not the Open Axis repo. `triage.py`'s `_project_context()`
correctly tells the dispatched model "Open Axis lives at
`C:\AI\control-plane`", but the actual CLI subprocess launched with a
different cwd, so of course it found nothing there. Fixed: `repl()` now
defaults `cwd = str(CP)` (the Open Axis repo itself) — `/cd` still exists
to point dispatches at any other project. Regression-guarded by
`test_repl_defaults_cwd_to_own_repo_not_launch_dir`.
**If a dispatched model reports your own files as "not found," check cwd
first** (`/cd` with no arg shows the current one) before assuming the
model or the routing is broken.

## In-flight / not yet done (real, not padding)

1. **Task #19**: quality-gated escalation — detect a subtly WRONG answer
   (not just a crash) and escalate to a stronger model. Concrete plan:
   wire `orchestrator/verify.py`'s real test results into `auto.py`'s
   success determination for code-touching tasks, escalate one tier on
   real verification failure. Scoped, not built.
2. **Task #21**: tighten `/evolve`'s Tier-D promotion criteria (add
   verification-signal requirement, not just exit-code success rate) +
   add provenance/hash tracking to `opencode_skill_promote.py`'s junction
   mechanism (skill_id, sha256, trust_level, promoted_by_task_id). Scoped,
   not built.
3. **Comparison-mode auto-routing** (`orchestrator/comparison_policy.py`)
   is built and tested standalone but **deliberately NOT wired into
   default task routing** — user explicitly said "let it sit... unless
   it's fixing something that already exists" mid-session. Don't wire it
   into `auto()`'s default path without the user asking again.

## Rules this session established, don't relitigate

- **No subagent spawning, ever** (`policies/subagent_policy.json`) —
  explicit user decision after token-cost concerns. Agent personas load
  inline, never spawned.
- Never invent a capability tier — a model without real benchmark data
  stays `UNKNOWN` and is excluded from routing, no exceptions.
- Every registry/policy claim must be verified against the actual
  installed CLI (`--help`, a real test dispatch), never assumed from
  training knowledge — this session found real, surprising CLI syntax
  differences from what would've been guessed (e.g. `codex exec` needs
  `--skip-git-repo-check`, Ollama's model is positional not a flag).
- When something breaks live, reproduce it, find the real root cause, fix
  that — not the symptom. This file exists because that discipline
  produced a real fix (the stdin/timeout bug) instead of a band-aid.

## Where to look for anything else

`docs/OPEN_AXIS_COMPLETE_REFERENCE.md` has the full module map, command
list, and architecture diagram. `reports/WEAKNESS_MAP.md` and
`reports/SPEC_CODE_GAP_ANALYSIS.md` have the fuller history of what's been
audited and fixed. Task list (if the harness's task tracking persists) has
#19/#21 as the live open items (#17/#20 shipped this session).
