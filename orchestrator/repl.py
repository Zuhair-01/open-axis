"""OPEN AXIS - the actual frontend. A persistent interactive session, in the
spirit of Claude Code / OpenCode's own UX: you type a task, it routes + runs
it, output prints inline, you keep going. Slash-commands for utilities,
matching that same convention (/model, /agents, /skills, /usage, /clear...).

ANSI escape codes only - no new dependency (rich/textual not installed, and
Windows Terminal/pwsh7 render ANSI natively).

Resilience: every command handler is wrapped so a single failure (a crashed
dispatch, a missing file) prints an error and returns to the prompt - it
never takes down the whole session, the same way Claude Code doesn't die
from one failed tool call.
"""
import json
import os
import subprocess
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path

CP = Path(r"C:\AI\control-plane")
sys.path.insert(0, str(CP))
from orchestrator.auto import auto, ALIAS_MAP
from orchestrator.multi_dispatch import dispatch_multi
from orchestrator.consensus import judge
from router.model_selector import select_top_n_diverse
from orchestrator.smart_route import plan, force_plan
from orchestrator.verify import verify
from orchestrator.usage_logger import summarize as usage_summarize
from router.skill_selector import select_skills
from router.agent_selector import select_agents
from router.classifier import classify
from health.budget_manager import render_dashboard
from adapters.cli_dispatch import check_auth, CLI_COMMANDS, dispatch as cli_dispatch
from integrations.opencode_agent_sync import main as sync_agents
from security.secret_scan import check_env, check_files
from task_state.state_store import list_tasks, get_task

RESET = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"

TIER_COLOR = {"A": MAGENTA, "B": CYAN, "C": GREEN, "D": DIM}
MODEL_ALIASES = {  # /model shortcuts -> (provider, model_id, tier)
    "opus": ("anthropic", "claude-opus-5", "A"),
    "sonnet": ("anthropic", "claude-sonnet-5", "B"),
    "haiku": ("anthropic", "claude-haiku-4-5-20251001", "C"),
    "kimi-k3": ("opencode-go", "opencode-go/kimi-k3", "A"),
    "qwen-max": ("opencode-go", "opencode-go/qwen3.8-max", "A"),
    "kimi-code": ("opencode-go", "opencode-go/kimi-k2.7-code", "B"),
    "glm": ("opencode-go", "opencode-go/glm-5.1", "C"),
    "mimo": ("opencode-go", "opencode-go/mimo-v2.5", "C"),
}

def _c(text, color):
    return f"{color}{text}{RESET}"

EXAMPLE_TASKS = [
    "fix the login bug",
    "audit this repo for security issues",
    "write tests for the payment module",
    "explain the tradeoffs between REST and GraphQL",
]

VERSION = "0.1"

GLYPH = [
    ("   ◢█◣   ", CYAN),
    ("  ◢ █ ◣  ", CYAN),
    (" ◢  █  ◣ ", MAGENTA),
    ("◥───┴───◤", MAGENTA),
]

def header(cwd: str):
    import random
    legs_live = 0
    not_authed = []
    for p in CLI_COMMANDS:
        r = check_auth(p)
        if "AUTHENTICATED" in r["status"] and "NOT" not in r["status"]:
            legs_live += 1
        elif r["status"] in ("NOT_AUTHENTICATED", "CLI_NOT_INSTALLED"):
            not_authed.append(p)

    info_lines = [
        _c("Open Axis", BOLD) + _c(f"  v{VERSION}", DIM),
        _c(f"{legs_live}/{len(set(CLI_COMMANDS))} legs live", GREEN if legs_live else RED) +
            _c("  ·  Claude Pro + OpenCode Go", DIM),
        _c(cwd, DIM),
    ]
    for (glyph_text, glyph_color), text in zip(GLYPH, info_lines + [""]):
        print(f"  {_c(glyph_text, glyph_color)}   {text}")
    print()

    if not_authed:
        print(_c(f"  ! {len(not_authed)} leg(s) need auth ({', '.join(sorted(set(not_authed)))}) · run /auth", YELLOW))
        print()

    print(_c(f'  | Try "{random.choice(EXAMPLE_TASKS)}"  ·  /help for commands  ·  /model to pin', DIM))
    print()

def print_routing(task_type, tier, provider, model, confidence, pinned=False):
    tc = TIER_COLOR.get(tier, RESET)
    tag = _c(" [pinned]", YELLOW) if pinned else ""
    print(f"{DIM}route:{RESET} {task_type} {_c(f'[tier {tier}]', tc)} "
          f"{DIM}confidence={confidence}{RESET}{tag}")
    label = model if "/" in model else f"{provider}/{model}"
    print(f"{DIM}-> {RESET}{_c(label, BOLD)}")

