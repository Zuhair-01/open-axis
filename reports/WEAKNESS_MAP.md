# Weakness Map — audited 2026-08-15 (updated: Open Axis frontend pass)

## Integration audit (frontend build pass)

Real risk during the Open Axis frontend build: subsystems built earlier this
session (fallback engine, skill promotion, Claude-Code model/effort advisor)
were fully tested in isolation but never actually called from the live
execution path (`repl.py` -> `auto.py`). Systematically checked by grepping
every `.py` module in the control plane against the entrypoint chain. Found
and fixed:

- **`orchestrator/fallback.py`'s health/retry logic was disconnected** -
  `auto()` did a single dispatch with no retry. Fixed: a real dispatch
  failure now marks that provider degraded and re-plans once against the
  next-best candidate (skipped when the user explicitly pinned a model via
  `/model` - an explicit choice is reported on failure, not silently rerouted).
- **`integrations/opencode_skill_promote.py` was disconnected** - the smart
  skill selector computed relevant offline-library skills but nothing ever
  junctioned them into OpenCode's discovery path before real execution, so
  the model never actually saw them. Fixed and verified live: forced an
  OpenCode Go dispatch for a WCAG task, confirmed `wcag-audit-patterns`
  (an offline-library skill) was junctioned in before the call.
- **`router/claude_code_selector.py`'s recommendation was computed but never
  displayed** - fixed, now shown as a footnote on `/plan`.
- `integrations/opencode_agent_sync.py` and `security/secret_scan.py` were
  legitimately standalone (maintenance/audit tools, not per-task
  dependencies) - not bugs, but added `/sync` and `/secrets` commands so
  every module built this session is reachable from the frontend, none of
  it orphaned.


Real audit, not a guess list — each item below was either found by running a
check against the actual files/DB, or is a known limitation stated plainly
when it was built. Fixed items are marked; open items have a concrete next
step, not just a complaint.

## Fixed this pass (real bugs, verified)

1. **`opencode-zen` (free tier) had no cost-role entry** → `model_selector.py`'s
   cost sort silently gave it the *worst* possible rank, so the free tier
   could never out-compete the paid `opencode-go` tier on cost — backwards
   from intent. Fixed: added the missing role in `provider_roles.json`, verified
   `model_providers - role_providers` is now empty.
2. **SQLite in default `delete` journal mode** → serializes every writer
   behind one file lock. Fine solo, but once Codex is a third concurrent
   leg dispatching real tasks, this becomes real `database is locked`
   failures. Fixed: switched to WAL mode in `state_store.py`, verified
   persisted (`PRAGMA journal_mode` → `wal`).
3. **Test suite polluted production `health/state.json`** (fixed earlier
   this session) — `CONTROL_PLANE_HEALTH_PATH` isolation added.
4. **`verify.py` guessed wrong test command for uv-managed projects** (fixed
   earlier) — now detects `uv.lock` and uses `uv run pytest`.
5. **Skill selector drowned specific terms under generic ones** ("app"
   swamping "graphql") — fixed with IDF weighting, verified the fix actually
   changed the result on the failing query.
6. **`opencode-zen` (free tier) missing role entry** → cost sort bug, same
   root cause as item 1 above but a separate provider. Fixed alongside it.
7. **Codex auth-check PATH resolution** — `claude`/`opencode` are real
   `.exe`s, but npm-installed `codex` is a `.cmd` batch shim, which Python's
   `subprocess.run` can't launch directly without `cmd /c` (this is a known
   Windows/Python gotcha, not an OpenCode/Claude issue). Fixed with
   `shutil.which()` + explicit `cmd /c` routing when the resolved binary is
   `.cmd`/`.bat`. This is what actually surfaced item 8 below — the fix
   worked, and immediately found a real problem it had been silently hiding.
8. **Codex CLI itself has a broken Windows install** — `@openai/codex@0.147.0`
   (auto-updated mid-session from 0.144.1) is missing its
   `@openai/codex-win32-x64` optional native dependency; `codex --version`
   and `codex doctor` both fail with the same error directly, not just
   through our wrapper. Running `npm install -g @openai/codex@latest` to fix
   - this is the actual blocker for the GPT/Codex leg landing, more than
   anything in this control plane.

