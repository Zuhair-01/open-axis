"""Dispatches a task to whichever CLI owns the subscription for the chosen
role, instead of trying to get one login to rule all three. Verified commands
only - claude/codex/opencode --help were actually run before writing this:

  claude -p "<prompt>"          headless/print mode, uses Claude Pro subscription
  codex exec "<prompt>"         non-interactive, uses ChatGPT+ subscription (once `codex login` done)
  opencode run "<message>"      non-interactive, uses whatever OpenCode provider is configured

Each runs as its own OS process with its OWN context - they do not share a
live session. The only shared state is (a) the real files on disk, which
every CLI edits directly, and (b) task_state/state.db, which carries a
compact summary (not a raw transcript) from one CLI's turn into the next
one's starting prompt. That's the "relay, not conversation" model.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

CP = Path(r"C:\AI\control-plane")
sys.path.insert(0, str(CP))
from task_state.state_store import get_task, update_task
from orchestrator.usage_logger import log_event

# Shared GPU lock (D:\AI_Models\GPU_LOCK_README.md) - the 8GB card is also used
# by clip-platform's GPU transcribe and MiniMax H3. Ollama dispatches must not
# fight them for VRAM.
_GPU_LOCK_PY = r"D:\AI_Models\gpu_lock.py"


def _gpu_lock_acquire() -> bool:
    if not os.path.exists(_GPU_LOCK_PY):
        return True  # lock system not present on this machine, don't block on it
    try:
        r = subprocess.run(
            ["python", _GPU_LOCK_PY, "acquire", "open-axis-ollama", "--pid", str(os.getpid())],
            capture_output=True, text=True, timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return True  # fail open - lock check itself failing shouldn't block dispatch


def _gpu_lock_release() -> None:
    if not os.path.exists(_GPU_LOCK_PY):
        return
    try:
        subprocess.run(
            ["python", _GPU_LOCK_PY, "release", "open-axis-ollama", "--pid", str(os.getpid())],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        pass

CLI_COMMANDS = {
    "anthropic": ["claude", "-p"],
    # --skip-git-repo-check confirmed real and narrowly-scoped via `codex
    # exec --help` (2026-08-15): only bypasses the "must be in a git repo"
    # check, does NOT disable sandboxing or approval prompts - unlike the
    # actually dangerous --dangerously-bypass-* flags, which are not used
    # here. Needed because Open Axis often dispatches from a non-git cwd.
    "openai": ["codex", "exec", "--skip-git-repo-check"],
    "opencode-zen": ["opencode", "run"],
    "opencode-go": ["opencode", "run"],  # model passed via -m, see dispatch()
    "ollama": ["ollama", "run"],  # model passed positionally right after "run", see dispatch()
}

AUTH_CHECK = {
    "anthropic": (["claude", "--version"], "Claude Code CLI"),
    "openai": (["codex", "login", "status"], "Codex CLI - run `codex login`, choose 'Sign in with ChatGPT'"),
    "opencode-zen": (["opencode", "auth", "list"], "OpenCode - run `opencode auth login`"),
    "opencode-go": (["opencode", "auth", "list"], "OpenCode - run `opencode auth login`, pick OpenCode Go"),
    "ollama": (["ollama", "list"], "Ollama - run `ollama pull <model>` to get models"),
}

def _resolve(cmd: list) -> list:
    """Real bug found 2026-08-15: on Windows, npm-installed CLIs (e.g. codex)
    are `.cmd` batch shims, not `.exe`s - subprocess.run(["codex", ...]) fails
    with FileNotFoundError because CreateProcess can't launch a .cmd directly
    without going through cmd.exe. `claude`/`opencode` are real .exe files so
    they never hit this. shutil.which() finds the actual .cmd path; if it's a
    batch file, route it through `cmd /c` explicitly (NOT shell=True with a
    list, which mangles argument passing on Windows - tried that, made it worse)."""
    exe = shutil.which(cmd[0])
    if exe and exe.lower().endswith((".cmd", ".bat")):
        # Real bug found 2026-10-11 (Car P9 benchmark): cmd.exe cuts an argument at its first newline, so every
        # multi-line prompt sent to Codex arrived as line 1 only. npm shims just run `node <script>`; call that
        # directly so CreateProcess passes arguments (newlines included) intact. cmd /c stays the fallback.
        import re
        try:
            shim = open(exe, encoding="utf-8", errors="replace").read()
        except OSError:
            shim = ""
        m = re.search(r'"%dp0%\\([^"]+\.(?:js|cjs|mjs))"', shim)
        if m:
            base = os.path.dirname(exe)
            script = os.path.join(base, m.group(1))
            node = os.path.join(base, "node.exe")
            node = node if os.path.exists(node) else (shutil.which("node") or "node")
            if os.path.exists(script):
                return [node, script] + cmd[1:]
        return ["cmd", "/c", exe] + cmd[1:]
    return cmd

def check_auth(provider: str) -> dict:
    cmd, hint = AUTH_CHECK.get(provider, (None, None))
    if not cmd:
        return {"provider": provider, "status": "UNKNOWN_PROVIDER"}
    try:
        r = subprocess.run(_resolve(cmd), capture_output=True, text=True, timeout=20,
                            encoding="utf-8", errors="replace")
        out = ((r.stdout or "") + (r.stderr or "")).lower()
        if "not logged in" in out or "0 credentials" in out:
            return {"provider": provider, "status": "NOT_AUTHENTICATED", "hint": hint}
        return {"provider": provider, "status": "LIKELY_AUTHENTICATED", "raw": (r.stdout + r.stderr)[:300]}
    except FileNotFoundError:
        return {"provider": provider, "status": "CLI_NOT_INSTALLED", "hint": hint}
    except subprocess.TimeoutExpired:
        return {"provider": provider, "status": "CHECK_TIMED_OUT"}

def build_handoff_prompt(task_id: str, new_instructions: str = None) -> str:
    """Relay baton: compact summary from task_state, not a raw transcript."""
    t = get_task(task_id)
    if not t:
        return new_instructions or ""
    parts = [f"OBJECTIVE: {t['objective']}"]
    if t.get("plan"):
        parts.append(f"PLAN SO FAR: {t['plan']}")
    if t.get("completed_steps"):
        parts.append(f"COMPLETED STEPS: {t['completed_steps']}")
    if t.get("modified_files"):
        parts.append(f"FILES TOUCHED: {t['modified_files']}")
    if t.get("fallback_history") and t["fallback_history"] != "[]":
        parts.append(f"PRIOR ATTEMPTS/FAILURES: {t['fallback_history']}")
    if new_instructions:
        parts.append(f"CONTINUE WITH: {new_instructions}")
    return "\n\n".join(parts)

def dispatch(task_id: str, provider: str, prompt: str, model_id: str = None,
             cwd: str = None, dry_run: bool = True, continue_session: bool = False,
             timeout: int = 1800, cancel_event=None, effort: str = None) -> dict:
    """dry_run=True by default: builds the exact command and returns it
    without running anything. Set dry_run=False to actually execute - this
    runs a real CLI against real files, so it's opt-in, not automatic.
    Every real (non-dry-run) call logs a usage event via usage_logger, so
    reports/usage.jsonl and the Budget Manager's observed-usage numbers stop
    being dormant once this is actually used.

    continue_session: real architecture gap fixed 2026-08-15 - every dispatch
    was previously fire-and-forget (a fresh `claude -p` process that exits
    after one answer), so if the model asked a follow-up question there was
    no way to actually reply - the question was structurally unanswerable.
    `claude -c` ("continue most recent conversation in this directory",
    confirmed via `claude --help`) lets a REPL /continue command resume that
    exact session instead of starting a disconnected new one. Only
    anthropic supports this cleanly right now - codex/opencode-go
    continuation is a known gap, not wired up."""
    if provider not in CLI_COMMANDS:
        return {"status": "ERROR", "reason": f"no CLI mapping for provider {provider}"}

    full_prompt = build_handoff_prompt(task_id, prompt)
    cmd = list(CLI_COMMANDS[provider])
    if continue_session and provider == "anthropic":
        cmd = [cmd[0], "-c"] + cmd[1:]
    # Real bug fixed 2026-10-11: anthropic/openai ignored model_id, so a task routed to Haiku ran on the
    # session default and the usage log claimed savings that never happened. Flags verified via --help.
    if provider == "anthropic" and model_id:
        cmd += ["--model", model_id]
    if provider == "anthropic" and effort:
        cmd += ["--effort", effort]
    if provider == "openai" and model_id:
        cmd += ["-m", model_id]
    if provider == "openai" and effort:
        cmd += ["-c", f"model_reasoning_effort={effort}"]
    if provider.startswith("opencode") and model_id:
        cmd += ["-m", model_id]
    if provider == "ollama" and model_id:
        cmd += [model_id]  # `ollama run <model> <prompt>` - model is positional, not a flag
    cmd += [full_prompt]

    if dry_run:
        return {"status": "DRY_RUN", "provider": provider, "command_preview": cmd,
                "note": "Nothing executed. Call with dry_run=False to actually run this CLI."}

    gpu_locked = False
    if provider == "ollama":
        if not _gpu_lock_acquire():
            return {"status": "ERROR",
                    "reason": "GPU busy (Kyros/clip-platform/MiniMax H3 holds the lock) - "
                               "retry once the other job finishes."}
        gpu_locked = True

    update_task(task_id, status="EXECUTING", provider=provider,
                model=model_id or provider)
    start = time.time()
    try:
        # Real root-cause fix 2026-08-15 (a 323s hang was reported live):
        # stdin was never explicitly closed, so the child process inherited
        # the parent's stdin. Some CLIs (confirmed: Codex prints "Reading
        # additional input from stdin...") will BLOCK waiting for input that
        # was never coming - Open Axis always passes the full prompt as a
        # command-line argument, never via stdin. DEVNULL guarantees the
        # child sees closed/empty stdin immediately instead of hanging
        # indefinitely on a read that can never succeed.
        proc = subprocess.Popen(_resolve(cmd), cwd=cwd, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, encoding="utf-8", errors="replace")
        try:
            # Real feature added 2026-08-15 (Esc-to-interrupt): a single
            # blocking communicate(timeout=timeout) call can't be interrupted
            # from another thread mid-wait - Python explicitly documents that
            # communicate() can be called again after a TimeoutExpired
            # without losing already-buffered output, so polling in short
            # slices and checking cancel_event between them gives real
            # mid-flight cancellation without changing timeout behavior at
            # all (the outer TimeoutExpired path below is unchanged).
            if cancel_event is not None:
                while True:
                    try:
                        stdout, stderr = proc.communicate(timeout=0.25)
                        break
                    except subprocess.TimeoutExpired:
                        if cancel_event.is_set():
                            proc.kill()
                            proc.wait(timeout=5)
                            latency_ms = (time.time() - start) * 1000
                            update_task(task_id, status="CANCELLED")
                            log_event(task_id, provider, model_id or provider, "ERROR",
                                       latency_ms=latency_ms, error="CANCELLED by user (Esc)")
                            if gpu_locked:
                                _gpu_lock_release()
                            return {"status": "CANCELLED"}
                        if time.time() - start > timeout:
                            raise subprocess.TimeoutExpired(cmd, timeout)
            else:
                stdout, stderr = proc.communicate(timeout=timeout)
        except KeyboardInterrupt:
            # Real cancellation, done properly (2026-08-15): the REPL is
            # single-threaded and blocks on this call, so a slash-command
            # like /cancel physically cannot interrupt a task mid-flight -
            # Ctrl+C is the only real interrupt available here, same as
            # every other CLI (including Claude Code itself). Terminate the
            # actual child process, don't just abandon it running in the
            # background.
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            latency_ms = (time.time() - start) * 1000
            update_task(task_id, status="CANCELLED")
            log_event(task_id, provider, model_id or provider, "ERROR",
                       latency_ms=latency_ms, error="CANCELLED by user (Ctrl+C)")
            if gpu_locked:
                _gpu_lock_release()
            return {"status": "CANCELLED"}
        r = type("R", (), {"returncode": proc.returncode, "stdout": stdout, "stderr": stderr})()
        latency_ms = (time.time() - start) * 1000
        # Real bug found 2026-08-15: this used to set VERIFYING and stop -
        # nothing downstream ever advances it further since verify.py is a
        # separate, opt-in step (not auto-chained per dispatch), so every
        # successful task sat stuck at VERIFYING forever in /tasks history,
        # indistinguishable from something actually hung.
        update_task(task_id, status="COMPLETED" if r.returncode == 0 else "FAILED")
        log_event(task_id, provider, model_id or provider,
                   "COMPLETED" if r.returncode == 0 else "ERROR",
                   latency_ms=latency_ms,
                   error=None if r.returncode == 0 else r.stderr[-500:])
        if gpu_locked:
            _gpu_lock_release()
        return {"status": "RAN", "returncode": r.returncode,
                "stdout_tail": r.stdout[-4000:], "stderr_tail": r.stderr[-2000:]}
    except subprocess.TimeoutExpired:
        # Real bug fixed 2026-08-15: communicate(timeout=...) raising
        # TimeoutExpired does NOT kill the child process (Python's own
        # documented behavior) - without this, a timed-out dispatch left
        # the actual claude/codex/opencode process running orphaned in the
        # background, still consuming real subscription usage even though
        # Open Axis had already given up and moved on.
        try:
            proc.kill()
            proc.wait(timeout=5)
        except Exception:
            pass
        latency_ms = (time.time() - start) * 1000
        update_task(task_id, status="FAILED")
        log_event(task_id, provider, model_id or provider, "ERROR",
                   latency_ms=latency_ms, error=f"TIMEOUT after {timeout}s")
        if gpu_locked:
            _gpu_lock_release()
        return {"status": "TIMEOUT"}

if __name__ == "__main__":
    print(json.dumps({p: check_auth(p) for p in CLI_COMMANDS}, indent=2))
