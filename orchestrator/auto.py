"""The actual thing you asked for: give it a task, it picks the right leg
(Claude / GPT-Codex / OpenCode Go) per the 3-brain priority design, and
RUNS it for real - not just a recommendation. This is smart_route.py's plan
plus cli_dispatch.py's execution, wired into one call. Like OVERSEER but
across three real subscriptions instead of one provider's skill router.

Wires in the two subsystems that were built earlier this session but weren't
actually connected to the live execution path (real gap found 2026-08-15):
- orchestrator.fallback's health/retry logic: a real dispatch failure now
  marks that provider degraded and re-plans once against the next-best
  candidate, instead of just failing silently with a single-shot call.
- integrations.opencode_skill_promote: the smart-selected offline-library
  skills now actually get junctioned into OpenCode's discovery path before
  an OpenCode-routed dispatch, not just computed and discarded.
"""
import json
import sys
from pathlib import Path

CP = Path(r"C:\AI\control-plane")
sys.path.insert(0, str(CP))
from orchestrator.smart_route import plan
from orchestrator.fallback import mark_provider
from adapters.cli_dispatch import dispatch, check_auth
from integrations.opencode_skill_promote import promote as promote_skills
from task_state.state_store import update_task
from router.smart import assess, effort, record_outcome
from router.model_selector import select_model
from orchestrator.verify import verify

ALIAS_MAP = {"claude-opus-5": "opus", "claude-sonnet-5": "sonnet",
             "claude-haiku-4-5-20251001": "haiku", "claude-fable-5": "fable"}

def _cli_model_arg(provider: str, model_id: str) -> str:
    return ALIAS_MAP.get(model_id, model_id) if provider == "anthropic" else model_id

# Effort per tier lives in router/smart.py (policy: policies/routing_policy.json).


def _do_dispatch(task_id, task_description, provider, model_id, cwd, cancel_event=None, effort=None):
    if provider.startswith("opencode"):
        # ties the smart skill-selection pipeline to what the model actually
        # sees - without this, offline-library skills the router picked as
        # relevant were never made loadable by OpenCode's own skill tool.
        promote_skills(task_description)
    return dispatch(task_id, provider, task_description,
                     model_id=_cli_model_arg(provider, model_id),
                     cwd=cwd, dry_run=False, cancel_event=cancel_event, effort=effort)