# Single source of truth for help text AND the live "/" suggestion list
# (real feature added 2026-08-15, matching Claude Code's own slash-command
# autocomplete). (command, args_hint, short_description)
COMMANDS = [
    ("/help", "", "this list"),
    ("/auth", "", "check Claude/Codex/OpenCode Go auth status"),
    ("/budget", "", "model budget dashboard"),
    ("/usage", "", "usage/cost summary (real logged calls)"),
    ("/model", "", "show current pin"),
    ("/model", "<alias>", "pin a model (opus, sonnet, haiku, kimi-k3, qwen-max, kimi-code, glm, mimo)"),
    ("/model clear", "", "unpin, return to auto-routing"),
    ("/cd", "<dir>", "set the working directory real tasks dispatch into"),
    ("/continue", "<msg>", "reply to Claude's most recent session (anthropic only so far)"),
    ("/cancel", "<id>", "mark a stuck/stale task CANCELLED (Ctrl+C stops one running now)"),
    ("/retry", "<id>", "re-dispatch a FAILED/BLOCKED/CANCELLED task with fresh triage"),
    ("/compare", "[n|aliases] <task>", "dispatch to 2-3 legs in parallel, blind-judged synthesis"),
    ("/agents", "<query>", "search the 301-agent registry directly"),
    ("/skills", "<query>", "search the 3,812-skill registry directly"),
    ("/plan", "<task>", "show routing decision only, don't execute"),
    ("/models", "", "list benchmarked models by tier"),
    ("/verify", "<dir>", "run a project's real tests/lint"),
    ("/benchmark", "<model>", "run the standard task bank against a model"),
    ("/tasks", "[filter]", "tracked task history (filter by provider or STATUS)"),
    ("/task", "<id>", "full detail on one tracked task"),
    ("/status", "", "live system status (auth, models, recent tasks, usage)"),
    ("/explain", "[id]", "why the router decided what it decided"),
    ("/report", "", "static system status report file"),
    ("/weakness", "", "known weaknesses / open issues"),
    ("/open", "", "open the control-plane folder"),
    ("/sync", "", "re-sync ~/.claude agents into OpenCode"),
    ("/evolve", "[--apply]", "self-evolving benchmarks: promote proven models from real usage"),
    ("/secrets", "", "credential FOUND/MISSING check (never prints values)"),
    ("/clear", "", "reset this session's task counter"),
    ("/exit", "", "leave (also /quit)"),
]

def cmd_help():
    print(f"\n{BOLD}Commands:{RESET}")
    for cmd, args, desc in COMMANDS:
        label = f"{cmd} {args}".strip() if args else cmd
        # pad THEN colorize - padding a string that already contains ANSI
        # escape codes counts the invisible escape chars as width, breaking
        # alignment (same bug class fixed earlier for /tasks columns)
        padded = f"{label:<28s}"
        print(f"  {_c(padded, CYAN)} {desc}")
    print(f"\nAnything else you type is treated as a task and auto-routed + executed.\n")

def cmd_auth():
    for p in CLI_COMMANDS:
        r = check_auth(p)
        status = r["status"]
        if status in ("NOT_AUTHENTICATED", "CLI_NOT_INSTALLED"):
            color = RED
        elif "AUTHENTICATED" in status:
            color = GREEN
        else:
            color = YELLOW
        print(f"  {p:14s} {_c(status, color)}")

def cmd_models():
    models = json.loads((CP / "registry/models/model_registry.json").read_text(encoding="utf-8"))["models"]
    by_tier = {}
    for m in models:
        t = m.get("capability_tier", "UNKNOWN")
        by_tier.setdefault(t, []).append(m["model_id"])
    for t in ["A", "B", "C", "D", "UNKNOWN"]:
        if t in by_tier:
            print(f"  {_c(t, TIER_COLOR.get(t, RESET))}: " + ", ".join(by_tier[t]))

def cmd_usage():
    s = usage_summarize()
    if s["events"] == 0:
        print(_c("No real dispatches logged yet.", DIM))
        return
    print(f"Total logged calls: {s['events']}")
    for prov, stats in s["by_provider"].items():
        print(f"  {prov:14s} calls={stats['events']:<4d} errors={stats['errors']:<3d} "
              f"cost=${stats['cost_usd']:.4f}" + (_c("  (cost tracking is structurally null - see WEAKNESS_MAP.md)", DIM) if stats['cost_usd'] == 0 else ""))

def cmd_status():
    """Real observability, computed from actual data - no fake percentages."""
    print(_c("PROVIDER AUTH", BOLD))
    for p in sorted(set(CLI_COMMANDS)):
        r = check_auth(p)
        status = r["status"]
        color = GREEN if "AUTHENTICATED" in status and "NOT" not in status else RED if status in ("NOT_AUTHENTICATED", "CLI_NOT_INSTALLED") else YELLOW
        print(f"  {p:14s} {_c(status, color)}")

    models = json.loads((CP / "registry/models/model_registry.json").read_text(encoding="utf-8"))["models"]
    qualified = [m for m in models if m.get("capability_tier") != "UNKNOWN"]
    print(f"\n{_c('MODELS', BOLD)}\n  {len(models)} registered, {len(qualified)} qualified (real benchmark data), {len(models) - len(qualified)} unbenchmarked (excluded from routing)")

    recent = list_tasks(limit=50)
    by_status = {}
    fallback_count = 0
    for t in recent:
        by_status[t["status"]] = by_status.get(t["status"], 0) + 1
        if t.get("fallback_history") and t["fallback_history"] not in ("[]", None):
            fallback_count += 1
    print(f"\n{_c('RECENT TASKS', BOLD)} (last {len(recent)})")
    for status, count in sorted(by_status.items(), key=lambda x: -x[1]):
        print(f"  {status:14s} {count}")
    if recent:
        print(f"  {DIM}fallback occurred in {fallback_count}/{len(recent)}{RESET}")

    usage = usage_summarize()
    print(f"\n{_c('USAGE', BOLD)}\n  {usage['events']} real dispatches logged this install")

def cmd_explain(task_id: str = None):
    """Why did the router decide what it decided - from actual stored state,
    not a re-derived guess."""
    if not task_id:
        recent = list_tasks(limit=1)
        if not recent:
            print(_c("no tracked tasks yet", DIM))
            return
        t = recent[0]
    else:
        t = get_task(task_id)
        if not t:
            print(_c(f"no task '{task_id}' found", RED))
            return

    print(f"{_c('task', CYAN)}: {t['task_id']}")
    print(f"{_c('objective', CYAN)}: {t.get('objective')}")
    cls = t.get("classification")
    if cls:
        try:
            c = json.loads(cls)
            print(f"{_c('classified as', CYAN)}: {c.get('task_type')} "
                  f"[floor {c.get('required_capability_floor')}] "
                  f"via {c.get('source', 'unknown')}")
        except (json.JSONDecodeError, TypeError):
            print(f"{_c('classification', CYAN)}: {cls}")
    model_label = t.get("model") or "?"
    # Same bug class fixed earlier in print_routing(): model_id from the
    # registry already self-describes for opencode ("opencode-go/glm-5.1"),
    # only bare anthropic aliases need the provider prefixed on.
    routed_label = model_label if "/" in model_label else f"{t.get('provider')}/{model_label}"
    print(f"{_c('routed to', CYAN)}: {routed_label}")
    if t.get("fallback_history") and t["fallback_history"] not in ("[]", None):
        print(f"{_c('fallback', YELLOW)}: {t['fallback_history']}")
    print(f"{_c('final status', CYAN)}: {t.get('status')}")

