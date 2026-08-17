"""Phase 29: observability - structured usage/routing/cost logging.
Appends JSONL, never logs secrets. Cost figures are only recorded when the
caller supplies them from an actual provider response - never estimated or
invented here.
"""
import json
import time
from pathlib import Path

LOG_PATH = Path(r"C:\AI\control-plane\logs\usage.jsonl")

def log_event(task_id: str, provider: str, model: str, event_type: str,
              tokens_in: int | None = None, tokens_out: int | None = None,
              cost_usd: float | None = None, latency_ms: float | None = None,
              routing_reason: str | None = None, error: str | None = None) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": time.time(), "task_id": task_id, "provider": provider, "model": model,
        "event_type": event_type,  # ROUTED | COMPLETED | FALLBACK | ERROR
        "tokens_in": tokens_in, "tokens_out": tokens_out, "cost_usd": cost_usd,
        "latency_ms": latency_ms, "routing_reason": routing_reason, "error": error,
    }
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

def summarize() -> dict:
    if not LOG_PATH.exists():
        return {"events": 0}
    events = [json.loads(l) for l in LOG_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    by_provider = {}
    total_cost = 0.0
    for e in events:
        p = e.get("provider") or "unknown"
        by_provider.setdefault(p, {"events": 0, "cost_usd": 0.0, "errors": 0})
        by_provider[p]["events"] += 1
        if e.get("cost_usd"):
            by_provider[p]["cost_usd"] += e["cost_usd"]
            total_cost += e["cost_usd"]
        if e.get("event_type") == "ERROR":
            by_provider[p]["errors"] += 1
    return {"events": len(events), "total_cost_usd": total_cost, "by_provider": by_provider}

if __name__ == "__main__":
    log_event("smoke-test-1", "opencode-zen", "opencode/big-pickle", "ROUTED",
               routing_reason="smoke test, no real call made")
    print(json.dumps(summarize(), indent=2))
