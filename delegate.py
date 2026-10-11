"""Delegate a task to ANOTHER engine (Codex / OpenCode), never Claude (Zoher 2026-10-11: no Claude subagents;
other tools do the work, he approves engine + model + effort first). Goal: the cheapest model and reasoning
level whose measured quality clears the task's bar (registry/models/capability_matrix.json).

  python delegate.py plan "<task>" [--cwd DIR]   route + save a plan (runs nothing)
  python delegate.py run <id> [--pick N]          run runnable option N (default 0) of an APPROVED plan; blocks
  python delegate.py status <id>                  plan + result summary
  python delegate.py --selftest                   selection proof on a fixture matrix (no engine is called)

Plans/results: logs/delegate/<id>.plan.json, <id>.result.json, <id>.out.txt
Claude's flow: plan -> approval popup with the options -> on yes, `run` in the background -> verify the result
itself (diff + checks) before calling anything done.
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from router.classifier import classify  # noqa: E402
from router.smart import assess  # noqa: E402
from adapters.cli_dispatch import _resolve  # noqa: E402  (newline-safe launcher for codex on Windows)

LOGS = ROOT / "logs" / "delegate"
MATRIX = ROOT / "registry" / "models" / "capability_matrix.json"
TIMEOUT_S = 3600
MAX_OPTIONS = 5
PROVISIONAL_Q = {"A": 50, "B": 40, "C": 30, "D": 20}
# "never read auth.json" must not make a task critical: drop negated clauses before the risk scan.
NEGATED = re.compile(r"\b(never|do not|don't|without|no|not)\b.*?(?=\.(?:\s|$)|[;\n]|$)", re.I)  # to sentence end


def load_matrix() -> dict:
    return json.loads(MATRIX.read_text(encoding="utf-8"))


def options(floor: str, critical: bool, matrix=None) -> list:
    """Every (model, level) whose quality clears the bar, cheapest first; one entry per model (its cheapest
    passing level). Critical work: measured models only, bar raised to A. Cursor rows are recommend-only."""
    mx = matrix if matrix is not None else load_matrix()
    bar = mx["bars"]["A" if critical else floor]
    rows = []
    for m in mx["models"]:
        eng = mx["engines"][m["engine"]]
        if not m.get("measured"):
            if critical:
                continue
            levels = {"default": [PROVISIONAL_Q[m["tier"]], None]}
        else:
            levels = m["levels"]
        passing = [(lvl, q, c) for lvl, (q, c) in levels.items() if q >= bar]
        if not passing or m.get("available") is False or (matrix is None and is_down(m["id"])):
            continue  # below the bar, not usable on Zoher's plan, or marked down by a recent limit/failure
        lvl, q, c = min(passing, key=lambda x: (x[2] if x[2] is not None else 9e9, -x[1]))
        rows.append({"engine": eng["name"], "provider": m["engine"], "model": m["id"], "effort": lvl, "q": q,
                     "cost_per_task": c, "measured": bool(m.get("measured")), "runnable": eng["runnable"],
                     "billing": eng["billing"], "why": m.get("why") or m.get("note") or "AA Intelligence Index"})
    # runnable first, then measured, then cheapest (unknown cost last), then higher quality
    rows.sort(key=lambda r: (not r["runnable"], not r["measured"],
                             r["cost_per_task"] if r["cost_per_task"] is not None else 9e9, -r["q"]))
    runnable = [r for r in rows if r["runnable"]][:MAX_OPTIONS]
    manual = [r for r in rows if not r["runnable"]][:2]
    return runnable + manual


def command(opt: dict, prompt: str, cwd: str, out_file: Path) -> list:
    p, model, eff = opt["provider"], opt["model"], opt["effort"]
    if p == "openai":
        return _resolve(["codex", "exec", "--skip-git-repo-check", "-s", "workspace-write", "-C", cwd, "-m", model,
                         "-c", f"model_reasoning_effort={eff}", "-o", str(out_file), prompt])
    if p.startswith("opencode"):
        return _resolve(["opencode", "run", "--dir", cwd, "-m", model, prompt])  # default variant (see matrix _doc)
    raise ValueError(f"{p} is not runnable from here (recommend-only)")


def plan(task: str, cwd: str) -> dict:
    cls = classify(task)
    sa = assess(NEGATED.sub("", task), cls, cwd)
    LOGS.mkdir(parents=True, exist_ok=True)
    pid, n = time.strftime("%Y%m%d-%H%M%S"), 1
    while (LOGS / f"{pid}.plan.json").exists():  # two plans in one second must not overwrite each other
        pid, n = f"{time.strftime('%Y%m%d-%H%M%S')}-{n}", n + 1
    if not task.strip():
        raise SystemExit("empty task")
    if cls.get("task_type") == "UNKNOWN" and sa["floor"] in ("C", "D"):
        sa["floor"] = "B"  # unclassifiable work handed to another engine: don't default to the weakest bar
    opts = options(sa["floor"], sa["critical"])
    rec = {"id": pid, "task": task, "cwd": cwd, "task_type": cls.get("task_type"), "floor": sa["floor"],
           "critical": sa["critical"], "risk": sa.get("risk", []), "options": opts,
           "status": "PLANNED" if any(o["runnable"] for o in opts) else "BLOCKED: no runnable model clears the bar"}
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / f"{pid}.plan.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
    return rec


HEALTH = LOGS / "health.json"
STALL_S = 600  # no new output for 10 min = the engine is not working (2026-10-11: mimo-v2.6-pro never answered)
LIMIT_TTL_S = 5 * 3600
UNAVAILABLE = [  # (pattern in the engine's output, how long the model is marked down; None = until fixed by hand)
    (re.compile(r"not supported when using|model .{0,40}not (found|supported|available)|unknown model|"
                r"invalid model", re.I), None),
    (re.compile(r"usage limit|rate.?limit|\b429\b|quota|too many requests|insufficient (credits|balance)|"
                r"limit (reached|exceeded)|try again (at|in)", re.I), LIMIT_TTL_S),
]


def load_health() -> dict:
    try:
        return json.loads(HEALTH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def is_down(model: str, health=None, now=None) -> bool:
    h = (health if health is not None else load_health()).get(model)
    return bool(h) and (h["until"] is None or h["until"] > (now or time.time()))


def mark_down(model: str, why: str, ttl):
    h = load_health()
    h[model] = {"why": why[:200], "since": time.time(), "until": None if ttl is None else time.time() + ttl}
    LOGS.mkdir(parents=True, exist_ok=True)
    HEALTH.write_text(json.dumps(h, indent=1), encoding="utf-8")


def availability_failure(output: str):
    """(reason, ttl) when the ENGINE could not work (limit, unsupported model), else None (a real task failure)."""
    for rx, ttl in UNAVAILABLE:
        m = rx.search(output[-4000:])
        if m:
            return m.group(0), ttl
    return None


def _attempt(rec: dict, opt: dict, out_txt: Path, last_msg: Path):
    prompt = (rec["task"] + "\n\nFollow your AGENTS.md rules (R1-R27). Work only in " + rec["cwd"] +
              ". When finished, list every file you changed and the checks you ran with their real output.")
    # Output streams into out.txt while the engine works, so progress is checkable (`status <id>`, or read the file).
    with out_txt.open("w", encoding="utf-8", errors="replace") as fh:
        p = subprocess.Popen(command(opt, prompt, rec["cwd"], last_msg), cwd=rec["cwd"], stdout=fh,
                             stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        (LOGS / f"{rec['id']}.pid").write_text(str(p.pid), encoding="utf-8")
        t0, size, grew = time.time(), -1, time.time()
        while p.poll() is None:
            time.sleep(5)
            now, cur = time.time(), out_txt.stat().st_size
            if cur != size:
                size, grew = cur, now
            # OpenCode writes little to stdout while it works; its own DB activity is not visible here, so the
            # stall rule only fires on a run that produced nothing new for STALL_S.
            if now - grew > STALL_S or now - t0 > TIMEOUT_S:
                p.kill()
                return ("STALLED" if now - grew > STALL_S else "TIMEOUT"), None
    return ("DONE" if p.returncode == 0 else "FAILED"), p.returncode


def run(pid: str, pick: int = 0, fallback: bool = True) -> dict:
    """Run the approved option; on an AVAILABILITY failure (limit, unsupported model, stall) mark that model down and
    fall through to the next runnable option of the same approved plan. A real task failure never falls back."""
    rec = json.loads((LOGS / f"{pid}.plan.json").read_text(encoding="utf-8"))
    out_txt, last_msg = LOGS / f"{pid}.out.txt", LOGS / f"{pid}.last.txt"
    chain = [o for o in rec["options"][pick:] if o["runnable"]] if fallback else [rec["options"][pick]]
    tried, t0 = [], time.time()
    status, rc, out, opt = "BLOCKED", None, "", None
    for opt in chain:
        if is_down(opt["model"]):
            tried.append({"model": opt["model"], "skipped": load_health()[opt["model"]]["why"]})
            continue
        status, rc = _attempt(rec, opt, out_txt, last_msg)
        out = out_txt.read_text(encoding="utf-8", errors="replace")
        why = ("no output for %d min" % (STALL_S // 60), LIMIT_TTL_S) if status == "STALLED" else \
            availability_failure(out) if status != "DONE" else None
        tried.append({"model": opt["model"], "status": status, "unavailable": why[0] if why else None})
        if not why:
            break  # done, or a real task failure: report it, don't burn another engine on the same mistake
        mark_down(opt["model"], why[0], why[1])
        status = "ALL_UNAVAILABLE"
    res = {"id": pid, "picked": opt, "status": status, "returncode": rc, "secs": round(time.time() - t0),
           "tried": tried, "output_file": str(out_txt),
           "last_message_file": str(last_msg) if last_msg.exists() else None, "tail": out[-1500:]}
    (LOGS / f"{pid}.result.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    return res


def selftest():
    mx = {"bars": {"A": 50, "B": 40, "C": 30, "D": 20},
          "engines": {"openai": {"name": "Codex", "runnable": True, "billing": "q"},
                      "opencode-go": {"name": "OpenCode Go", "runnable": True, "billing": "q"},
                      "cursor": {"name": "Cursor", "runnable": False, "billing": "q"}},
          "models": [
              {"id": "sol", "engine": "openai", "measured": True,
               "levels": {"low": [42, 0.13], "medium": [48, 0.21], "high": [50, 0.32], "xhigh": [51, 0.39]}},
              {"id": "mimo-pro", "engine": "opencode-go", "measured": True, "levels": {"default": [46, 0.13]}},
              {"id": "cheap-weak", "engine": "opencode-go", "measured": True, "levels": {"default": [25, 0.01]}},
              {"id": "glm-5.2", "engine": "opencode-go", "measured": False, "tier": "B", "why": "locked"},
              {"id": "Grok 4.7", "engine": "cursor", "measured": True, "levels": {"high": [46, 0.0]}}]}
    a = options("A", False, mx)
    assert [(o["model"], o["effort"]) for o in a if o["runnable"]] == [("sol", "high")], a  # cheapest level >= 50
    b = options("B", False, mx)
    assert b[0]["model"] == "mimo-pro" and b[1] == {**b[1], "model": "sol", "effort": "low"}, b  # 0.13 tie: q wins
    assert "cheap-weak" not in {o["model"] for o in b}, "below the bar is never offered"
    assert any(o["model"] == "glm-5.2" and not o["measured"] for o in b), "provisional offered for non-critical"
    assert all(o["measured"] for o in options("B", True, mx)), "critical: measured only"
    assert [o["model"] for o in options("B", True, mx) if o["runnable"]] == ["sol"], "critical raises bar to A"
    assert b[-1]["model"] == "Grok 4.7" and not b[-1]["runnable"], "Cursor listed last, recommend-only"
    d = options("D", False, mx)
    assert d[0]["model"] == "cheap-weak", "D work goes to the cheapest model that clears 20"
    neg = NEGATED.sub("", "build it. never read auth.json or .credentials.json. then test it.")
    assert "auth" not in neg and "credentials" not in neg and "build it" in neg and "test it" in neg, neg
    unavailable = {**mx, "models": mx["models"] + [{"id": "gone", "engine": "openai", "measured": True,
                                                       "available": False, "levels": {"low": [60, 0.0]}}]}
    assert "gone" not in {o["model"] for o in options("A", False, unavailable)}, "available:false never offered"
    assert availability_failure("ERROR: The 'x' model is not supported when using Codex with a ChatGPT account.")[1] \
        is None, "unsupported model = down until fixed"
    assert availability_failure("You've hit your usage limit. Try again at 5pm")[1] == LIMIT_TTL_S, "limit = 5 h"
    assert availability_failure("Error: 429 Too Many Requests")[1] == LIMIT_TTL_S
    assert availability_failure("AssertionError: totals wrong in selftest") is None, "task failure: no fallback"
    h = {"m1": {"until": None}, "m2": {"until": 100.0}, "m3": {"until": 9e12}}
    assert is_down("m1", h, 50) and not is_down("m2", h, 200) and is_down("m3", h, 200) and not is_down("x", h, 1)
    cmd = command({"provider": "openai", "model": "sol", "effort": "high"}, "x", "C:/w", Path("o.txt"))
    assert "workspace-write" in cmd and "model_reasoning_effort=high" in cmd
    try:
        command({"provider": "cursor", "model": "Grok 4.7", "effort": "high"}, "x", "C:/w", Path("o.txt"))
        raise AssertionError("cursor must not be runnable")
    except ValueError:
        pass
    print("delegate selftest: PASS (cheapest passing level, bar per floor, critical=A+measured, provisional, "
          "Cursor recommend-only, negation-safe risk)")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
    elif a[0] == "--selftest":
        selftest()
    elif a[0] == "plan" and len(a) >= 2:
        cwd = a[a.index("--cwd") + 1] if "--cwd" in a else str(Path.cwd())
        print(json.dumps(plan(a[1], cwd), indent=1))
    elif a[0] == "run" and len(a) >= 2:
        pick = int(a[a.index("--pick") + 1]) if "--pick" in a else 0
        print(json.dumps(run(a[1], pick), indent=1))
    elif a[0] == "status" and len(a) >= 2:
        for suf in ("plan", "result"):
            f = LOGS / f"{a[1]}.{suf}.json"
            print(f.read_text(encoding="utf-8") if f.exists() else f"no {suf} yet")
    else:
        sys.exit(__doc__)
