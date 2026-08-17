"""Phase 15+30: fallback engine + provider health (short-TTL, never permanent).
Classifies failures, preserves task state, walks candidate models without
dropping the capability floor.
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(r"C:\AI\control-plane")))
from router.model_selector import select_model
from task_state.state_store import create_task, update_task, get_task

# Tests must not corrupt real routing state - set CONTROL_PLANE_HEALTH_PATH to
# isolate. Discovered as a real bug: the test suite was writing simulated
# DEGRADED/UNAVAILABLE statuses into production health/state.json.
HEALTH_PATH = Path(os.environ.get("CONTROL_PLANE_HEALTH_PATH",
                                   r"C:\AI\control-plane\health\state.json"))
HEALTH_TTL_SECONDS = 600  # health entries expire - never a permanent blacklist

RETRYABLE = {"RATE_LIMIT", "QUOTA_EXHAUSTED", "TIMEOUT", "PROVIDER_DOWN", "MODEL_UNAVAILABLE"}
NON_RETRYABLE = {"AUTH_FAILURE", "CONTEXT_OVERFLOW", "INVALID_REQUEST", "INSUFFICIENT_CAPABILITY"}

def _load_health() -> dict:
    if not HEALTH_PATH.exists():
        return {}
    data = json.loads(HEALTH_PATH.read_text(encoding="utf-8"))
    now = time.time()
    return {k: v for k, v in data.items() if v.get("expires_at", 0) > now}

def _save_health(data: dict) -> None:
    HEALTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    HEALTH_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

def mark_provider(provider: str, status: str, ttl: int = HEALTH_TTL_SECONDS) -> None:
    data = _load_health()
    data[provider] = {"status": status, "set_at": time.time(), "expires_at": time.time() + ttl}
    _save_health(data)

def run_with_fallback(task_id: str, objective: str, required_capability_floor: str,
                       simulated_errors: list[str] | None = None) -> dict:
    """simulated_errors: ordered list of error codes to simulate per attempt,
    for Phase 37 failure simulation. In real use this would come from actual
    provider call failures, not a param."""
    create_task(task_id, objective)
    update_task(task_id, status="PLANNING")
    history = []
    errors = list(simulated_errors or [])

    for attempt in range(4):  # max_retries_per_chain(3) + 1 initial
        choice = select_model(required_capability_floor)
        if not choice.get("selected"):
            update_task(task_id, status="BLOCKED", fallback_history=history)
            return {"status": "BLOCKED", "reason": choice["reason"], "history": history}

        model = choice["selected"]
        update_task(task_id, status="EXECUTING", model=model["model_id"], provider=model["provider"])

        err = errors.pop(0) if errors else None
        if err is None:
            update_task(task_id, status="COMPLETED", fallback_history=history)
            return {"status": "COMPLETED", "model_used": model["model_id"], "history": history}

        history.append({"attempt": attempt, "model": model["model_id"], "error": err})
        update_task(task_id, status="FALLING_BACK", fallback_history=history)

        if err in NON_RETRYABLE:
            mark_provider(model["provider"], "AUTH_FAILURE" if err == "AUTH_FAILURE" else "UNAVAILABLE")
        elif err in RETRYABLE:
            mark_provider(model["provider"], "DEGRADED", ttl=120)
        else:
            update_task(task_id, status="FAILED", fallback_history=history)
            return {"status": "FAILED", "reason": f"unclassified error {err}", "history": history}

    update_task(task_id, status="FAILED", fallback_history=history)
    return {"status": "FAILED", "reason": "max retries exceeded", "history": history}

if __name__ == "__main__":
    print(json.dumps(run_with_fallback("demo-1", "test fallback", "B",
                                        simulated_errors=["RATE_LIMIT", "PROVIDER_DOWN"]), indent=2))