CANCELLABLE_STATUSES = {"EXECUTING", "WAITING", "PLANNING", "FALLING_BACK", "VERIFYING", "CREATED"}
RETRYABLE_STATUSES = {"FAILED", "BLOCKED", "CANCELLED"}

def cmd_cancel(task_id: str):
    """Real technical constraint: a task ACTIVELY running right now can only
    be interrupted with Ctrl+C (the REPL is single-threaded, blocked on the
    subprocess - a slash command physically cannot reach it mid-flight).
    What /cancel DOES do for real: mark a stale task (stuck EXECUTING/
    WAITING from a session that crashed or was killed externally, not a
    clean exit) as CANCELLED, so it stops cluttering /tasks and /status as
    if still active."""
    t = get_task(task_id)
    if not t:
        print(_c(f"no task '{task_id}' found", RED))
        return
    if t["status"] not in CANCELLABLE_STATUSES:
        print(_c(f"task is already {t['status']} - nothing to cancel", DIM))
        return
    from task_state.state_store import update_task
    update_task(task_id, status="CANCELLED")
    print(_c(f"marked {task_id} CANCELLED", YELLOW))
    print(_c("(if this task is ACTUALLY running right now in this session, "
              "use Ctrl+C instead - that's the only real interrupt for an "
              "in-flight subprocess)", DIM))

def cmd_compare(arg_str: str, task_id: str, cwd: str):
    """Real feature added 2026-08-15 (multi-leg consensus, not subagent
    spawning - separate provider CLIs dispatched in parallel threads, same
    class of operation as sequential dispatch, just concurrent). Syntax:
    /compare <task>              -> 2 diverse legs, auto-picked by floor
    /compare 3 <task>            -> 3 diverse legs
    /compare opus,glm <task>     -> explicit legs by /model alias"""
    arg_str = arg_str.strip()
    n = 2
    legs_arg = None
    if arg_str[:1].isdigit():
        n_str, _, rest = arg_str.partition(" ")
        if n_str in ("2", "3"):
            n, arg_str = int(n_str), rest.strip()
    elif "," in arg_str.split(" ", 1)[0]:
        legs_arg, _, arg_str = arg_str.partition(" ")

    task = arg_str.strip()
    if not task:
        print(_c("usage: /compare [n|alias1,alias2] <task>", RED))
        return

    if legs_arg:
        aliases = [a.strip() for a in legs_arg.split(",")]
        unknown = [a for a in aliases if a not in MODEL_ALIASES]
        if unknown:
            print(_c(f"unknown alias(es): {', '.join(unknown)}. Options: {', '.join(MODEL_ALIASES)}", RED))
            return
        legs = [{"provider": MODEL_ALIASES[a][0], "model_id": MODEL_ALIASES[a][1]} for a in aliases]
    else:
        classification = classify(task)
        legs = select_top_n_diverse(classification["required_capability_floor"], n)
        if len(legs) < 2:
            print(_c(f"only {len(legs)} authenticated/qualified provider(s) available at this task's "
                      f"floor - need at least 2 to compare. Use explicit aliases instead: "
                      f"/compare opus,glm {task}", RED))
            return
        print(_c(f"auto-picked legs for tier {classification['required_capability_floor']}: "
                  + ", ".join(f"{l['provider']}/{l['model_id']}" for l in legs), DIM))

    print(_c(f"dispatching to {len(legs)} legs in parallel...", DIM))
    stop_event = threading.Event()
    spinner_thread = threading.Thread(target=_spin, args=(stop_event, f"waiting on {len(legs)} legs"), daemon=True)
    spinner_thread.start()
    try:
        multi_result = dispatch_multi(task, legs, task_id, cwd=cwd)
    finally:
        stop_event.set()
        spinner_thread.join()

    for leg_label, r in multi_result["results"].items():
        color = GREEN if r["status"] == "OK" else RED
        elapsed_label = f"{r['elapsed_s']}s"
        print(f"\n{_c(leg_label, BOLD)} {_c(r['status'], color)} {_c(elapsed_label, DIM)}")
        print(r["output"].strip()[:1500])

    print(_c("\nsynthesizing (blind judge, provider identity hidden until after judgment)...", DIM))
    verdict = judge(task, multi_result["results"], task_id)

    print(f"\n{_c('=== SYNTHESIS ===', BOLD)}")
    if verdict["status"] == "INSUFFICIENT_LEGS":
        print(_c(verdict["reason"], RED))
        return
    if verdict["status"] == "JUDGE_FAILED":
        print(_c(verdict["reason"], YELLOW))
        for label, leg in verdict["label_map"].items():
            print(f"  {label} = {leg}")
        return

    if verdict.get("consensus"):
        print(f"{_c('CONSENSUS:', GREEN)} {verdict['consensus']}")
    if verdict.get("disagreements"):
        print(f"{_c('DISAGREEMENT:', YELLOW)} {verdict['disagreements']}")
    if verdict.get("unique_insights"):
        print(f"{_c('UNIQUE:', CYAN)} {verdict['unique_insights']}")
    if verdict["failed_legs"]:
        print(_c(f"UNAVAILABLE: {', '.join(verdict['failed_legs'])} - synthesis based on remaining legs only", DIM))
    print(f"{_c('RECOMMENDATION:', BOLD)} {verdict.get('recommendation', '')}")
    print(_c(f"(confidence: {verdict.get('confidence', 'unknown')})", DIM))
    print(f"\n{_c('who said what:', DIM)}")
    for label, leg in verdict["label_map"].items():
        print(f"  {label} = {leg}")