## Open — real, with a concrete next step

| # | Weakness | Concrete fix, when it's worth doing |
|---|---|---|
| 1 | ~~3 agent duplicate-name groups returned twice by the selector~~ — **FIXED**: `agent_selector.py` now dedupes by name, preferring `agents_live` over `agents_library` on collision. Verified against real query. | Done. |
| 2 | ~~`codex login status` auth-check fragile~~ — **FIXED** (see fixed-items list above, #7). Root-caused: `.cmd` shim needs `cmd /c` routing. | Done. |
| 2b | **Codex CLI's Windows install is broken right now** (item 8 above) — real, external, not our bug. | Reinstalling via `npm install -g @openai/codex@latest` (in progress). Once done, re-run `check_auth('openai')` to confirm it flips to `NOT_AUTHENTICATED` (meaning the binary works, just not logged in yet) before you run `codex login`. |
| 3 | ~~Classifier small-vocabulary keyword matching~~ — **IMPROVED**: expanded from ~10 sparse categories to richer patterns per category plus a new PERFORMANCE type. Verified fix on the exact failing case ("REST vs GraphQL tradeoffs" now classifies RESEARCH, was UNKNOWN). Still keyword-based (no embeddings) - will still miss sufficiently novel phrasing. | Further improvement path (embeddings via local Ollama) still open if this keeps being a friction point. |
| 4 | ~~`verify.py` only checked project root~~ — **FIXED**: added depth-limited (3 levels) recursive scan skipping noise dirs, runs checks per detected subproject with labeled output. | Done. |
| 4b | **`npm` is also a `.cmd` shim** (confirmed via `where npm`) - same root cause as Codex's bug. `verify.py`'s npm checks were silently mis-reporting "tool not installed" for any Node project. | **FIXED** alongside item 4 - same `_resolve()` pattern applied, verified against a real project (`clip-platform/web`): npm test/lint both ran for real, lint even surfaced 2 real bugs in that project (impure `Date.now()` calls during React render). |
| 5 | **No cleanup for promoted skill junctions** — `opencode_skill_promote.py` creates junctions under `~/.config/opencode/skills/` and never removes stale ones. Harmless (junctions are just pointers, real disk cost ~0) but will accumulate over months of varied tasks. | Add a `--prune` mode that removes junctions untouched for N days, run manually or on a schedule. Not urgent. |
| 6 | **Cost/token figures are structurally null** — `usage_logger.py` logs real latency now, but OpenCode's CLI doesn't expose token counts or dollar cost in its output, so those fields stay `null` forever unless a different capture method is used (e.g. `--format json` from `opencode run` might expose more — untested). | Worth 10 minutes checking `opencode run --format json` output structure once Codex is live and there's a reason to compare real cost across all three legs. |
| 7 | **No loop-protection enforcement mechanism**, only a documented policy (`fallback_chains.json`'s `max_retries_per_chain`, honored inside `fallback.py`, but nothing catches identical repeated *dispatch* calls at the `cli_dispatch.py` level itself). | Add a lightweight recent-calls cache (task_id + prompt hash + timestamp) in `cli_dispatch.dispatch()` that refuses an identical call within N seconds. Worth doing before heavy real usage, not urgent for current low volume. |
| 8 | **17 of 26 OpenCode Go/Zen models still unbenchmarked** (documented, not a bug) — correctly excluded from routing. | Extend with `scripts/run_benchmark.py <model_id>` as real tasks come up, or in a dedicated pass. |
| 9 | **Skill/agent relevance is keyword-only, no embeddings** (documented limitation, same root cause as #3). | Same fix path as #3 if it becomes a real friction point. |

## Priority for "Codex lands smoothly"

**#2 is the one to actually fix before `codex login` happens** — everything
else is either already fixed, cosmetic, or independent of the third leg
landing cleanly. Recommend: re-run `check_auth('openai')` right now (before
Codex is even logged in) to see if the `FileNotFoundError` flakiness still
reproduces, and fix the PATH issue if so — so the moment you finish
`codex login`, the system detects it correctly on the first try.
