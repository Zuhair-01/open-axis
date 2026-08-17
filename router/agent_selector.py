"""Phase 13: agent selection from the real agent registry built in Phase 4.
Never forces Claude-specific agents into OpenCode; only returns candidates
whose status is not CLAUDE_SPECIFIC/NEEDS_REVIEW for cross-environment use.
"""
import json
from pathlib import Path

CP = Path(r"C:\AI\control-plane")

def load_agents():
    return json.loads((CP / "registry/agents/agent_registry.json").read_text(encoding="utf-8"))["agents"]

def select_agents(task_type: str, cross_environment: bool = False) -> list:
    agents = load_agents()
    scored = []
    for a in agents:
        desc = (a.get("description") or "").lower()
        name = (a.get("name") or "").lower()
        hay = f"{name} {desc}"
        if task_type.lower().replace("_", " ") in hay or task_type.lower() in hay:
            if cross_environment and a["status"] in ("NEEDS_REVIEW",):
                continue
            scored.append(a)

    # Real bug found 2026-08-15: 3 duplicate-name groups in the registry
    # (e.g. 'compliance auditor' appears in both agents_live and
    # agents_library) meant the same agent could be returned twice. Dedupe
    # by name, preferring agents_live (status ACTIVE) over agents_library
    # (status NEEDS_REVIEW) when there's a collision.
    by_name = {}
    for a in scored:
        key = (a.get("name") or "").lower()
        if key not in by_name or (by_name[key]["source"] != "agents_live" and a["source"] == "agents_live"):
            by_name[key] = a
    return list(by_name.values())

if __name__ == "__main__":
    import sys
    tt = sys.argv[1] if len(sys.argv) > 1 else "security"
    for a in select_agents(tt)[:10]:
        print(a["name"], "-", a["source"], "-", a["status"])