def cmd_retry(task_id: str, cwd: str):
    t = get_task(task_id)
    if not t:
        print(_c(f"no task '{task_id}' found", RED))
        return
    if t["status"] not in RETRYABLE_STATUSES:
        print(_c(f"task is {t['status']}, not FAILED/BLOCKED/CANCELLED - nothing to retry", DIM))
        return
    objective = t.get("objective")
    if not objective:
        print(_c("no objective stored for this task - can't retry", RED))
        return
    print(_c(f"retrying: {objective}", DIM))
    print(_c("(fresh triage, not reusing the old classification - the prior "
              "attempt's failure may mean the old classification was wrong too)", DIM))
    run(objective, f"{task_id}-retry-{uuid.uuid4().hex[:6]}", cwd=cwd)

def cmd_tasks(filter_arg: str = ""):
    provider = filter_arg.strip() if filter_arg.strip() in ("anthropic", "openai", "opencode-go", "opencode-zen") else None
    status = filter_arg.strip().upper() if filter_arg.strip() and not provider else None
    tasks = list_tasks(limit=20, provider=provider, status=status)
    if not tasks:
        print(_c("no tracked tasks yet", DIM))
        return
    status_color = {"COMPLETED": GREEN, "FAILED": RED, "BLOCKED": RED, "CANCELLED": RED,
                     "EXECUTING": YELLOW, "FALLING_BACK": YELLOW, "WAITING": YELLOW,
                     "VERIFYING": CYAN, "PLANNING": DIM, "CREATED": DIM}
    for t in tasks:
        ts = datetime.fromtimestamp(t["updated_at"]).strftime("%H:%M:%S")
        sc = status_color.get(t["status"], RESET)
        status_padded = f"{t['status']:<10s}"
        model = t.get("model") or "-"
        obj = (t.get("objective") or "")[:48]
        print(f"  {DIM}{ts}{RESET}  {_c(status_padded, sc)} {DIM}{(t.get('provider') or '-'):12s}{RESET} "
              f"{model:28s} {obj}")
    print(_c(f"\n({len(tasks)} shown - /task <id> for full detail, filter by provider or status e.g. /tasks FAILED)", DIM))

def cmd_task_detail(task_id: str):
    t = get_task(task_id)
    if not t:
        print(_c(f"no task '{task_id}' found", RED))
        return
    for k in ["task_id", "status", "provider", "model", "agent", "objective",
              "classification", "plan", "completed_steps", "modified_files", "fallback_history"]:
        v = t.get(k)
        if v:
            print(f"  {_c(k, CYAN)}: {v}")
    dur = t["updated_at"] - t["created_at"]
    print(f"  {_c('duration', CYAN)}: {dur:.1f}s")

def cmd_agents(query: str):
    results = select_agents(query)[:10]
    if not results:
        print(_c("no matches", DIM))
        return
    for a in results:
        print(f"  {a['name']:35s} [{a['source']}]")

def cmd_skills(query: str):
    results = select_skills(query, top_n=10)
    if not results:
        print(_c("no matches", DIM))
        return
    for s in results:
        desc = (s.get("description") or "")[:70]
        print(f"  {s['id']:30s} [{s['source']}]  {desc}")

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

def _spin(stop_event: threading.Event, label: str, cancel_event: threading.Event = None,
          queued: list = None):
    """Live progress feedback while a real dispatch runs (10-60s+, was
    silent/dead-feeling before - the exact gap flagged comparing this to
    Claude Code's own 'Reticulating... (1m 35s)' live indicator).

    Real feature added 2026-08-15 (Esc-to-interrupt + type-ahead queueing):
    this spinner is the SOLE writer to its terminal line (single `\\r`-owned
    row), which is what makes it safe to also read keystrokes here instead
    of running a second concurrent input reader - two things independently
    writing/redrawing the same line is what actually causes terminal
    corruption, not keystroke-reading itself. msvcrt.kbhit() is non-blocking
    so this costs nothing when the user isn't typing. Esc or Ctrl+C sets
    cancel_event (consumed by cli_dispatch.dispatch()'s poll loop to
    actually kill the child process); Enter appends the typed line to
    `queued` and clears the buffer, letting the user queue their next task
    exactly like Claude Code does while a turn is still running - it does
    NOT start executing until the current dispatch finishes."""
    # Real bug fixed 2026-08-15: braille spinner glyphs crash on any console
    # using cp1252 (default Windows PowerShell host, not just Windows
    # Terminal) with UnicodeEncodeError - the crash was silent-ish (caught
    # by Python's default thread exception handler, printed a traceback but
    # didn't kill the main thread), yet still noisy/alarming and left no
    # visible progress indicator at all on those consoles. ASCII fallback.
    ascii_frames = ["|", "/", "-", "\\"]
    start = time.time()
    i = 0
    use_ascii = False
    typed = ""
    can_read_keys = _HAS_MSVCRT and sys.stdin.isatty()
    while not stop_event.is_set():
        if can_read_keys:
            while msvcrt.kbhit():
                ch = msvcrt.getwch()
                if ch in ("\x1b", "\x03") and cancel_event is not None:
                    cancel_event.set()
                elif ch in ("\r", "\n"):
                    if typed.strip() and queued is not None:
                        queued.append(typed.strip())
                    typed = ""
                elif ch in ("\x08", "\x7f"):
                    typed = typed[:-1]
                elif ch in ("\x00", "\xe0"):
                    msvcrt.getwch()  # swallow special/arrow key second byte
                elif ch.isprintable():
                    typed += ch
        elapsed = time.time() - start
        frames = ascii_frames if use_ascii else SPINNER_FRAMES
        frame = frames[i % len(frames)]
        interrupt_note = f"{DIM}  [esc to interrupt]{RESET}" if cancel_event is not None else ""
        queued_note = f"{YELLOW}  {len(queued)} queued{RESET}" if queued else ""
        typed_note = f"{DIM}  next> {RESET}{typed}" if typed else ""
        try:
            sys.stdout.write(f"\r{_c(frame, CYAN)} {DIM}{label} ({elapsed:0.1f}s){RESET}"
                              f"{interrupt_note}{queued_note}{typed_note}   ")
            sys.stdout.flush()
        except UnicodeEncodeError:
            use_ascii = True
            continue
        i += 1
        time.sleep(0.08)
    try:
        sys.stdout.write("\r" + " " * 100 + "\r")
        sys.stdout.flush()
    except UnicodeEncodeError:
        pass

