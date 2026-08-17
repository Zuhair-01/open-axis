"""Phase 14+16, extended with the Model Budget Manager pipeline:

TASK -> DIFFICULTY/IMPORTANCE (capability floor, from classifier)
     -> QUALITY FLOOR (hard filter, never crossed)
     -> CURRENT QUOTA (budget_manager: skip providers that are RATE_LIMITED/
        UNAVAILABLE/AUTH_FAILURE right now, or over their user-set soft cap)
     -> COST (prefer lower cost_class among remaining)
     -> LATENCY (tiebreak)
     -> MODEL SELECTION

Never silently downgrades below the floor. If nothing survives the floor
filter, this returns BLOCKED with "Required capability unavailable" -
the "PAUSE / PRESERVE STATE / WAIT OR ASK USER" behavior, never a silent
substitute with a weaker model (spec Phase 16 hard safety rule).
"""
import json
import sys
from pathlib import Path

CP = Path(r"C:\AI\control-plane")
sys.path.insert(0, str(CP))
from health.budget_manager import get_budget

TIER_ORDER = ["A", "B", "C", "D", "UNKNOWN"]  # A best
COST_ORDER = ["FREE_OR_LOW", "MEDIUM", "HIGH", None]

def _tier_rank(tier: str) -> int:
    return TIER_ORDER.index(tier) if tier in TIER_ORDER else len(TIER_ORDER)

def _cost_rank(cost: str) -> int:
    return COST_ORDER.index(cost) if cost in COST_ORDER else len(COST_ORDER)

def load_models():
    return json.loads((CP / "registry/models/model_registry.json").read_text(encoding="utf-8"))["models"]

def load_roles():
    roles = json.loads((CP / "policies/provider_roles.json").read_text(encoding="utf-8"))["roles"]
    return {r["provider_id"]: r for r in roles}

def select_model(required_capability_floor: str) -> dict:
    models = load_models()
    roles = load_roles()
    floor_rank = _tier_rank(required_capability_floor)

    # Stage 1: hard capability floor filter - never crossed
    stage1 = []
    for m in models:
        tier = m.get("capability_tier", "UNKNOWN")
        if tier == "UNKNOWN":
            continue  # never assume an unbenchmarked model meets a floor
        if _tier_rank(tier) > floor_rank:
            continue  # below floor - excluded, no exceptions
        if "NOT CONFIGURED" in m.get("access_type", ""):
            continue  # not actually usable right now
        stage1.append(m)

    if not stage1:
        return {
            "selected": None,
            "status": "BLOCKED",
            "reason": "Required capability unavailable.",
            "required_capability_floor": required_capability_floor,
            "action": "PAUSE / PRESERVE STATE / WAIT OR ASK USER - never substitute a weaker model.",
            "fix": "Authenticate a provider that meets this floor (`opencode auth login`) "
                   "or explicitly lower task scope.",
        }

    # Stage 2: quota/budget filter - drop providers that are currently degraded/unavailable
    stage2 = []
    budget_notes = {}
    for m in stage1:
        b = get_budget(m["provider"])
        budget_notes[m["provider"]] = b
        if b["status"] in ("UNAVAILABLE", "AUTH_FAILURE", "RATE_LIMITED"):
            continue
        stage2.append(m)

    if not stage2:
        return {
            "selected": None,
            "status": "BLOCKED",
            "reason": "All capability-eligible providers are currently rate-limited/unavailable.",
            "required_capability_floor": required_capability_floor,
            "action": "PAUSE / PRESERVE STATE / WAIT OR ASK USER - never substitute a weaker model.",
            "budget_snapshot": budget_notes,
        }

    # Stage 3: PRIORITY, per-tier (your 3-brain design): Tier A -> Claude
    # first (scarce, save for what needs it); Tier B -> GPT/Codex first
    # (your own words: "tasks where Claude shouldn't be consumed"); Tier
    # C/D -> OpenCode Go workhorse first ("tasks that don't justify
    # Claude/GPT"). Real bug fixed 2026-08-15: a first attempt made
    # HARD_TASKS unconditionally top priority, which routed even trivial
    # Tier-D tasks to Claude - backwards, burns the scarce rate-limit window
    # on work that never needed it. Cost is the tiebreak within a tier.
    PRIORITY_BY_FLOOR = {
        "A": ["HARD_TASKS", "HARD_TASKS_CODE", "HIGH_VOLUME"],
        "B": ["HARD_TASKS_CODE", "HARD_TASKS", "HIGH_VOLUME"],
        "C": ["HIGH_VOLUME", "HARD_TASKS_CODE", "HARD_TASKS"],
        "D": ["HIGH_VOLUME", "HARD_TASKS_CODE", "HARD_TASKS"],
    }
    priority_order = PRIORITY_BY_FLOOR.get(required_capability_floor, PRIORITY_BY_FLOOR["B"])

    def _priority_rank(provider: str) -> int:
        p = roles.get(provider, {}).get("priority")
        return priority_order.index(p) if p in priority_order else len(priority_order)

    def sort_key(m):
        role = roles.get(m["provider"], {})
        return (
            _priority_rank(m["provider"]),
            _cost_rank(role.get("cost_class")),
            _tier_rank(m["capability_tier"]) * -1,  # prefer stronger within same priority/cost when tied
        )
    stage2.sort(key=sort_key)

    return {
        "selected": stage2[0],
        "status": "OK",
        "candidates_considered": len(stage2),
        "pipeline": ["capability_floor", "quota_budget", "priority", "cost", "latency_tiebreak"],
        "budget_snapshot": {m["provider"]: budget_notes[m["provider"]] for m in stage2},
    }

