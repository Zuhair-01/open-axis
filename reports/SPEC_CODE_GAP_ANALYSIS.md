# SPEC / CODE GAP ANALYSIS — 2026-08-15

Classification per this spec's own taxonomy: MATCHED / OUTDATED / MISSING /
PARTIALLY_IMPLEMENTED / BROKEN / UNVERIFIED / CONFLICTING.

| Subsystem (spec section) | Status | Notes |
|---|---|---|
| 3 provider legs (§2) | **MATCHED** | Claude/OpenCode Go authenticated and dispatching for real; Codex CLI healthy but not logged in (user action pending) |
| Pipeline shape (§4) | **MATCHED** | REPL → triage → skills → agent → floor → model rank → skill promotion → dispatch → fallback → task_state exists end-to-end, verified live this session |
| Capability tiers per-model not per-provider (§13) | **MATCHED (already true)** | Spec assumed this was a gap; registry already stores tier per model_id |
| Clarity gate: local fast-path before triage (§8) | **MISSING** | Every task pays a real ~5-15s model call, even obviously-clear ones like "run tests". Real, valid gap — implementing below. |
| Anti-loop protection (§9) | **PARTIALLY_IMPLEMENTED** | Thread-context carrying exists and is verified working (a 2nd clarification round asks a genuinely different question, not a repeat) — but there's no explicit "same question twice → stop and force a decision" hard-stop yet |
| Skill selection (§10) | **PARTIALLY_IMPLEMENTED** | Keyword+IDF works, verified. No semantic reranking, no trust/hash/version tracking per selection |
| Skill security/trust layer (§11) | **PARTIALLY_IMPLEMENTED** | Heuristic scan exists (`security/skill_security_scan_results.json`, 70 flagged out of 3,812, reviewed as false positives) but no formal TRUSTED/REVIEW_REQUIRED/BLOCKED classification, no hash/provenance tracking, no promotion audit log |
| Agent spawn policy (§12) | **CONFLICTING with spec, by explicit user decision** | Spec wants a cost/value decision rule for occasional spawning. Current policy is a HARD "never spawn, ever" per your own explicit instruction earlier this session (not an oversight — a deliberate simplification you asked for after subagent token cost concerns). Flagging the conflict rather than silently changing your decision. |
| Model registry fields (§14) | **PARTIALLY_IMPLEMENTED** | Has provider/model_id/capability_tier/access_type/task_types/notes. Missing: explicit QUALIFIED/UNQUALIFIED/FAILED/DISABLED status enum, task-type-specific scores, context capability, last-benchmark-date field |
| Model selection engine explainability (§15) | **PARTIALLY_IMPLEMENTED** | Selection IS explainable (pipeline stages print classification/skills/agent/model live) but not in the exact structured format spec describes (ranked candidates with scores) |
| Weighted routing policy profiles (§16-17) | **MISSING** | Current selection is floor→priority-tier→cost, not a configurable weighted-scoring system with CRITICAL/BULK/URGENT profiles. This is a legitimate, large feature, not implemented. |
| Premium capacity reserve bands (§17) | **MISSING** | No % Claude quota reserve bands — correctly so, since neither Anthropic nor OpenAI expose real remaining quota; spec itself says "if unknown, use UNKNOWN" which is what's happening (health/budget shows `?`, not a fake %) |
| Budget manager 3-way split (§18) | **PARTIALLY_IMPLEMENTED** | Has OBSERVED USAGE (real, from usage log). No PROVIDER-REPORTED (none of the 3 CLIs expose it). No ESTIMATED REMAINING calculation yet. |
| Typed fallback failure classes (§19-20) | **MATCHED** | `RETRYABLE`/`NON_RETRYABLE` error sets already exist in `orchestrator/fallback.py` and `policies/fallback_chains.json`; hard capability-floor-never-crossed rule verified via tests |
| Handoff packet (§21) | **PARTIALLY_IMPLEMENTED** | `task_state` stores most required fields (objective, plan, completed_steps, modified_files, fallback_history) but not as one standardized packet object; no `do_not_repeat`/`known_constraints` fields |
| Unified session abstraction (§22) | **MISSING (mostly)** | Only Claude has real continuation (`claude -c`, verified working). No `start_session`/`fork_session`/`export_session` abstraction layer; Codex/OpenCode continuation unexplored |
| Benchmark system depth (§23-24) | **PARTIALLY_IMPLEMENTED** | 11/25 models benchmarked with real judged tasks across a small task bank (8 tasks, tiers A-D). No deterministic-check-first judging, no CODING/REASONING/AGENTIC/RESEARCH/BUSINESS category split, no independent-model judging for critical benchmarks |
| Historical routing learning (§25) | **MISSING** | No performance-by-task-type-by-model learning store. Genuinely not built. |
| Concurrency testing (§26) | **UNVERIFIED** | WAL mode is on (built specifically for this), but no actual 1/3/5/10/20-concurrent-task test has been run |
| Atomicity (§27) | **PARTIALLY_IMPLEMENTED** | SQLite transactions via WAL; no atomic-write pattern for the JSON registry files themselves (a crash mid-write to model_registry.json could corrupt it — not tested) |
| Config/secrets/cache/logs separation (§28) | **MATCHED** | Already cleanly separated by directory (`config/`, `task_state/`, `logs/`, `reports/`); secrets never stored in-repo, only FOUND/MISSING checked |
| OpenCode version discipline (§29, §65) | **MATCHED** | Verified stable `opencode` binary only, no `opencode2` present, confirmed via `opencode --version`/`--help` before any integration work this session |
| OpenCode permissions native reuse (§30-32) | **PARTIALLY_IMPLEMENTED** | `opencode.jsonc` permission block set (edit/bash/task/skill), but not the fine-grained per-skill or external_directory-aware policy spec describes |
| Prompt injection defense (§33) | **PARTIALLY_IMPLEMENTED** | Documented policy + heuristic skill scan exists; no actual adversarial test suite run against it |
| Verification: model-says vs system-verified (§34-35) | **MATCHED** | `orchestrator/verify.py` runs real lint/test commands (not model self-report), correctly detects uv/npm projects (fixed a real bug doing so), tested against a live 515-test project |
| `/status`, `/health`, `/routing`, `/explain` commands (§38-43) | **MISSING** | Not built yet — implementing `/status` and `/explain` below as the highest-value pair |
| `/cancel`, `/retry` (§46-47) | **MISSING** | Not built. Real gap for anything long-running. |
| Artifact management (§48) | **MISSING** | No dedicated artifact tracking beyond task_state's `modified_files` field |
| Documentation set (§56) | **PARTIALLY_IMPLEMENTED** | README/ARCHITECTURE/OPERATIONS/SECURITY/TROUBLESHOOTING/CHANGELOG exist. ROUTING.md/FALLBACK.md/BENCHMARKS.md/SKILLS.md/AGENTS.md/PROVIDERS.md as separate files do not — that content currently lives inside the broader docs instead |
| Interface boundaries / abstract classes (§61) | **MISSING** | Current modules are plain functions/scripts, not formal `ProviderAdapter`/`ModelRegistry` class interfaces. Works today; would matter more with a 2nd implementation of any of these (e.g. a real semantic skill search) |

## Honest summary

Core pipeline: solid, real, tested, verified live multiple times this
session. The gaps that matter most are the ones this spec correctly flags:
**no local fast-path before triage** (real latency cost on every single
task) and **no observability commands** (`/status`, `/explain`). Those two
get built now. Everything else in this list is a legitimate roadmap item,
not something to fake as "done."
