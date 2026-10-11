"""Reconcile registry/models/model_registry.json with what each engine actually offers today.

Rules (the router's safety rule stays intact: UNKNOWN is never routed):
  - a registry model the engine no longer lists -> access_type "NOT CONFIGURED (...)", so model_selector skips it
  - a model the engine lists but the registry lacks -> added with capability_tier "UNKNOWN" (benchmark first)
  - existing human tier judgements are never changed here; only availability is reconciled
  - Anthropic and Codex are not listable from a CLI, so their current ids come from CURRENT below (update it on
    model releases; the doctor's version check reminds you)

  python scripts/sync_models.py            dry run: print the diff
  python scripts/sync_models.py --write    write the registry (git-tracked; previous version is in history)
"""
import datetime as dt, json, re, subprocess, sys, tomllib
from pathlib import Path

CP = Path(__file__).resolve().parent.parent
REGISTRY = CP / "registry/models/model_registry.json"
TODAY = dt.date.today().isoformat()
CLAUDE_ACCESS = ("SUBSCRIPTION_ACCESS via Claude Code CLI (claude --model <id> -p) - dispatched via "
                 "adapters/cli_dispatch.py, NOT through OpenCode")
# Positioning per Anthropic (Opus > Sonnet > Haiku); directional, same basis as the registry's schema_note.
CURRENT = {
    "anthropic": [
        {"model_id": "claude-opus-5-5", "display_name": "Opus 5.5", "capability_tier": "A",
         "task_types": ["ARCHITECTURE", "SECURITY", "DEBUGGING", "RESEARCH"]},
        {"model_id": "claude-sonnet-5-5", "display_name": "Sonnet 5.5", "capability_tier": "B",
         "task_types": ["IMPLEMENTATION", "REFACTOR", "TESTING", "DOCUMENTATION"]},
        {"model_id": "claude-haiku-5-5", "display_name": "Haiku 5.5", "capability_tier": "C",
         "task_types": ["SIMPLE_EDIT", "DOCUMENTATION", "ROUTINE_IMPLEMENTATION"]},
    ],
    # Fable bills usage credits on Pro and needs Zoher's one-time consent: listed, never routed.
    "anthropic_not_routed": {"claude-fable-5-1": "NOT CONFIGURED (Fable bills usage credits; needs Zoher's consent)"},
}


def live_opencode():
    out = subprocess.run(["opencode", "models"], capture_output=True, text=True, timeout=90,
                         encoding="utf-8", errors="replace").stdout
    return {l.strip() for l in out.splitlines() if re.match(r"^[\w.-]+/[\w.:-]+$", l.strip())}


def live_ollama():
    out = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=30).stdout
    return {l.split()[0] for l in out.splitlines()[1:] if l.strip()}


def live_codex():
    cfg = tomllib.loads((Path.home() / ".codex/config.toml").read_text(encoding="utf-8"))
    return {cfg["model"]} if cfg.get("model") else set()


def reconcile(models, opencode, ollama, codex):
    by_id = {m["model_id"]: m for m in models}
    changes = []
    for m in models:
        mid, prov = m["model_id"], m["provider"]
        gone = ((prov in ("opencode-zen", "opencode-go") and mid not in opencode) or
                (prov == "ollama" and mid not in ollama) or
                (prov == "openai" and mid not in codex) or
                (prov == "anthropic" and mid not in {c["model_id"] for c in CURRENT["anthropic"]}))
        if gone and "NOT CONFIGURED" not in m.get("access_type", ""):
            m["access_type"] = f"NOT CONFIGURED (not offered by the engine on {TODAY}; was: {m.get('access_type', '')[:80]})"
            changes.append(f"retired   {mid}")
    for c in CURRENT["anthropic"]:
        if c["model_id"] not in by_id:
            models.append({"provider": "anthropic", **c, "access_type": CLAUDE_ACCESS + f", listed {TODAY}"})
            changes.append(f"added     {c['model_id']} (tier {c['capability_tier']}, directional)")
    for mid, why in CURRENT["anthropic_not_routed"].items():
        if mid not in by_id:
            models.append({"provider": "anthropic", "model_id": mid, "display_name": mid,
                           "capability_tier": "UNKNOWN", "access_type": why, "task_types": []})
            changes.append(f"added     {mid} (not routed)")
    for prov, ids, access in (("opencode-go", {i for i in opencode if i.startswith("opencode-go/")}, "OpenCode Go subscription"),
                              ("opencode-zen", {i for i in opencode if i.startswith("opencode/")}, "OpenCode free models"),
                              ("ollama", ollama, "LOCAL_MODEL_ACCESS via Ollama"),
                              ("openai", codex, "SUBSCRIPTION_ACCESS via Codex CLI")):
        for mid in sorted(ids - set(by_id)):
            models.append({"provider": prov, "model_id": mid, "display_name": mid, "capability_tier": "UNKNOWN",
                           "access_type": f"{access} (listed {TODAY})", "task_types": [],
                           "notes": "Unbenchmarked: never routed until scripts/run_benchmark.py + a human/Opus tier call."})
            changes.append(f"added     {mid} (UNKNOWN, needs benchmark)")
    return models, changes


def main():
    d = json.loads(REGISTRY.read_text(encoding="utf-8"))
    models, changes = reconcile(d["models"], live_opencode(), live_ollama(), live_codex())
    routable = [m["model_id"] for m in models
                if m.get("capability_tier") != "UNKNOWN" and "NOT CONFIGURED" not in m.get("access_type", "")]
    print("\n".join(changes) or "registry already in sync")
    print(f"\nroutable now ({len(routable)}): {', '.join(routable)}")
    if "--write" in sys.argv:
        d["models"] = models
        d["last_synced"] = TODAY
        REGISTRY.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"written: {REGISTRY}")


if __name__ == "__main__":
    main()
