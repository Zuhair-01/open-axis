"""Real understanding instead of regex pretending to be intelligence.

The critique that landed this: `classifier.py` is keyword pattern-matching -
it has no idea what a task actually means, so vague input ("try using our
systems") either misclassifies or defaults blind, then a full dispatch comes
back asking the exact clarifying question a moment of real understanding
would have asked for free. This module fixes that: a genuinely cheap, fast
model call (Tier C, ~2-4s, not the expensive final dispatch) actually reads
the task and returns a structured judgment - task type, capability floor,
and whether it's even specific enough to execute - BEFORE any real work
commits. If the task is too vague, the clarifying question comes back
directly, with zero wasted expensive-tier dispatch.

Falls back to the local keyword classifier (never silently guesses) if the
triage call fails or returns something unparseable - degrade gracefully,
don't hard-fail.
"""
import json
import re
import sys
from pathlib import Path

CP = Path(r"C:\AI\control-plane")
sys.path.insert(0, str(CP))
from router.classifier import classify as local_classify
from adapters.cli_dispatch import dispatch

TRIAGE_MODEL = "opencode-go/mimo-v2.5"  # benchmarked Tier C, fast (see reports/BENCHMARK_RESULTS.md)
TRIAGE_PROVIDER = "opencode-go"

TASK_TYPES = ["ARCHITECTURE", "SECURITY", "DEBUGGING", "REFACTOR", "RESEARCH",
              "DOCUMENTATION", "TESTING", "DEVOPS", "SIMPLE_EDIT", "IMPLEMENTATION",
              "PERFORMANCE", "UNKNOWN"]

# Real grounding, not just rephrasing (2026-08-15): "test our OpenAxis
# systems" should resolve to actual facts - where the code lives, what its
# real test suite is - not a vaguer restatement of the same words. Without
# this, "engineered_prompt" was just polishing vocabulary; input quality
# genuinely determines output quality, so self-referential tasks need real
# project grounding, the same way a competent engineer would already know
# where the repo and tests live before touching anything.
def _project_context() -> str:
    return (
        "PROJECT CONTEXT (use this to ground vague references - do not restate it "
        "verbatim in engineered_prompt, use it to fill in real specifics):\n"
        "'Open Axis' / 'our system' / 'openaxis' = the AI orchestration control plane "
        f"at {CP}. Routes tasks across Claude (claude CLI), Codex/GPT (codex CLI), "
        "OpenCode Go (opencode CLI, 26 models), and Ollama (local models). "
        f"Test suites: {CP}/tests/test_control_plane.py and {CP}/tests/test_clarity_gate.py "
        "(run via `python <path>`). Registries at "
        f"{CP}/registry/. Full docs at {CP}/reports/ and {CP}/docs/."
    )

TRIAGE_PROMPT = """{context}

Classify this task request AND, if it's specific enough to
execute, rewrite it into a sharper, more precise prompt for whichever model
actually does the work - add concrete detail the original implies but
doesn't state (e.g. expected inputs/outputs, edge cases worth handling,
relevant constraints, real file paths from PROJECT CONTEXT above when the
task refers to Open Axis itself), without inventing requirements that
weren't implied. If it's NOT specific enough, leave engineered_prompt empty
- a vague original shouldn't get a confidently-invented rewrite.

Respond with ONLY a JSON object, no other text, no markdown fences:
{{"task_type": one of {types}, "capability_floor": one of ["A","B","C","D"] (A=hardest/architecture/security, D=trivial edit), "specific_enough_to_execute": true or false, "clarifying_question": "" or a short question if not specific enough, "engineered_prompt": "" or the sharpened version of the task}}

Task: {task}"""

def _extract_json(text: str) -> dict | None:
    text = text.strip()
    # models sometimes wrap in ```json fences despite instructions - strip them
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None

def _try_triage_call(task_description: str, task_id: str) -> dict | None:
    prompt = TRIAGE_PROMPT.format(context=_project_context(), types=TASK_TYPES, task=task_description)
    # Real bug fixed 2026-08-15 (live report: stuck 323s+ on "understanding
    # task"): triage was using the default 1800s (30-minute) timeout meant
    # for actual execution work. A quick understanding pass should never
    # legitimately take more than ~60s - if it does, something is actually
    # wrong (stuck process, dead backend) and the graceful local-classifier
    # fallback should kick in fast, not after half an hour.
    result = dispatch(task_id, TRIAGE_PROVIDER, prompt, model_id=TRIAGE_MODEL, dry_run=False, timeout=60)
    if result.get("status") != "RAN" or result.get("returncode") != 0:
        return None
    parsed = _extract_json(result.get("stdout_tail", ""))
    if not parsed or parsed.get("task_type") not in TASK_TYPES or parsed.get("capability_floor") not in ("A", "B", "C", "D"):
        return None
    return {
        "task_type": parsed["task_type"],
        "required_capability_floor": parsed["capability_floor"],
        "confidence": "high",
        "source": "triage_model",
        "needs_clarification": not parsed.get("specific_enough_to_execute", True),
        "clarifying_question": parsed.get("clarifying_question", ""),
        # Prompt engineering, done as part of the same call (real feature
        # added 2026-08-15) - not a separate round trip. Empty when the
        # task was too vague to safely sharpen - never fabricate detail
        # onto an ambiguous request.
        "engineered_prompt": parsed.get("engineered_prompt", "") or "",
    }

def triage(task_description: str, task_id: str = "triage") -> dict:
    """Returns: task_type, required_capability_floor, confidence, source
    ("triage_model" or "local_fallback"), and if not specific enough:
    needs_clarification=True + clarifying_question.

    Retries once on a parse failure before falling back locally (real
    resilience fix, 2026-08-15): confirmed via direct reproduction that a
    real triage call occasionally returns a generation that doesn't parse
    as valid JSON - not a bug in the parser, genuine LLM non-determinism.
    Falling back to the much weaker local regex classifier on a single bad
    generation was wasting the real understanding this system exists to
    provide - one retry costs a few more seconds and recovers most of them."""
    out = _try_triage_call(task_description, f"{task_id}-triage")
    if out is None:
        out = _try_triage_call(task_description, f"{task_id}-triage-retry")
    if out is not None:
        return out

    # graceful fallback - triage call failed twice, timed out, or the
    # model genuinely can't be reached (not just one bad generation)
    local = local_classify(task_description)
    local["source"] = "local_fallback"
    local["needs_clarification"] = False
    local["clarifying_question"] = ""
    local["engineered_prompt"] = ""  # local regex classifier can't do this - no model call to draw from
    return local

if __name__ == "__main__":
    task = " ".join(sys.argv[1:]) or "try using our systems"
    print(json.dumps(triage(task), indent=2))