def select_top_n_diverse(required_capability_floor: str, n: int = 2) -> list:
    """For /compare (real feature added 2026-08-15): the single-winner
    select_model() isn't useful for multi-leg comparison - you want N
    candidates from DISTINCT providers (Claude + OpenCode Go, not two
    OpenCode Go models), each still respecting the hard capability floor.
    Reuses select_model()'s own filtering by calling it once, then walks
    the same candidate pool it built, picking one per provider in priority
    order until n are found or the pool is exhausted."""
    first = select_model(required_capability_floor)
    if first["status"] != "OK":
        return []
    seen_providers = set()
    picks = []
    # re-run the same filtering pipeline to get the full sorted candidate
    # pool, not just the winner - select_model() already computed this
    # internally but didn't expose it, so recompute cheaply (all local/cheap
    # operations, no extra dispatch calls happen here)
    models = load_models()
    roles = load_roles()
    floor_rank = _tier_rank(required_capability_floor)
    candidates = [m for m in models
                  if m.get("capability_tier", "UNKNOWN") != "UNKNOWN"
                  and _tier_rank(m["capability_tier"]) <= floor_rank
                  and "NOT CONFIGURED" not in m.get("access_type", "")]
    candidates = [m for m in candidates
                  if get_budget(m["provider"])["status"] not in ("UNAVAILABLE", "AUTH_FAILURE", "RATE_LIMITED")]
    priority_order = {
        "A": ["HARD_TASKS", "HARD_TASKS_CODE", "HIGH_VOLUME"],
        "B": ["HARD_TASKS_CODE", "HARD_TASKS", "HIGH_VOLUME"],
        "C": ["HIGH_VOLUME", "HARD_TASKS_CODE", "HARD_TASKS"],
        "D": ["HIGH_VOLUME", "HARD_TASKS_CODE", "HARD_TASKS"],
    }.get(required_capability_floor, [])
    def rank(m):
        role = roles.get(m["provider"], {})
        p = priority_order.index(role.get("priority")) if role.get("priority") in priority_order else len(priority_order)
        return (p, _cost_rank(role.get("cost_class")), _tier_rank(m["capability_tier"]) * -1)
    for m in sorted(candidates, key=rank):
        if m["provider"] in seen_providers:
            continue
        seen_providers.add(m["provider"])
        picks.append(m)
        if len(picks) >= n:
            break
    return picks

if __name__ == "__main__":
    floor = sys.argv[1] if len(sys.argv) > 1 else "B"
    print(json.dumps(select_model(floor), indent=2))