QUESTION_HINT_PATTERNS = ["ok to ", "should i ", "do you want", "would you like",
                          "please confirm", "let me know", "?"]

def _normalize_question(q: str) -> set:
    return set(w for w in q.lower().strip("?. ").split() if len(w) > 2)

def _prior_questions(thread: str) -> list:
    if not thread:
        return []
    return [line[len("I asked: "):] for line in thread.splitlines() if line.startswith("I asked: ")]

def _is_repeat_question(new_question: str, thread: str) -> bool:
    """Fast local pre-check only: near-identical rewording, free, no model
    call. Catches the cheap case (same words, minor edits) but NOT a real
    paraphrase ("which repository do you mean?" vs "what repo are you
    referring to?" share almost no words despite asking the same thing) -
    that needs actual understanding, which is what
    _is_repeat_question_smart layers on top of this."""
    new_words = _normalize_question(new_question)
    if not new_words:
        return False
    for prior in _prior_questions(thread):
        prior_words = _normalize_question(prior)
        if not prior_words:
            continue
        overlap = len(new_words & prior_words) / len(new_words | prior_words)
        if overlap > 0.5:
            return True
    return False

def _is_repeat_question_smart(new_question: str, thread: str, task_id: str) -> bool:
    """Anti-loop hard-stop, done properly (2026-08-15): a real gap in the
    first version was that plain word-overlap misses genuine paraphrases -
    "which repository do you mean?" and "what repo are you referring to?"
    share almost no surface words but ARE the same stuck question. Fast
    local check first (free, catches easy near-duplicates); only escalates
    to one real cheap-model semantic call when the local check is
    inconclusive AND there IS a prior question to compare against - this
    only runs on the rare 2nd+ clarification round, so the extra ~3-5s is
    justified by actually solving the loop, not just papering over it.
    Falls back to the local result if the model call itself fails."""
    if _is_repeat_question(new_question, thread):
        return True
    priors = _prior_questions(thread)
    if not priors:
        return False
    last_prior = priors[-1]
    prompt = (f'Are these two questions asking about the same fundamental missing '
              f'information, just worded differently? Answer with exactly one word, '
              f'YES or NO, nothing else.\nQ1: {last_prior}\nQ2: {new_question}')
    try:
        result = cli_dispatch(f"{task_id}-repeatcheck", "opencode-go", prompt,
                               model_id="opencode-go/mimo-v2.5", dry_run=False, timeout=60)
        if result.get("status") == "RAN" and result.get("returncode") == 0:
            answer = (result.get("stdout_tail") or "").strip().upper()
            return answer.startswith("YES")
    except Exception:
        pass
    return False

def _looks_like_a_question(output: str) -> bool:
    tail = output.strip()[-200:].lower()
    return any(p in tail for p in QUESTION_HINT_PATTERNS)

def cmd_continue(message: str, task_id: str, cwd: str):
    stop_event = threading.Event()
    spinner_thread = threading.Thread(target=_spin, args=(stop_event, "continuing claude session"), daemon=True)
    spinner_thread.start()
    start = time.time()
    try:
        result = cli_dispatch(task_id, "anthropic", message, cwd=cwd, dry_run=False, continue_session=True)
    finally:
        stop_event.set()
        spinner_thread.join()
    elapsed = time.time() - start
    output = result.get("stdout_tail") or result.get("stderr_tail") or ""
    color = GREEN if result.get("returncode") in (0, None) else RED
    print(_c(f"[{result.get('status')}]", color) + _c(f"  {elapsed:.1f}s", DIM))
    print(output.strip())
    if _looks_like_a_question(output):
        print(_c("(still asking something - /continue <answer> again to keep replying)", DIM))

