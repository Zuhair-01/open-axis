"""Model Budget Manager. Utilization % is computed ONLY from actually observed
usage (orchestrator/logs/usage.jsonl) against a user-supplied cap in
config/budget_caps.json. If no cap is set, status is UNKNOWN - never a
fabricated percentage. `status` (AVAILABLE/DEGRADED/RATE_LIMITED/UNAVAILABLE/
AUTH_FAILURE) comes from health/state.json, which is only ever set by real
observed provider errors (see orchestrator/fallback.py mark_provider) - not by
the utilization percentage. A provider can be at 95% observed usage and still
show AVAILABLE if it hasn't actually errored.
"""
import json
import os
import time
from pathlib import Path

CP = Path(r"C:\AI\control-plane")
USAGE_LOG = CP / "logs" / "usage.jsonl"
CAPS_PATH = CP / "config" / "budget_caps.json"
HEALTH_PATH = Path(os.environ.get("CONTROL_PLANE_HEALTH_PATH", str(CP / "health" / "state.json")))
ROLES_PATH = CP / "policies" / "provider_roles.json"

def _load_json(p: Path, default):
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))

def _windowed_usage(provider: str, window_hours: float) -> dict:
    if not USAGE_LOG.exists():
        return {"requests": 0, "tokens": 0}
    cutoff = time.time() - window_hours * 3600
    requests, tokens = 0, 0
    for line in USAGE_LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("provider") != provider or rec.get("ts", 0) < cutoff:
            continue
        requests += 1
        tokens += (rec.get("tokens_in") or 0) + (rec.get("tokens_out") or 0)
    return {"requests": requests, "tokens": tokens}

def get_budget(provider: str) -> dict:
    caps_cfg = _load_json(CAPS_PATH, {"window_hours": 5, "caps": {}})
    window_hours = caps_cfg.get("window_hours", 5)
    cap = caps_cfg.get("caps", {}).get(provider, {})
    usage = _windowed_usage(provider, window_hours)

    health = _load_json(HEALTH_PATH, {})
    now = time.time()
    h = health.get(provider, {})
    status = h["status"] if h and h.get("expires_at", 0) > now else "AVAILABLE"

    req_cap = cap.get("requests_per_window")
    pct = None
    if req_cap:
        pct = min(100, round(100 * usage["requests"] / req_cap))

    return {
        "provider": provider,
        "status": status,
        "window_hours": window_hours,
        "observed_requests": usage["requests"],
        "observed_tokens": usage["tokens"],
        "cap_requests_per_window": req_cap,
        "utilization_pct": pct,
        "utilization_basis": "OBSERVED USAGE vs USER-SET CAP" if pct is not None else "UNKNOWN - no cap configured in config/budget_caps.json",
    }

def render_bar(pct, width=10) -> str:
    if pct is None:
        return "?" * width + " no cap set"
    filled = round(width * pct / 100)
    return "█" * filled + "░" * (width - filled) + f" {pct}%"

def render_dashboard() -> str:
    roles = _load_json(ROLES_PATH, {"roles": []})["roles"]
    lines = ["MODEL BUDGET MANAGER", ""]
    for r in roles:
        b = get_budget(r["provider_id"])
        lines.append(f"{r['label']}")
        lines.append(render_bar(b["utilization_pct"]))
        lines.append(f"Status: {b['status']}   Priority: {r['priority']}")
        lines.append(f"Basis: {b['utilization_basis']}")
        lines.append("")
    return "\n".join(lines)

if __name__ == "__main__":
    print(render_dashboard())
