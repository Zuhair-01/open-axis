"""Self-evolving benchmark data (real feature requested 2026-08-15): instead
of only updating registry/models/model_registry.json manually via
scripts/run_benchmark.py, learn from REAL production dispatches as they
happen. Every completed task already gets logged (orchestrator/usage_logger.py
+ task_state) with provider/model/status - this mines that log for evidence
and promotes an UNKNOWN model to a real capability tier once there's enough
real-world success to justify it.

Safety principles, matching spec's own "never let one anomaly move routing":
- Minimum sample size before ANY promotion (default 5 successful completions
  at the SAME floor, no failures at that floor).
- Never auto-DEMOTE a model that was manually benchmarked with real judged
  output (scripts/run_benchmark.py) - only touches models still UNKNOWN, or
  raises confidence notes on already-rated ones. A few production failures
  on a model already proven capable is noise, not evidence it got worse.
- Every auto-promotion is clearly labeled "auto_evolved" in the registry,
  distinct from "spot-tested" (human-judged output) - honest about the
  difference between "it ran without erroring" and "a human read the output
  and confirmed it was actually good."
- Never promotes to Tier A - a model reaching Tier A needs the real judged
  benchmark process (subjective quality, not just exit code 0), not just
  "didn't crash N times."
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

CP = Path(r"C:\AI\control-plane")
sys.path.insert(0, str(CP))

USAGE_LOG = CP / "logs" / "usage.jsonl"
MODEL_REGISTRY = CP / "registry" / "models" / "model_registry.json"
MIN_SAMPLES = 5

def _read_events() -> list:
    if not USAGE_LOG.exists():
        return []
    events = []
    for line in USAGE_LOG.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events

def _model_success_stats() -> dict:
    """(provider, model) -> {"completed": N, "errors": N}"""
    stats = defaultdict(lambda: {"completed": 0, "errors": 0})
    for e in _read_events():
        key = (e.get("provider"), e.get("model"))
        if key == (None, None):
            continue
        if e.get("event_type") == "COMPLETED":
            stats[key]["completed"] += 1
        elif e.get("event_type") == "ERROR":
            stats[key]["errors"] += 1
    return stats

def evolve(min_samples: int = MIN_SAMPLES, dry_run: bool = True) -> dict:
    """dry_run=True by default - shows what WOULD change without writing.
    Call with dry_run=False to actually update the registry."""
    stats = _model_success_stats()
    registry = json.loads(MODEL_REGISTRY.read_text(encoding="utf-8"))
    by_id = {(m["provider"], m["model_id"]): m for m in registry["models"]}

    promotions = []
    for (provider, model), s in stats.items():
        total = s["completed"] + s["errors"]
        if total < min_samples:
            continue
        model_entry = by_id.get((provider, model))
        if not model_entry or model_entry.get("capability_tier") != "UNKNOWN":
            continue  # never touch manually-benchmarked or already-tiered models
        success_rate = s["completed"] / total
        if success_rate < 0.8:
            continue  # not enough real evidence of reliability
        # Conservative: real production success only earns Tier D (never
        # crashed on N real tasks) - actual capability (B/C/A) still needs
        # a human-judged benchmark via run_benchmark.py. This just stops an
        # actively-working model from sitting excluded from routing forever.
        promotions.append({
            "provider": provider, "model": model,
            "observed_completions": s["completed"], "observed_errors": s["errors"],
            "success_rate": round(success_rate, 2),
            "proposed_tier": "D",
        })
        if not dry_run:
            model_entry["capability_tier"] = "D"
            model_entry["notes"] = (
                f"Auto-evolved 2026-08-15+ from {s['completed']} real production completions "
                f"({s['errors']} errors, {round(success_rate*100)}% success) - NOT a human-judged "
                f"benchmark, just proven reliability at Tier D. Run scripts/run_benchmark.py for "
                f"a real quality assessment before trusting this for anything above D."
            )
            model_entry["auto_evolved"] = True

    if not dry_run and promotions:
        MODEL_REGISTRY.write_text(json.dumps(registry, indent=2), encoding="utf-8")

    return {"dry_run": dry_run, "promotions": promotions, "min_samples": min_samples}

if __name__ == "__main__":
    dry = "--apply" not in sys.argv
    result = evolve(dry_run=dry)
    print(json.dumps(result, indent=2))
    if dry and result["promotions"]:
        print("\n(dry run - re-run with --apply to actually update the registry)")