def run(task: str, task_id: str, pinned_model: dict = None, cwd: str = ".",
        thread: str = None) -> dict:
    """thread: accumulated context from a prior NEEDS_CLARIFICATION round in
    this same conversation (original task + question + your reply, appended
    each round). Real bug fixed 2026-08-15: without this, every reply to a
    clarifying question was triaged as a brand-new, context-free task - "it"
    and "the systems" had nothing to resolve against, so it kept asking the
    same kind of question forever. Returns {"needs_clarification": bool,
    "thread": str|None, "queued": list[str]} so the caller can carry the
    thread into the next turn and dispatch anything typed during this run
    (real feature added 2026-08-15 - see _spin())."""
    queued: list = []
    override = None
    if pinned_model:
        override = {"provider": pinned_model[0], "model_id": pinned_model[1], "capability_tier": pinned_model[2]}

    effective_task = f"{thread}\n\nUser's follow-up reply: {task}" if thread else task

    # Real fix 2026-08-15: this used to preview with the fast LOCAL keyword
    # classifier, then auto() separately ran the real triage model - two
    # different classifications that could disagree, and a duplicate
    # cheap-model call. Now plan() (which calls the triage model once) runs
    # here, its result is shown AND handed straight to auto() via
    # precomputed_plan - one real understanding pass, reused for both.
    def step(label, fn):
        sys.stdout.write(f"  {DIM}◦ {label}...{RESET}")
        sys.stdout.flush()
        result = fn()
        sys.stdout.write(f"\r  {GREEN}✓{RESET} {label}                    \n")
        return result

    stop_event = threading.Event()
    spinner_thread = threading.Thread(target=_spin, args=(stop_event, "understanding task"), daemon=True)
    spinner_thread.start()
    try:
        p = plan(task_id, effective_task)
    finally:
        stop_event.set()
        spinner_thread.join()
    print(f"  {GREEN}✓{RESET} understanding task (real model, not keyword guessing)")

    if p["status"] == "NEEDS_CLARIFICATION" and not override:
        if _is_repeat_question_smart(p["clarifying_question"], thread, task_id):
            print(_c("! ", YELLOW) + "Same question came back again - stopping the loop instead of "
                  "asking a third time.")
            print(_c(f"Proceeding with the router's best guess: {p['classification']['task_type']} "
                      f"[tier {p['classification']['required_capability_floor']}]. "
                      f"If that's wrong, use /model to pin the right one directly.", DIM))
            p = force_plan(task_id, effective_task, p["classification"])
        else:
            print(_c("?", YELLOW) + f" {p['clarifying_question']}")
            print(_c("No dispatch made - answer this and resend, or be more specific.", DIM))
            # carry the whole thread forward, not just the latest question, so
            # a second round of clarification still has the full picture
            new_thread = f"{effective_task}\n\nI asked: {p['clarifying_question']}"
            return {"needs_clarification": True, "thread": new_thread, "queued": queued}

    classification = p["classification"]
    skills = p.get("selected_skills", [])
    agent = p.get("primary_agent")
    print(f"    {DIM}{len(skills)} skills matched"
          f"{', agent: ' + agent['id'] if agent else ''}{RESET}")

    if override:
        print_routing(classification.get("task_type", "?"), pinned_model[2],
                      pinned_model[0], pinned_model[1], classification.get("confidence", "?"),
                      pinned=True)
    else:
        ms = p["model_selection"]
        if ms["status"] != "OK":
            print(_c("BLOCKED", RED) + f" - {ms.get('reason')}")
            print(_c(ms.get('action', ''), DIM))
            return {"needs_clarification": False, "thread": None, "queued": queued}
        sel = ms["selected"]
        print_routing(classification.get("task_type", "?"), sel["capability_tier"],
                      sel["provider"], sel["model_id"], classification.get("confidence", "?"))
    print()

    active_model = pinned_model[1].split("/")[-1] if pinned_model else sel["model_id"].split("/")[-1]
    stop_event = threading.Event()
    cancel_event = threading.Event()
    spinner_thread = threading.Thread(
        target=_spin, args=(stop_event, f"waiting on {active_model}", cancel_event, queued), daemon=True)
    spinner_thread.start()
    start = time.time()
    try:
        result = auto(effective_task, cwd=cwd, task_id=task_id, override=override,
                       precomputed_plan=p, cancel_event=cancel_event)
    finally:
        stop_event.set()
        spinner_thread.join()
    elapsed = time.time() - start

    if result["status"] == "CANCELLED":
        print(_c("cancelled", YELLOW) + _c(f"  {elapsed:.1f}s (esc pressed)", DIM))
        return {"needs_clarification": False, "thread": None, "queued": queued}

    if result["status"] == "NEEDS_CLARIFICATION":
        print(_c("?", YELLOW) + f" {result['clarifying_question']}")
        print(_c(result.get("note", ""), DIM))
        new_thread = f"{effective_task}\n\nI asked: {result['clarifying_question']}"
        return {"needs_clarification": True, "thread": new_thread, "queued": queued}

    if result["status"] == "BLOCKED":
        print(_c("BLOCKED", RED) + f" - {result['reason']}")
        print(_c(result.get("note", ""), DIM))
        return {"needs_clarification": False, "thread": None, "queued": queued}

    if result.get("fell_back"):
        print(_c(f"! primary route failed, fell back to {result['routed_to']['provider']}", YELLOW))

    status_color = GREEN if result["status"] == "EXECUTED" else RED
    print(_c(f"[{result['status']}]", status_color) + _c(f"  {elapsed:.1f}s", DIM))
    output = result.get("output", "").strip()
    print(output)
    if _looks_like_a_question(output):
        # Real bug fixed 2026-08-15: this referenced an undefined `routed`
        # variable (leftover from an earlier version of this function) and
        # crashed every time a response actually looked like a question -
        # exactly the scenario this hint exists for. My own testing didn't
        # catch it because that test's output happened not to trigger this
        # branch. Use result["routed_to"] directly instead.
        if result["routed_to"]["provider"] == "anthropic":
            print(_c("(looks like it's asking something - reply with /continue <answer>)", YELLOW))
        else:
            print(_c(f"(looks like it's asking something, but {result['routed_to']['provider']} "
                      f"dispatches are one-shot - session continuation isn't wired up for this leg yet)", DIM))
    return {"needs_clarification": False, "thread": None, "queued": queued}

try:
    import msvcrt
    _HAS_MSVCRT = True
except ImportError:
    _HAS_MSVCRT = False

def _matching_commands(buf: str) -> list:
    if not buf.startswith("/") or " " in buf:
        return []
    return [c for c in COMMANDS if c[0].startswith(buf)]

