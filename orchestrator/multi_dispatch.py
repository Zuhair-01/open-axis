"""Real feature added 2026-08-15: dispatch the SAME task to 2-3 legs in
parallel and compare outputs - for when one opinion isn't enough (e.g.
"get Claude AND GPT's take on this architecture", or a genuine three-way
check). This is NOT the "no subagent spawning" policy being violated -
that rule was specifically about Claude Code's Agent-tool cold-start cost
inside a single provider's session. This is dispatching to separate,
independent provider CLIs in parallel threads (each already a full
subprocess anyway) - the same class of operation as running Claude and
OpenCode Go sequentially, just concurrent instead of one-after-another.
"""
import sys
import threading
import time
from pathlib import Path

CP = Path(r"C:\AI\control-plane")
sys.path.insert(0, str(CP))
from adapters.cli_dispatch import dispatch
from integrations.opencode_skill_promote import promote as promote_skills
from orchestrator.auto import ALIAS_MAP, _cli_model_arg

def dispatch_multi(task_description: str, legs: list, task_id: str, cwd: str = ".") -> dict:
    """legs: list of {"provider": ..., "model_id": ...} dicts (2-3 typical).
    Runs each dispatch in its own thread - real parallelism, not sequential
    with a shared spinner. Each leg gets its own task_id suffix so
    task_state/usage tracking stays correct per-leg, not overwritten."""
    results = {}
    threads = []

    def run_one(leg, idx):
        provider, model_id = leg["provider"], leg["model_id"]
        leg_task_id = f"{task_id}-multi{idx}"
        if provider.startswith("opencode"):
            promote_skills(task_description)
        start = time.time()
        r = dispatch(leg_task_id, provider, task_description,
                      model_id=_cli_model_arg(provider, model_id), cwd=cwd, dry_run=False)
        elapsed = time.time() - start
        # Same bug class fixed earlier in print_routing()/cmd_explain(): an
        # opencode model_id already self-describes ("opencode-go/glm-5.1"),
        # only bare anthropic aliases need the provider prefixed on.
        leg_label = model_id if "/" in model_id else f"{provider}/{model_id}"
        results[leg_label] = {
            "output": r.get("stdout_tail") or r.get("stderr_tail") or "",
            "status": "OK" if r.get("status") == "RAN" and r.get("returncode") in (0, None) else r.get("status"),
            "elapsed_s": round(elapsed, 1),
        }

    for i, leg in enumerate(legs):
        t = threading.Thread(target=run_one, args=(leg, i), daemon=True)
        threads.append(t)
        t.start()
    for t in threads:
        t.join()

    return {"task": task_description, "legs": len(legs), "results": results}
