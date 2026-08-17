"""The actual entrypoint implementing:

TASK -> UNDERSTAND TASK -> FIND REQUIRED CAPABILITIES -> SELECT 3-10 SKILLS
     -> SELECT 1 AGENT PERSONA (reference only, never spawned - see
        policies/subagent_policy.json: no subagents, period, per explicit
        user decision 2026-08-15) -> SELECT MODEL (capability floor -> quota
        -> cost -> latency) -> [EXECUTE - out of scope for this control
        plane, that's OpenCode's/Claude Code's job] -> VERIFY (stub: real
        verification is running actual lint/test/build, wired up
        per-project, not here)

This does NOT execute anything and does NOT spawn anything. It resolves the
plan and returns it, so the caller (you, or an OpenCode/Claude Code session
working normally, no multi-agent fan-out) knows exactly what to load and
which model to target - without shoving 3,812 skills or 301 agents into
context, and without paying subagent cold-start cost.
"""
import json
import sys
from pathlib import Path

CP = Path(r"C:\AI\control-plane")
sys.path.insert(0, str(CP))
from router.classifier import classify
from router.triage import triage
from router.clarity_gate import is_obviously_clear
from router.skill_selector import select_skills
from router.agent_selector import select_agents
from router.model_selector import select_model
from router.claude_code_selector import recommend as recommend_claude_code
from task_state.state_store import create_task, update_task

def plan(task_id: str, task_description: str, use_triage: bool = True) -> dict:
    """use_triage=True (default) uses a real cheap-model understanding pass
    (router/triage.py) instead of local keyword regex - genuine
    classification, not pattern-matching pretending to be intelligence
    (real critique, 2026-08-15). Set False for instant/free local-only
    classification (e.g. REPL step-visibility preview before the real plan
    runs) where a cheap-model round-trip isn't worth the latency."""
    create_task(task_id, task_description)
    update_task(task_id, status="PLANNING")

    # Stage A (local, free, instant): obviously-clear tasks skip the real
    # model call entirely. Real cost this closes: every task, including
    # "run tests" or "fix the bug in src/auth.ts line 42", was paying a
    # ~5-15s cheap-model round trip before this. Anything not clearly
    # unambiguous still goes through the real triage model - this only
    # skips it when skipping is clearly safe, never lowers the bar.
    used_fast_path = use_triage and is_obviously_clear(task_description)
    if used_fast_path:
        classification = classify(task_description)
        classification["source"] = "local_fast_path"
        classification["needs_clarification"] = False
        classification["clarifying_question"] = ""
        classification["engineered_prompt"] = ""  # local regex path has no model call to draw a rewrite from
    else:
        classification = triage(task_description, task_id) if use_triage else classify(task_description)

    if classification.get("needs_clarification"):
        update_task(task_id, status="BLOCKED", classification=json.dumps(classification))
        return {
            "task_id": task_id,
            "task": task_description,
            "classification": classification,
            "status": "NEEDS_CLARIFICATION",
            "clarifying_question": classification.get("clarifying_question"),
            "next_step": "Answer the question, or rephrase the task with the specifics it needs "
                          "(file/repo/exact behavior) - no expensive dispatch was made.",
        }

    return _build_plan(task_id, task_description, classification)

def force_plan(task_id: str, task_description: str, classification: dict) -> dict:
    """Anti-loop hard-stop (real gap fixed 2026-08-15): called when triage
    asks essentially the same clarifying question twice in a row despite
    already having the prior answer in context - continuing to ask a third
    time is a loop, not progress. Skips the clarification gate entirely and
    proceeds with the router's best-known classification so far, clearly
    labeled so the user knows a guess was made, not a confirmed decision."""
    classification = dict(classification)
    classification["needs_clarification"] = False
    classification["source"] = classification.get("source", "unknown") + "_forced_after_repeat"
    return _build_plan(task_id, task_description, classification)

def _build_plan(task_id: str, task_description: str, classification: dict) -> dict:
    skills = select_skills(task_description, top_n=10)
    agent_matches = select_agents(classification["task_type"])
    primary_agent = agent_matches[0] if agent_matches else None
    model_choice = select_model(classification["required_capability_floor"])
    cc_reco = recommend_claude_code(task_description)

    result = {
        "task_id": task_id,
        "task": task_description,
        "classification": classification,
        "selected_skills": [{"id": s["id"], "source": s["source"]} for s in skills],
        "primary_agent": {"id": primary_agent["id"], "source": primary_agent["source"]} if primary_agent else None,
        "invocation_mode": "INLINE_ONLY",
        "invocation_note": "No subagents are spawned, ever (user decision 2026-08-15, "
                            "policies/subagent_policy.json). The primary agent's persona "
                            "text is reference for the current session to work in that style "
                            "directly - this is the normal, single-context way of working, "
                            "not a multi-agent pipeline.",
        "model_selection": model_choice,
        "if_staying_in_claude_code": {
            "recommended_model": cc_reco["recommended_model"],
            "recommended_effort": cc_reco["recommended_effort"],
            "commands": cc_reco["current_session_commands"],
        },
        "next_step": "EXECUTE (work directly, in the current session, using the above "
                      "skills/agent persona/model) then VERIFY (lint/test/build "
                      "per-project, not simulated here).",
    }

    if model_choice["status"] != "OK":
        update_task(task_id, status="BLOCKED", classification=json.dumps(classification))
        result["status"] = "BLOCKED"
    else:
        update_task(task_id, status="WAITING", classification=json.dumps(classification),
                    agent=(primary_agent["id"] if primary_agent else None),
                    model=model_choice["selected"]["model_id"],
                    provider=model_choice["selected"]["provider"])
        result["status"] = "READY_TO_EXECUTE"

    return result

if __name__ == "__main__":
    desc = " ".join(sys.argv[1:]) or "fix a security vulnerability in the payment webhook handler"
    print(json.dumps(plan("smart-route-demo", desc), indent=2))
