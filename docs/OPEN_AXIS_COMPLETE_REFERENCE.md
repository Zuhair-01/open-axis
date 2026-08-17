# Open Axis — Complete Reference

**Status as of 2026-08-15.** Every fact below is real — pulled from actual
files, real test runs, and live dispatches. Nothing here is aspirational.

## What this is and why it exists

Open Axis is a control plane that routes engineering tasks across multiple
AI subscriptions you already pay for, instead of using per-token API keys.
The original plan was API-based routing; that broke immediately because
Anthropic and OpenAI don't expose consumer subscriptions (Claude Pro,
ChatGPT+) through third-party tools — those only work inside their own
first-party clients. So Open Axis dispatches through each provider's own
official CLI instead:

| Leg | CLI | Subscription | Status |
|---|---|---|---|
| Claude | `claude -p` | Claude Pro | **Live** |
| GPT/Codex | `codex exec --skip-git-repo-check` | ChatGPT+ | **Live** (gpt-5.6-terra, verified end-to-end 2026-08-15) |
| OpenCode Go | `opencode run -m` | OpenCode Go (26 models) | **Live** |
| Ollama | `ollama run` | free/local | **Live** |

**All four legs live — the full milestone.** Codex was the last one; verified
with a real dispatch (`codex login status` → "Logged in using ChatGPT",
then a real `codex exec` call: exit 0, real session ID, task_state
COMPLETED). Needed `--skip-git-repo-check` (confirmed real/narrow via
`codex exec --help` — only bypasses the git-repo requirement, not
sandboxing or approvals). Ollama was added mid-session once it turned out
5 real local models (llama3.1:8b, deepseek-r1:8b, qwen2.5-coder:7b, gemma4,
moondream) were already installed and running, at zero cost and zero
network latency.

## Real counts

- **301 agents** discovered (164 live, 137 offline library) — all correctly
  linked, zero broken file references.
- **3,812 skills** discovered (265 live, 3,547 offline library) — zero
  broken directory links.
- **31 models registered**, **13 with real benchmark data** (spot-tested
  against actual judged tasks, not assumed) — includes Claude, OpenCode Go
  (7 models across A/B/C), Ollama's qwen2.5-coder:7b (C), and Codex's
  gpt-5.6-terra (B). 18 correctly excluded from routing until tested.
- **43/43 tests passing** (30 in `tests/test_control_plane.py` + 13 in `tests/test_clarity_gate.py`).

## How a task actually flows, end to end

```
You type a task into `openaxis` (global command, works from any terminal)
  │
  ▼
CLARITY GATE (router/clarity_gate.py) — local, free, instant, no model call
  │  Obviously-clear tasks ("run tests", "fix src/auth.ts line 42") skip
  │  straight to local classification. Deliberately conservative: a file
  │  path alone is never enough ("analyze auth.py" still needs real triage).
  │  When uncertain, always falls through to the real triage model below —
  │  false negatives (extra latency) are fine, false positives (wrong
  │  routing) are not.
  ▼
TRIAGE (router/triage.py) — real cheap-model call (opencode-go/mimo-v2.5),
  │  ~5-15s, only runs when the clarity gate didn't already resolve it.
  │  Does THREE things in one call:
  │  1. Classifies task_type + capability floor (A-D)
  │  2. Judges whether the task is specific enough to execute at all —
  │     if not, asks a clarifying question and STOPS. No dispatch made.
  │     Retries once on a parse failure before falling back locally
  │     (real LLM non-determinism, confirmed by direct reproduction).
  │  3. PROMPT ENGINEERING: rewrites the task into a sharper prompt for
  │     whichever model does the real work, grounded in real project
  │     context (e.g. "test our OpenAxis systems" resolves to the actual
  │     file paths of the actual test suites, not a vaguer restatement).
  │  Falls back to router/classifier.py (local keyword regex) if the
  │  triage model is unreachable entirely.
  ▼
ANTI-LOOP CHECK (only on a 2nd+ clarification round) — fast local
  │  word-overlap check first (free); if inconclusive, ONE real semantic
  │  model call asks "are these two questions about the same gap?" (catches
  │  genuine paraphrases like "which repository?" vs "what repo are you
  │  referring to?" that share almost no surface words). If the same
  │  question comes back a 3rd time, force_plan() proceeds with the best
  │  guess instead of looping forever, clearly labeled as a forced guess.
  ▼
SKILL SELECTION (router/skill_selector.py) — keyword + IDF-weighted search
  │  over all 3,812 skills, returns ~10 relevant ones. IDF weighting means a
  │  skill matching on a RARE, specific word ("graphql") beats one matching
  │  only on a common word ("app") that appears in hundreds of skills.
  ▼
AGENT SELECTION (router/agent_selector.py) — picks ONE agent persona as
  │  reference context, deduped by name. NEVER spawned as a subagent —
  │  explicit policy (policies/subagent_policy.json): cold-starting a
  │  subagent costs ~20x+ tokens vs. loading the persona inline, on any
  │  provider. The persona is just context for whichever model runs the task.
  ▼
MODEL SELECTION (router/model_selector.py) — hard capability-floor filter
  │  first (a Tier-A task NEVER silently gets a Tier-D model, no exceptions,
  │  tested), then health/budget filter (skip rate-limited/unavailable
  │  providers, short TTL, never a permanent blacklist), then PRIORITY BY
  │  TIER: Tier A prefers Claude (scarce, save it for what needs it), Tier B
  │  prefers GPT/Codex once authenticated, Tier C/D prefer OpenCode Go's
  │  workhorse tier. Cost is only a tiebreak within the same priority level.
  │  If nothing qualifies: BLOCKED, not a silent downgrade.
  ▼
SKILL PROMOTION (integrations/opencode_skill_promote.py) — for
  │  OpenCode-routed dispatches, any relevant OFFLINE-library skill gets
  │  junctioned into OpenCode's real discovery path right before dispatch,
  │  so the model actually sees what the selector picked (verified live:
  │  forced a dispatch, confirmed the junction existed afterward).
  ▼
DISPATCH (adapters/cli_dispatch.py) — shells out to the real CLI. Handles:
  │  - Windows .cmd shim resolution (codex/npm are .cmd files, not .exe —
  │    bare subprocess.run fails without this, root-caused and fixed)
  │  - Real cancellation via Ctrl+C (Popen + terminate, not just abandoned)
  │  - Session continuation for Claude only (`claude -c`, verified: told it
  │    a secret number in one process, asked it back in a separate process,
  │    got the right answer)
  ▼
FALLBACK (orchestrator/fallback.py) — on a real failure, marks that
  │  provider degraded (120s TTL) and re-plans once against the next-best
  │  candidate at the same-or-higher floor. Never downgrades.
  ▼
TASK STATE (task_state/state_store.py) — SQLite, WAL mode (survives
  │  concurrent writes from multiple legs), every task tracked with a
  │  globally-unique ID (fixed a real bug: session-scoped IDs used to
  │  collide and silently overwrite history across separate REPL runs).
  ▼
USAGE LOG (orchestrator/usage_logger.py) — real latency logged per call.
     Token/cost fields stay structurally null — no CLI exposes them in a
     capturable way — never faked.
```