def _read_line_with_suggestions(prompt_prefix: str) -> str:
    """Real feature added 2026-08-15: live slash-command suggestions as you
    type, matching Claude Code's own UX. Needs character-by-character input
    (Python's built-in input() only returns after Enter, too late to show
    suggestions mid-type) - msvcrt is Windows' stdlib low-level console
    module, no new dependency. Falls back to plain input() if msvcrt isn't
    available (e.g. running under a non-Windows shell) - suggestions are a
    nice-to-have, typing a command by hand still works either way."""
    # Real correctness issue caught before this shipped: msvcrt.getwch()
    # reads directly from the console device (CONIN$), bypassing normal
    # stdin redirection entirely - it does NOT see piped input. Every
    # automated/non-interactive invocation this session (`printf ... |
    # openaxis`, test harnesses, CI) redirects stdin, so unconditionally
    # switching to msvcrt would silently break all of that. Only use the
    # live-suggestion reader when stdin is a real interactive terminal.
    if not _HAS_MSVCRT or not sys.stdin.isatty():
        return input(prompt_prefix)

    buf = ""
    sys.stdout.write(prompt_prefix)
    sys.stdout.write("\033[s")  # save cursor: right after the prompt, before any typed text
    sys.stdout.flush()

    def redraw():
        sys.stdout.write("\033[u\033[0J")  # restore to saved position, clear everything after it
        sys.stdout.write(buf)
        for cmd, args, desc in _matching_commands(buf)[:6]:
            label = f"{cmd} {args}".strip() if args else cmd
            sys.stdout.write(f"\n  {DIM}{label:<24s}{RESET}{DIM}{desc}{RESET}")
        sys.stdout.write("\033[u")
        if buf:
            sys.stdout.write(f"\033[{len(buf)}C")
        sys.stdout.flush()

    while True:
        ch = msvcrt.getwch()
        if ch in ("\r", "\n"):
            sys.stdout.write("\033[u\033[0J")  # clear any suggestion lines before finalizing
            sys.stdout.write(buf + "\n")
            sys.stdout.flush()
            return buf
        if ch == "\x03":
            raise KeyboardInterrupt
        if ch in ("\x08", "\x7f"):
            buf = buf[:-1]
            redraw()
        elif ch in ("\x00", "\xe0"):
            msvcrt.getwch()  # swallow the second byte of a special/arrow key - not supported here
        elif ch.isprintable():
            buf += ch
            redraw()

def _boxed_prompt(pinned_model, cwd) -> str:
    """Claude Code-style boxed input with a persistent hint line underneath,
    approximated in plain ANSI (no full TUI redraw framework available) -
    top border, input on its own line (with live slash-command suggestions
    as you type), bottom border, then a status/hint row that gets reprinted
    every turn since we can't truly pin it to the bottom of the terminal
    without a curses-style redraw loop."""
    width = 60
    print(_c("-" * width, DIM))
    pin_tag = f"{_c('pinned:' + pinned_model[1].split('/')[-1], YELLOW)}  " if pinned_model else ""
    try:
        line = _read_line_with_suggestions(_c("> ", BOLD + CYAN))
    except (EOFError, KeyboardInterrupt):
        print()
        raise
    print(_c("-" * width, DIM))
    hint = f"{pin_tag}{DIM}{Path(cwd).resolve()}{RESET}"
    print(hint)
    return line.strip()

