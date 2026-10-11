"""Car: which delegate models actually answer on Zoher's plans. A one-line 'reply OK' per model (seconds of quota).
Writes logs/delegate/probe_<stamp>.json and marks failures down in logs/delegate/health.json.
  python scripts/probe_models.py [model ...]     default: every runnable model in capability_matrix.json
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import delegate as d  # noqa: E402


def probe(m: dict) -> dict:
    opt = {"provider": m["engine"], "model": m["id"], "effort": next(iter(m.get("levels", {"low": 0})))}
    if opt["provider"] == "openai":
        opt["effort"] = "low"
    t0 = time.time()
    try:
        r = subprocess.run(d.command(opt, "Reply with exactly: OK", str(ROOT), ROOT / "logs/delegate/probe_last.txt"),
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        out = r.stdout + r.stderr
        ok = r.returncode == 0 and "OK" in out
    except subprocess.TimeoutExpired:
        out, ok = "no answer in 120 s", False
    why = None if ok else (d.availability_failure(out) or ("no answer / failed: " + out.strip()[-160:], d.LIMIT_TTL_S))
    if why:
        d.mark_down(m["id"], why[0], why[1])
    else:  # it answers now: lift any earlier down-mark (limit expired, CLI upgraded...)
        h = d.load_health()
        if h.pop(m["id"], None) is not None:
            d.HEALTH.write_text(json.dumps(h, indent=1), encoding="utf-8")
    return {"model": m["id"], "ok": ok, "secs": round(time.time() - t0), "why": why[0] if why else None}


if __name__ == "__main__":
    mx = d.load_matrix()
    runnable = [m for m in mx["models"] if mx["engines"][m["engine"]]["runnable"] and m.get("available") is not False]
    want = set(sys.argv[1:])
    res = [probe(m) for m in runnable if not want or m["id"] in want]
    out = ROOT / "logs/delegate" / f"probe_{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
    for r in res:
        print(("OK  " if r["ok"] else "DOWN"), r["model"], f"{r['secs']}s", r["why"] or "")
    print("->", out)