## The frontend (`openaxis` command)

A persistent REPL modeled on Claude Code/OpenCode's UX, not a copy:
- Mascot glyph header (3-vector axis converging at a core — Claude/GPT/
  OpenCode Go/Ollama meeting at one router) + live auth summary + auth
  warnings, matching the "N servers need auth" convention.
- Boxed input prompt with a persistent hint line (cwd, pinned model).
- **Live slash-command suggestions as you type** (Windows `msvcrt`
  character-by-character input, stdlib, no new dependency) — gated behind
  `sys.stdin.isatty()` so it never breaks piped/automated invocations.
- Live spinner with elapsed time during real dispatches, with an
  ASCII-safe fallback for consoles that crash on the braille glyphs
  (found and fixed: Windows PowerShell's default cp1252 console).
- Step-by-step pipeline visibility (analyzing → skills → agent → model →
  dispatch), each a real stage actually running, not simulated for show.

### Commands (29 total)

| Command | What it does |
|---|---|
| *(plain text)* | auto-routed + executed task |
| `/plan <task>` | preview routing, no execution |
| `/compare [n\|aliases] <task>` | dispatch to 2-3 legs in parallel, blind-judged synthesis |
| `/continue <msg>` | reply to Claude's session (only leg with real continuation) |
| `/cancel <id>` | mark a stale task CANCELLED (Ctrl+C for one actually running) |
| `/retry <id>` | re-dispatch a FAILED/BLOCKED/CANCELLED task, fresh triage |
| `/model [alias\|clear]` | pin a specific model, bypassing the router |
| `/cd [dir]` | working directory real dispatches run in |
| `/tasks [filter]` / `/task <id>` | tracked history across all legs |
| `/status` | live auth/model/task/usage snapshot |
| `/explain [id]` | why the router decided what it decided |
| `/evolve [--apply]` | self-evolving benchmarks (see below) |
| `/auth` `/budget` `/usage` `/models` | dashboards |
| `/agents <q>` `/skills <q>` | direct registry search |
| `/verify <dir>` | real lint/test run, detects uv/npm correctly |
| `/benchmark <model>` | run the standard task bank against a model |
| `/sync` `/secrets` `/open` `/report` `/weakness` `/clear` `/help` | utilities |

## Multi-leg comparison (`/compare`)

Real feature, not "which answer is best" — dispatches to 2-3 legs in
**parallel threads** (genuine concurrency, each a real subprocess), then a
**blind-labeled judge**: the synthesis model sees "Response A/B/C" only,
provider identity revealed only after judgment (avoids reputation bias).
Output: CONSENSUS / DISAGREEMENT / UNIQUE insights / RECOMMENDATION, not a
single winner. Handles partial failure honestly (if one leg errors, says so,
synthesizes from what succeeded). Verified live: Claude Opus + OpenCode Go's
GLM model, both dispatched in parallel, real judge synthesis, correct
before/after label reveal.

## Self-evolving benchmarks (`/evolve`)

Mines the real usage log for evidence: an UNKNOWN model that's completed 5+
real production tasks with 80%+ success gets auto-promoted to Tier D
(proven reliable — never crashed) — but NEVER touches a model that already
has a human-judged tier from `run_benchmark.py`, and never auto-promotes
past D (real capability quality still needs a human reading the output, not
just "didn't error"). Every auto-promotion is clearly labeled `auto_evolved`
in the registry, distinct from spot-tested entries.

## Security & safety posture

- Secrets: never printed, only FOUND/MISSING checked.
- Skills: heuristic scan flagged 70/3,812 for review (all reviewed,
  confirmed false positives — security-topic skills discussing the exact
  patterns they scan for).
- Permissions: `opencode.jsonc` permission block set (edit/bash/task/skill).
- No subagent spawning, ever — explicit policy, not a bug.
- Prompt engineering never fabricates requirements onto a vague task —
  `engineered_prompt` stays empty when the task doesn't imply enough.

## Real bugs found and fixed this session (partial list, for calibration)

1. Claude was structurally invisible to the router (stale exclusion rule)
2. Router briefly over-corrected to route EVERYTHING to Claude (fixed to per-tier priority)
3. Tasks stuck showing VERIFYING forever even on success
4. Task IDs collided across sessions, silently overwriting history
5. Model names tracked as CLI aliases ("sonnet") not real registry IDs
6. `.cmd` shim resolution (Codex/npm) crashed on bare subprocess calls
7. Codex CLI itself had a broken Windows install (missing native binary) — fixed via reinstall
8. Skill selector: generic words ("app") drowned out specific ones ("graphql") — IDF fix
9. `opencode-zen` free tier had no cost-role entry — inverted the cost sort
10. SQLite default journal mode would've caused real lock contention across concurrent legs
11. Undefined-variable crash in the question-hint code path (caught live, fixed, regression test added)
12. Clarification loop had zero memory — every reply was re-triaged from scratch
13. Word-overlap-only repeat detection missed real paraphrases — upgraded to a real semantic check
14. Duplicate provider-prefix bug (recurred 3 separate times in different display paths — print_routing, cmd_explain, multi_dispatch — same root cause each time, now fixed everywhere it was found)
15. Spinner crashed on non-UTF8 consoles (Windows PowerShell's default cp1252)
16. Stale duplicate `ollama-local` provider entry left over from initial bootstrap

## Known real gaps (tracked, not hidden)

- GPT/Codex leg not yet authenticated (`codex login` pending, your call)
- 18 of 30 models still unbenchmarked
- Session continuation only works for Claude (Codex/OpenCode Go one-shot)
- Persistent task-queue UI panel (live checklist, message queueing while a
  task runs) — real architecture change (background dispatch thread),
  scoped but not built
- Quality-gated escalation (detect a subtly WRONG output, not just a crash,
  and escalate) — scoped but not built
- No formal 3-way concurrent dispatch test yet (blocked on Codex auth)
- Cost/token tracking structurally null (no CLI exposes it capturably)

## Where everything lives

```
C:\AI\control-plane\
  orchestrator\   repl.py (frontend), auto.py, smart_route.py, fallback.py,
                  multi_dispatch.py, consensus.py, self_evolve.py, verify.py
  router\         triage.py, clarity_gate.py, classifier.py, model_selector.py,
                  skill_selector.py, agent_selector.py, claude_code_selector.py
  adapters\       cli_dispatch.py
  integrations\   opencode_agent_sync.py, opencode_skill_promote.py
  registry\       agents/skills/models/providers (real data, not invented)
  policies\       capability_tiers.json, provider_roles.json, permissions.json,
                  subagent_policy.json, fallback_chains.json
  task_state\     state_store.py (SQLite, WAL)
  health\         budget_manager.py
  security\       secret_scan.py
  tests\          test_control_plane.py (30 tests), test_clarity_gate.py (13 tests)
  reports\        BASELINE_REPORT.md, SPEC_CODE_GAP_ANALYSIS.md, WEAKNESS_MAP.md,
                  BENCHMARK_RESULTS.md, FINAL_SYSTEM_REPORT.md
  docs\           this file, OPENCODE-HANDOFF.md, OVERSEER-RELATIONSHIP.md

C:\Users\Zoher\Desktop\Open Axis.lnk   -> double-click launcher (custom icon)
C:\Users\Zoher\.local\bin\openaxis.cmd -> global command, any terminal
C:\AI\local-stack\                     -> Ollama (live), Kokoro TTS (live, verified),
                                           self-host runbook for Supabase/Coolify/etc.
```
