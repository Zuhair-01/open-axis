"""Recommends which Claude Code model + effort level to use for a task -
the same capability-floor logic already applied to OpenCode's models,
mapped onto Claude Code's own `--model` / `--effort` flags (verified via
`claude --help`: model aliases fable/opus/sonnet/haiku, effort levels
low/medium/high/xhigh/max).

This does NOT invoke Claude Code (it's already running - you're in it).
It's advisory: prints the recommended `--model`/`--effort` for a new session,
or the /model and /effort slash-command values for the current one.
"""
import json
import sys
from pathlib import Path

CP = Path(r"C:\AI\control-plane")
sys.path.insert(0, str(CP))
from router.classifier import classify

# Model choice: capability floor drives which Claude model, matching the same
# A/B/C/D tiers used for OpenCode Go (registry/models/model_registry.json:
# opus=A, sonnet=B, haiku=C, fable=UNKNOWN/uncharacterized).
MODEL_BY_FLOOR = {
    "A": "opus",     # ARCHITECTURE, SECURITY, DIFFICULT_DEBUGGING, HIGH_RISK
    "B": "sonnet",   # IMPLEMENTATION, REFACTOR, TESTING, DEBUGGING
    "C": "sonnet",   # ROUTINE_IMPLEMENTATION, DOCUMENTATION - sonnet is still
                      # the practical default; haiku is a further downshift
                      # you opt into explicitly for pure volume, not auto-picked
    "D": "haiku",    # SIMPLE_EDIT, FORMATTING, BASIC_TRANSFORM
}

# Effort: independent axis from model - how hard the model should work, not
# which model. Confidence in the classification also lowers effort spend:
# an UNKNOWN/low-confidence classification shouldn't burn "max" effort
# guessing at a task that wasn't understood in the first place.
EFFORT_BY_FLOOR = {"A": "high", "B": "medium", "C": "low", "D": "low"}

def recommend(task_description: str) -> dict:
    c = classify(task_description)
    floor = c["required_capability_floor"]
    model = MODEL_BY_FLOOR.get(floor, "sonnet")
    effort = EFFORT_BY_FLOOR.get(floor, "medium")

    # low-confidence classification: don't escalate effort on a guess
    if c["confidence"] == "low" and effort in ("high",):
        effort = "medium"

    return {
        "task": task_description,
        "classification": c,
        "recommended_model": model,
        "recommended_effort": effort,
        "new_session_flags": f"claude --model {model} --effort {effort}",
        "current_session_commands": f"/model {model}\n/effort {effort}",
        "note": "Advisory only - this doesn't switch anything for you. "
                "capability_tier mapping matches registry/models/model_registry.json "
                "(opus~A, sonnet~B/C, haiku~D) - Fable's profile is uncharacterized "
                "this session, so it's never auto-recommended.",
    }

if __name__ == "__main__":
    task = " ".join(sys.argv[1:]) or "fix a typo in the readme"
    print(json.dumps(recommend(task), indent=2))