def repl():
    # Real crash fixed 2026-08-15: the header's glyph/checkmark Unicode
    # characters crash outright on any console using cp1252 (Windows
    # PowerShell's actual default, not just an edge case) - reconfiguring
    # stdout's error handling once here makes EVERY print() in this file
    # degrade gracefully (unsupported glyphs render as `?`) instead of
    # crashing the whole REPL before it even shows the first prompt. Real
    # terminals that DO support these characters (Windows Terminal, modern
    # conhost) are completely unaffected - this only changes what happens
    # when a glyph can't be encoded, never the glyph itself.
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass  # not a real reconfigurable stream (e.g. redirected in a way that doesn't support it) - fine, just skip

    # Real bug found live 2026-08-15: defaulting to "." meant cwd was
    # whatever directory the shell happened to be in when `openaxis` was
    # typed (often the user's home dir, since it's a global command) - not
    # the Open Axis repo itself. _project_context() in triage.py correctly
    # tells the dispatched model "Open Axis lives at C:\AI\control-plane",
    # but the actual CLI subprocess ran with cwd=<home dir>, so when the
    # model went to verify those paths (correctly - it shouldn't trust
    # unverified claims) it found nothing and reported the paths as
    # fictional. They weren't fictional, the cwd was just wrong. Default to
    # the Open Axis repo itself - /cd still exists for pointing dispatches
    # at any other project.
    cwd = str(CP)
    header(str(Path(cwd).resolve()))
    n = 0
    # Real bug fixed 2026-08-15: task IDs like "repl-1" collided across
    # separate sessions (SQLite INSERT OR REPLACE silently overwrote prior
    # history under the same primary key), which made /tasks tracking
    # meaningless beyond a single run. session_id makes every task_id
    # globally unique so history actually accumulates across sessions.
    session_id = uuid.uuid4().hex[:8]
    pinned_model = None  # (provider, model_id, tier) or None
    pending_thread = None  # carries context across a NEEDS_CLARIFICATION round
    while True:
        try:
            line = _boxed_prompt(pinned_model, cwd).strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not line:
            continue

        if line.startswith("/cd"):
            target = line[len("/cd"):].strip()
            if not target:
                print(_c(f"cwd: {Path(cwd).resolve()}", DIM))
            elif Path(target).is_dir():
                cwd = target
                print(_c(f"cwd -> {Path(cwd).resolve()}", GREEN))
            else:
                print(_c(f"not a directory: {target}", RED))
            continue
        if line in ("/exit", "/quit"):
            break

        try:
            if line == "/help":
                cmd_help(); continue
            if line == "/auth":
                cmd_auth(); continue
            if line == "/budget":
                print(render_dashboard()); continue
            if line == "/usage":
                cmd_usage(); continue
            if line == "/models":
                cmd_models(); continue
            if line == "/clear":
                n = 0
                print(_c("session counter reset", DIM))
                continue
            if line == "/model":
                if pinned_model:
                    print(f"pinned: {_c(pinned_model[1], YELLOW)} (tier {pinned_model[2]})")
                else:
                    print(_c("no pin - auto-routing", DIM))
                continue
            if line.startswith("/model "):
                arg = line[len("/model "):].strip()
                if arg == "clear":
                    pinned_model = None
                    print(_c("unpinned - back to auto-routing", DIM))
                elif arg in MODEL_ALIASES:
                    pinned_model = MODEL_ALIASES[arg]
                    print(_c(f"pinned to {pinned_model[1]}", YELLOW))
                else:
                    print(_c(f"unknown alias '{arg}'. Options: {', '.join(MODEL_ALIASES)}, clear", RED))
                continue
            if line.startswith("/agents "):
                cmd_agents(line[len("/agents "):].strip()); continue
            if line.startswith("/skills "):
                cmd_skills(line[len("/skills "):].strip()); continue
            if line.startswith("/verify"):
                target = line[len("/verify"):].strip() or cwd
                r = verify(f"{session_id}-verify-{n}", target)
                color = GREEN if r["status"] == "PASSED" else RED if r["status"] == "FAILED" else YELLOW
                print(_c(r["status"], color))
                for c in r.get("checks", []):
                    cc = GREEN if c["passed"] else RED if c["passed"] is False else YELLOW
                    print(f"  {_c(c['label'], cc)}: {c['command']}")
                if r.get("note"):
                    print(_c(r["note"], DIM))
                n += 1
                continue
            if line.startswith("/benchmark "):
                model = line[len("/benchmark "):].strip()
                print(_c(f"running standard task bank against {model} ...", DIM))
                subprocess.run([sys.executable, str(CP / "scripts" / "run_benchmark.py"), model])
                print(_c(f"results saved to {CP / 'reports' / 'benchmarks'}", DIM))
                n += 1
                continue
            if line == "/status":
                cmd_status()
                continue
            if line == "/report":
                print((CP / "reports" / "FINAL_SYSTEM_REPORT.md").read_text(encoding="utf-8"))
                continue
            if line == "/explain" or line.startswith("/explain "):
                cmd_explain(line[len("/explain"):].strip() or None)
                continue
            if line == "/weakness":
                print((CP / "reports" / "WEAKNESS_MAP.md").read_text(encoding="utf-8"))
                continue
            if line == "/open":
                os.startfile(str(CP))
                continue
            if line == "/sync":
                sync_agents()
                continue
            if line == "/evolve" or line.startswith("/evolve "):
                from orchestrator.self_evolve import evolve
                apply = "--apply" in line
                result = evolve(dry_run=not apply)
                if not result["promotions"]:
                    print(_c(f"no models have {result['min_samples']}+ real completions yet at 80%+ success", DIM))
                for p in result["promotions"]:
                    print(f"  {p['provider']}/{p['model']} -> tier {p['proposed_tier']} "
                          f"({p['observed_completions']} real completions, {int(p['success_rate']*100)}% success)")
                if result["promotions"] and not apply:
                    print(_c("(dry run - /evolve --apply to actually update the registry)", DIM))
                continue
            if line == "/secrets":
                env = check_env()
                files = check_files()
                for k, v in {**env, **files}.items():
                    print(f"  {k:45s} {_c(v, GREEN if v == 'FOUND' else DIM)}")
                continue
            if line == "/tasks" or line.startswith("/tasks "):
                cmd_tasks(line[len("/tasks"):].strip())
                continue
            if line.startswith("/task "):
                cmd_task_detail(line[len("/task "):].strip())
                continue
            if line.startswith("/cancel "):
                cmd_cancel(line[len("/cancel "):].strip())
                continue
            if line.startswith("/retry "):
                cmd_retry(line[len("/retry "):].strip(), cwd)
                continue
            if line.startswith("/compare "):
                n += 1
                cmd_compare(line[len("/compare "):], f"{session_id}-compare-{n}", cwd)
                continue
            if line.startswith("/continue "):
                n += 1
                cmd_continue(line[len("/continue "):], f"{session_id}-{n}", cwd)
                continue
            if line.startswith("/plan "):
                p = plan(f"{session_id}-plan-{n}", line[len("/plan "):])
                ms = p["model_selection"]
                if ms["status"] == "OK":
                    print_routing(p["classification"]["task_type"],
                                  ms["selected"]["capability_tier"],
                                  ms["selected"]["provider"], ms["selected"]["model_id"],
                                  p["classification"]["confidence"])
                else:
                    print(_c("BLOCKED", RED) + f" - {ms.get('reason')}")
                cc = p.get("if_staying_in_claude_code", {})
                if cc:
                    print(_c(f"if staying in Claude Code: {cc['recommended_model']} "
                              f"/effort {cc['recommended_effort']}", DIM))
                n += 1
                continue

            n += 1
            run_result = run(line, f"{session_id}-{n}", pinned_model=pinned_model, cwd=cwd, thread=pending_thread)
            pending_thread = run_result.get("thread") if run_result else None
            print()

            # Real feature added 2026-08-15: anything typed during the
            # "waiting on <model>" spinner (see _spin()) lands here instead
            # of being lost or fought over with the prompt - process it the
            # same way a typed-and-submitted line would be, one at a time,
            # in the order it was queued. Using a work-list (not a plain
            # for-loop over the original batch) matters: if the user keeps
            # typing while a QUEUED task is itself dispatching, that new
            # item needs to append to the same tail, not get silently
            # dropped because the for-loop had already captured its
            # iterable before the second round of typing happened.
            pending_queue = list(run_result.get("queued") or [])
            while pending_queue:
                queued_task = pending_queue.pop(0)
                print(_c(f"> {queued_task}", DIM) + _c("  (queued while previous task ran)", DIM))
                n += 1
                queued_result = run(queued_task, f"{session_id}-{n}", pinned_model=pinned_model,
                                     cwd=cwd, thread=pending_thread)
                pending_thread = queued_result.get("thread") if queued_result else None
                pending_queue.extend(queued_result.get("queued") or [])
                print()
        except Exception as e:
            print(_c(f"error: {e}", RED))
            print(_c(traceback.format_exc(limit=3), DIM))
            print(_c("(session continues - this did not crash Open Axis)", DIM))

if __name__ == "__main__":
    repl()
