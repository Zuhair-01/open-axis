"""Structured, blind-labeled synthesis of multi-leg comparison results (real
feature added 2026-08-15). NOT "which answer is best" - a judge model reads
anonymized Response A/B/C (provider identity hidden until AFTER judging, to
avoid the judge just favoring "Claude" by reputation) and produces:
agreements, disagreements, unique insights, and a recommendation. Provider
identity is revealed only in the final display, after the judgment is made.
"""
import json
import re
import sys
from pathlib import Path

CP = Path(r"C:\AI\control-plane")
sys.path.insert(0, str(CP))
from adapters.cli_dispatch import dispatch

JUDGE_MODEL = "opencode-go/mimo-v2.5"
JUDGE_PROVIDER = "opencode-go"

JUDGE_PROMPT = """You are comparing {n} independent responses to the same task.
You do NOT know which AI produced which response - judge purely on content.

TASK: {task}

{responses}

Respond with ONLY a JSON object, no markdown fences:
{{"consensus": "what the responses agree on, or empty if no real agreement",
"disagreements": "specific points where responses conflict, or empty",
"unique_insights": "anything only ONE response raised that seems valuable, or empty",
"recommendation": "your synthesized recommendation given all responses",
"confidence": "high", "medium", or "low" - how confident you are given the (dis)agreement level}}"""

def _extract_json(text: str) -> dict | None:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None

def judge(task: str, leg_results: dict, task_id: str = "judge") -> dict:
    """leg_results: {"provider/model": {"output": ..., "status": ...}, ...}
    Only includes legs that actually succeeded - a failed leg contributes
    nothing to judge on, and is reported separately as unavailable, not
    silently dropped."""
    succeeded = {k: v for k, v in leg_results.items() if v.get("status") == "OK" and v.get("output")}
    failed = [k for k, v in leg_results.items() if k not in succeeded]

    if len(succeeded) < 2:
        return {
            "status": "INSUFFICIENT_LEGS",
            "reason": f"only {len(succeeded)} leg(s) succeeded - need at least 2 to compare",
            "failed_legs": failed,
        }

    labels = {f"Response {chr(65+i)}": (leg, data) for i, (leg, data) in enumerate(succeeded.items())}
    responses_text = "\n\n".join(f"{label}:\n{data['output'][:2000]}" for label, (leg, data) in labels.items())
    prompt = JUDGE_PROMPT.format(n=len(succeeded), task=task, responses=responses_text)

    result = dispatch(f"{task_id}-judge", JUDGE_PROVIDER, prompt, model_id=JUDGE_MODEL, dry_run=False, timeout=90)
    parsed = None
    if result.get("status") == "RAN" and result.get("returncode") == 0:
        parsed = _extract_json(result.get("stdout_tail", ""))

    label_to_leg = {label: leg for label, (leg, _) in labels.items()}

    if not parsed:
        return {
            "status": "JUDGE_FAILED",
            "reason": "judge model call failed or returned unparseable output - raw responses still available",
            "label_map": label_to_leg,
            "failed_legs": failed,
        }

    return {
        "status": "OK",
        "consensus": parsed.get("consensus", ""),
        "disagreements": parsed.get("disagreements", ""),
        "unique_insights": parsed.get("unique_insights", ""),
        "recommendation": parsed.get("recommendation", ""),
        "confidence": parsed.get("confidence", "unknown"),
        "label_map": label_to_leg,  # revealed AFTER judging, per the blind-judging design
        "failed_legs": failed,
    }
