"""Comparison-mode routing intelligence (real feature added 2026-08-15, per
explicit design review): /compare shouldn't be a manual-only command - the
router itself should decide when independent multi-model reasoning is worth
the extra cost, not just react when you ask for it.

Deliberately reuses the EXISTING capability-floor concept instead of
inventing a separate "risk score" - floor A tasks (architecture/security/
major refactor/high-risk, per policies/capability_tiers.json) already ARE
the "critical/high-uncertainty" bucket; no new taxonomy needed.

Cost-conscious default: only Tier A auto-triggers DUAL (not TRIPLE - that
stays an explicit `/compare 3` choice, since 3x dispatch cost for every
single hard task by default is exactly the "burn 3x capacity for no
reason" the design review warned against). Tier B/C/D stay single-leg
(NONE) by default - you can always ask for /compare explicitly on anything.
"""

COMPARISON_MODES = ("NONE", "DUAL", "TRIPLE")

# floor -> default comparison_mode. Deliberately conservative: real-world
# cost data (once /evolve has enough of it) should be what raises this, not
# a guess made before any usage data exists.
DEFAULT_MODE_BY_FLOOR = {"A": "DUAL", "B": "NONE", "C": "NONE", "D": "NONE"}

def decide_comparison_mode(required_capability_floor: str, confidence: str = "high") -> str:
    """confidence: low-confidence classification should NOT auto-escalate to
    a more expensive comparison mode - being unsure what a task needs is not
    evidence it's important, same principle already applied to the
    UNKNOWN-task-type capability-floor default (real bug fixed earlier this
    session)."""
    if confidence == "low":
        return "NONE"
    return DEFAULT_MODE_BY_FLOOR.get(required_capability_floor, "NONE")

def legs_needed(mode: str) -> int:
    return {"NONE": 1, "DUAL": 2, "TRIPLE": 3}.get(mode, 1)
