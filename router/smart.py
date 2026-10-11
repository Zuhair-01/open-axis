"""Smart routing layer (Car P9, 2026-10-11). Sits on top of the classifier and model_selector; never breaks
their hard rule (no model below the capability floor) except through a *verified* cascade:

  1. risk     - risky work (auth, payments, migrations, deletes, secrets, deploys, PII) RAISES the floor to A
                and marks the task critical (max effort). Risk can only raise, never lower.
  2. cascade  - when the project has an automated oracle (a real test suite) and the task type is safe to try
                cheap, try one tier lower first; the oracle decides; on failure the floor model runs.
                Never for critical/risky/A-floor work, never without an oracle.
  3. learning - every verified outcome (PASS/FAIL by the oracle) is logged per (task_type, model). With at
                least min_observations, a model's measured success re-orders candidates inside the existing
                priority/cost order. Unmeasured models keep the default order (no guessing).
All rules come from policies/routing_policy.json (shared with the zoher-router Claude mod).
"""
import json, re, time
from pathlib import Path

CP = Path(__file__).resolve().parent.parent
POLICY = json.loads((CP / "policies" / "routing_policy.json").read_text(encoding="utf-8"))
OUTCOMES = Path(POLICY["learning"]["outcomes_log"])
TIERS = "ABCD"
ORACLE_MARKERS = ("package.json", "pyproject.toml", "requirements.txt", "go.mod", "Cargo.toml")


def risk_hits(text: str, files=()) -> list:
    blob = (text + " " + " ".join(map(str, files))).lower()
    return [p for p in POLICY["risk_patterns"] if re.search(p, blob)]


def has_oracle(cwd) -> bool:
    if not cwd:
        return False
    d = Path(cwd)
    return any((d / m).exists() for m in ORACLE_MARKERS) and any(
        (d / t).exists() for t in ("tests", "test", "__tests__", "spec"))


def assess(text: str, classification: dict, cwd=None, files=()) -> dict:
    hits = risk_hits(text, files)
    floor = classification.get("required_capability_floor", "C")
    critical = bool(hits) or classification.get("task_type") in POLICY["critical_task_types"]
    if hits and TIERS.index(POLICY["risk_floor"]) < TIERS.index(floor):
        floor = POLICY["risk_floor"]
    oracle = has_oracle(cwd)
    c = POLICY["cascade"]
    floors = [floor]
    if (oracle and not critical and floor in c["step_down"]
            and classification.get("task_type") in c["allowed_task_types"]):
        floors = [c["step_down"][floor], floor]
    return {"floor": floor, "critical": critical, "risk": hits, "oracle": oracle, "try_floors": floors,
            "reason": ("risk raised floor to %s" % floor if hits else "") +
                      ("; verified cascade %s" % "->".join(floors) if len(floors) > 1 else "")}


def effort(floor: str, critical: bool, provider: str):
    if provider not in ("anthropic", "openai"):
        return None
    if critical:
        return POLICY["critical_effort"][provider]
    return POLICY["effort_by_floor"].get(floor, "medium")


def record_outcome(task_id, task_type, provider, model, floor, verdict, cascade_step=0):
    """verdict: PASS | FAIL (from the oracle) | NONE (no oracle: not used for learning)."""
    OUTCOMES.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTCOMES, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.time(), "task_id": task_id, "task_type": task_type, "provider": provider,
                            "model": model, "floor": floor, "verdict": verdict, "cascade_step": cascade_step}) + "\n")


def learned(task_type: str, path=None) -> dict:
    """{model: (success_mean, n)} from verified outcomes; Beta(1,1) prior."""
    p = Path(path) if path else OUTCOMES
    stats = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("task_type") != task_type or e.get("verdict") not in ("PASS", "FAIL"):
                continue
            s, n = stats.get(e["model"], (0, 0))
            stats[e["model"]] = (s + (e["verdict"] == "PASS"), n + 1)
    return {m: ((s + 1) / (n + 2), n) for m, (s, n) in stats.items()}


def rerank(candidates: list, task_type: str, path=None) -> list:
    """Stable re-order: measured models (n >= min) sort by success; others keep their original order/slot."""
    stats, k = learned(task_type, path), POLICY["learning"]["min_observations"]
    def key(i_m):
        i, m = i_m
        mean, n = stats.get(m["model_id"], (None, 0))
        return (-(mean if n >= k else 0.5), i)  # unmeasured = neutral 0.5, ties keep original order
    return [m for _, m in sorted(enumerate(candidates), key=key)]
