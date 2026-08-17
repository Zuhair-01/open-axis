"""Reusable benchmark runner. Run this against any new model/provider so
results stay comparable over time instead of one-off ad hoc probes.

Usage:
  python run_benchmark.py opencode-go/kimi-k3
  python run_benchmark.py opencode-go/kimi-k3 --tasks d1_simple_edit,a1_hard_reasoning

Saves raw output to reports/benchmarks/<model_slug>__<task_id>.md. Scoring
(capability_tier) is a human judgment call against each task's pass_criteria
- this script does NOT auto-grade. Auto-grading with an LLM judge is a real
option (see skill: advanced-evaluation) but a second model judging a first
model's work has its own bias risks; a human spot-check on a small task bank
like this is more trustworthy than it looks expensive.
"""
import json
import subprocess
import sys
from pathlib import Path

CP = Path(r"C:\AI\control-plane")
TASKS_PATH = CP / "fixtures/benchmark_tasks.json"
OUT_DIR = CP / "reports/benchmarks"

def load_tasks(filter_ids=None):
    tasks = json.loads(TASKS_PATH.read_text(encoding="utf-8"))["tasks"]
    if filter_ids:
        tasks = [t for t in tasks if t["id"] in filter_ids]
    return tasks

def run_one(model_id: str, task: dict) -> dict:
    slug = model_id.replace("/", "__")
    out_path = OUT_DIR / f"{slug}__{task['id']}.md"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    cmd = ["opencode", "run", "-m", model_id, task["prompt"]]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180,
                            encoding="utf-8", errors="replace")
        output = r.stdout or r.stderr
    except subprocess.TimeoutExpired:
        output = "TIMEOUT after 180s"
    except FileNotFoundError:
        output = "ERROR: opencode CLI not found"

    out_path.write_text(
        f"# Benchmark: {model_id} / {task['id']}\n\n"
        f"**Tier target:** {task['tier_target']}  **Task type:** {task['task_type']}\n\n"
        f"**Prompt:**\n```\n{task['prompt']}\n```\n\n"
        f"**Pass criteria:** {task['pass_criteria']}\n\n"
        f"**Raw output:**\n\n{output}\n\n"
        f"**Verdict:** _NOT YET SCORED - fill in PASS/FAIL/PARTIAL + tier note after reviewing above_\n",
        encoding="utf-8"
    )
    return {"task_id": task["id"], "output_path": str(out_path)}

def main():
    if len(sys.argv) < 2:
        print("usage: run_benchmark.py <provider/model> [--tasks id1,id2,...]")
        sys.exit(1)
    model_id = sys.argv[1]
    filter_ids = None
    if len(sys.argv) > 2 and sys.argv[2] == "--tasks":
        filter_ids = set(sys.argv[3].split(","))

    tasks = load_tasks(filter_ids)
    results = [run_one(model_id, t) for t in tasks]
    print(json.dumps({"model": model_id, "ran": len(results), "results": results}, indent=2))

if __name__ == "__main__":
    main()