def auto(task_description: str, cwd: str = None, task_id: str = "auto",
          override: dict = None, precomputed_plan: dict = None, cancel_event=None) -> dict:
    """override: {"provider": ..., "model_id": ..., "capability_tier": ...} -
    lets a caller (e.g. REPL's /model pin) bypass the router's own choice
    while still going through the same triage -> dispatch -> log pipeline.
    An explicit override is respected as-is (no fallback retry redirect) -
    the user asked for that model specifically, so a failure is reported,
    not silently rerouted.

    precomputed_plan: pass an already-computed plan() result (e.g. one the
    caller already ran to show routing/clarification to the user) so this
    doesn't call the triage model a second time for the same task - that
    would double the cheap-model round-trip cost for no reason."""
    p = precomputed_plan if precomputed_plan is not None else plan(task_id, task_description)

    if p["status"] == "NEEDS_CLARIFICATION" and not override:
        # Real fix 2026-08-15: previously an ambiguous task went straight to
        # a full expensive dispatch that just came back asking this same
        # question - now the triage model catches it up front, before any
        # real work commits.
        return {
            "status": "NEEDS_CLARIFICATION",
            "clarifying_question": p["clarifying_question"],
            "note": "No dispatch made - answer this and resend, or be more specific.",
        }

    cls = p.get("classification", {})
    sa = assess(task_description, cls, cwd)  # Car P9 smart layer: risk floor, verified cascade, learning
    if override:
        selected = override
        allow_fallback_retry = False
    elif sa["floor"] != cls.get("required_capability_floor") or p["status"] == "OK":
        sel = select_model(sa["floor"], cls.get("task_type"))
        if sel["status"] != "OK":
            return {"status": "BLOCKED", "reason": sel.get("reason"), "smart": sa,
                    "note": "No safe model at the (risk-adjusted) floor - PAUSED rather than guessing.", "plan": p}
        selected = sel["selected"]
        allow_fallback_retry = True
    elif p["status"] == "BLOCKED":
        return {
            "status": "BLOCKED",
            "reason": p["model_selection"].get("reason"),
            "note": "No safe substitute found - PAUSED rather than guessing with an "
                    "unrated model. Authenticate a stronger provider or lower task scope.",
            "plan": p,
        }
    else:
        selected = p["model_selection"]["selected"]
        allow_fallback_retry = True

    # Prompt engineering, done as part of triage (real feature added
    # 2026-08-15): if the triage model sharpened the task into a more
    # precise prompt, dispatch THAT instead of the raw original - the
    # whole point is the model doing the actual work gets a better brief
    # than what you typed, not just a routing decision made about it.
    dispatch_text = p["classification"].get("engineered_prompt") or task_description

    tt = cls.get("task_type")
    # Verified cascade: try one tier cheaper first ONLY when an automated oracle (tests) can judge the result.
    if not override and len(sa["try_floors"]) > 1:
        cheap = select_model(sa["try_floors"][0], tt)
        if cheap["status"] == "OK" and cheap["selected"]["model_id"] != selected["model_id"]:
            c = cheap["selected"]
            r0 = _do_dispatch(f"{task_id}-cascade", dispatch_text, c["provider"], c["model_id"], cwd,
                              cancel_event=cancel_event, effort=effort(sa["try_floors"][0], False, c["provider"]))
            v0 = verify(f"{task_id}-cascade", cwd)
            verdict0 = "PASS" if v0.get("status") == "PASSED" else "FAIL"
            record_outcome(task_id, tt, c["provider"], c["model_id"], sa["try_floors"][0], verdict0, cascade_step=0)
            if verdict0 == "PASS" and r0.get("status") == "RAN" and r0.get("returncode") in (0, None):
                update_task(task_id, model=c["model_id"])
                return {"status": "EXECUTED", "routed_to": {"provider": c["provider"], "model": c["model_id"],
                        "capability_tier": c["capability_tier"]}, "why": cls, "smart": sa,
                        "verified": "PASS (cheap tier, tests green)", "output": r0.get("stdout_tail") or "",
                        "returncode": r0.get("returncode"), "fell_back": False}

    provider, model_id = selected["provider"], selected["model_id"]
    result = _do_dispatch(task_id, dispatch_text, provider, model_id, cwd, cancel_event=cancel_event,
                          effort=effort(sa["floor"], sa["critical"], provider))
    # Real bug found 2026-08-15: cli_dispatch.dispatch() tracks whatever CLI
    # arg it was actually given (e.g. anthropic's short alias "sonnet"), not
    # the registry's real model_id ("claude-sonnet-5") - made /tasks history
    # inconsistent with registry/models/model_registry.json. auto() already
    # knows the real id, so overwrite it after dispatch.
    update_task(task_id, model=model_id)
    retried = False

    real_failure = result.get("status") in ("ERROR", "TIMEOUT") or \
                   (result.get("status") == "RAN" and result.get("returncode") not in (0, None))

    if real_failure and allow_fallback_retry:
        mark_provider(provider, "DEGRADED", ttl=120)
        retry_plan = plan(f"{task_id}-retry", task_description)
        retry_choice = retry_plan["model_selection"]
        if retry_choice["status"] == "OK" and retry_choice["selected"]["provider"] != provider:
            retried = True
            provider = retry_choice["selected"]["provider"]
            model_id = retry_choice["selected"]["model_id"]
            selected = retry_choice["selected"]
            result = _do_dispatch(f"{task_id}-retry", dispatch_text, provider, model_id, cwd,
                                  effort=effort(sa["floor"], sa["critical"], provider))
            update_task(f"{task_id}-retry", model=model_id)

    verified = "NONE (no test oracle)"
    if sa["oracle"]:
        v = verify(task_id, cwd)
        verdict = "PASS" if v.get("status") == "PASSED" else "FAIL"
        record_outcome(task_id, tt, provider, model_id, sa["floor"], verdict, cascade_step=1)
        verified = verdict
    return {
        "smart": sa,
        "verified": verified,
        "status": "EXECUTED" if result.get("status") == "RAN" and result.get("returncode") in (0, None)
                   else result.get("status"),
        "routed_to": {"provider": provider, "model": model_id, "capability_tier": selected["capability_tier"]},
        "why": p["classification"],
        "output": result.get("stdout_tail") or result.get("stderr_tail") or "",
        "returncode": result.get("returncode"),
        "fell_back": retried,
    }

if __name__ == "__main__":
    task = " ".join(sys.argv[1:]) or "explain what this codebase does"
    r = auto(task, cwd=".")
    print(json.dumps({k: v for k, v in r.items() if k != "output"}, indent=2))
    print("\n--- OUTPUT ---\n")
    print(r.get("output", ""))
