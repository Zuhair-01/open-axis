import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from router.classifier import classify  # noqa: E402

BASELINE = {  # captured from the pre-JSON classifier on 2026-10-11
    "fix the race condition in the payment webhook": ("SECURITY", "A"),
    "rename variable foo to bar": ("SIMPLE_EDIT", "D"),
    "write a README for the API": ("DOCUMENTATION", "C"),
    "implement a new endpoint for orders": ("IMPLEMENTATION", "B"),
    "design a system for 10M events/day": ("ARCHITECTURE", "A"),
    "why is this test failing with an exception": ("DEBUGGING", "B"),
    "optimize the slow query": ("PERFORMANCE", "B"),
    "refactor the auth module": ("REFACTOR", "B"),
    "hello there": ("UNKNOWN", "C"),
    # 2026-10-11 router regression: debugging follow-ups used to fall to UNKNOWN -> C (effort low)
    "router issue?? why this happened? make sure its perfected": ("DEBUGGING", "B"),
    "why did the export fail": ("DEBUGGING", "B"),
    "it doesnt work after the update": ("DEBUGGING", "B"),
    "open a github issue for this": ("UNKNOWN", "C"),
}


def test_policy_json_classifier_matches_baseline():
    for text, (tt, floor) in BASELINE.items():
        r = classify(text)
        assert (r["task_type"], r["required_capability_floor"]) == (tt, floor), text
