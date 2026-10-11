"""Phase 12: deterministic-first task classifier. Falls back to UNKNOWN rather
than guessing when confidence is low - never pretend certainty (spec rule).
"""
import re

import json as _json
from pathlib import Path as _Path

# Car P9 (2026-10-11): the policy lives in policies/routing_policy.json so every engine (this Python router
# and the zoher-router Claude mod) classifies identically. Edit the JSON, not this file.
_POLICY = _json.loads((_Path(__file__).resolve().parent.parent / "policies" / "routing_policy.json")
                      .read_text(encoding="utf-8"))
TASK_TYPE_KEYWORDS = _POLICY["task_type_keywords"]
CAPABILITY_FLOOR_BY_TYPE = _POLICY["capability_floor_by_type"]

def classify(task_description: str) -> dict:
    text = task_description.lower()
    scores = {}
    for task_type, patterns in TASK_TYPE_KEYWORDS.items():
        hits = sum(1 for p in patterns if re.search(p, text))
        if hits:
            scores[task_type] = hits

    if not scores:
        return {
            "task_type": "UNKNOWN",
            "confidence": "low",
            "required_capability_floor": CAPABILITY_FLOOR_BY_TYPE["UNKNOWN"],
            "reason": "no keyword match - do not pretend certainty",
        }

    best = max(scores, key=scores.get)
    total_hits = sum(scores.values())
    confidence = "high" if scores[best] >= 2 and len(scores) == 1 else \
                 "medium" if scores[best] > total_hits / max(len(scores), 1) else "low"
    return {
        "task_type": best,
        "confidence": confidence,
        "required_capability_floor": CAPABILITY_FLOOR_BY_TYPE.get(best, "B"),
        "all_matches": scores,
    }

if __name__ == "__main__":
    import sys, json
    print(json.dumps(classify(" ".join(sys.argv[1:]) or "fix the login bug"), indent=2))
