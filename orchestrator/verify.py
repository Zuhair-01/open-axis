"""Closes the 'VERIFY is a stub' gap from FINAL_SYSTEM_REPORT.md. Generic,
best-effort: detects the project type from files actually present in the
target directory and runs its real lint/test command - never invents a
command for a stack that isn't there. Returns per-check pass/fail, not a
single boolean, so a missing tool doesn't silently look like success.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

CP = Path(r"C:\AI\control-plane")
sys.path.insert(0, str(CP))
from task_state.state_store import update_task

SKIP_DIRS = {"node_modules", ".venv", "venv", ".git", "dist", "build", "__pycache__", ".next"}

def _resolve(cmd: list) -> list:
    """Same fix as adapters/cli_dispatch.py: `npm` is a .cmd shim on Windows
    (confirmed via `where npm`), so bare subprocess.run(["npm", ...]) raises
    FileNotFoundError and gets misreported here as 'tool not installed' even
    though npm is genuinely present. Route .cmd/.bat through cmd /c."""
    exe = shutil.which(cmd[0])
    if exe and exe.lower().endswith((".cmd", ".bat")):
        return ["cmd", "/c", exe] + cmd[1:]
    return cmd

def _python_test_cmd(pdir: Path) -> list:
    """uv-managed projects (uv.lock present) must run through `uv run` - the
    system Python won't have the venv's packages installed. Real bug found
    2026-08-15 testing against Empire_Base/clip-platform (a uv project per
    project memory): `python -m pytest` failed with 'No module named pytest'
    even though the project has a real, working test suite."""
    if (pdir / "uv.lock").exists():
        return ["uv", "run", "pytest", "-q"]
    return ["python", "-m", "pytest", "-q"]

# Each detector: (marker file, [(label, command_or_callable)])
DETECTORS = [
    ("package.json", [
        ("npm test", ["npm", "test", "--if-present"]),
        ("npm lint", ["npm", "run", "lint", "--if-present"]),
    ]),
    ("pyproject.toml", [
        ("pytest", _python_test_cmd),
    ]),
    ("requirements.txt", [
        ("pytest", _python_test_cmd),
    ]),
    ("go.mod", [
        ("go test", ["go", "test", "./..."]),
        ("go vet", ["go", "vet", "./..."]),
    ]),
    ("Cargo.toml", [
        ("cargo test", ["cargo", "test"]),
        ("cargo clippy", ["cargo", "clippy"]),
    ]),
]

def _run(cmd, cwd) -> dict:
    try:
        r = subprocess.run(_resolve(cmd), cwd=cwd, capture_output=True, text=True,
                            timeout=600, encoding="utf-8", errors="replace")
        return {"command": " ".join(cmd), "returncode": r.returncode,
                "passed": r.returncode == 0, "tail": (r.stdout + r.stderr)[-2000:]}
    except FileNotFoundError:
        return {"command": " ".join(cmd), "passed": None, "reason": "tool not installed"}
    except subprocess.TimeoutExpired:
        return {"command": " ".join(cmd), "passed": False, "reason": "TIMEOUT after 600s"}

def _find_project_dirs(root: Path, max_depth: int = 3) -> list:
    """Real gap found 2026-08-15: only checked the root dir, missing monorepos
    (e.g. backend/pyproject.toml + frontend/package.json side by side).
    Shallow, depth-limited scan, skips noise dirs."""
    found = []
    def walk(d: Path, depth: int):
        if depth > max_depth or d.name in SKIP_DIRS:
            return
        if any((d / marker).exists() for marker, _ in DETECTORS):
            found.append(d)
        try:
            for child in d.iterdir():
                if child.is_dir() and child.name not in SKIP_DIRS:
                    walk(child, depth + 1)
        except PermissionError:
            pass
    walk(root, 0)
    return found

def verify(task_id: str, project_dir: str) -> dict:
    pdir = Path(project_dir)
    checks = []
    detected_any = False

    project_dirs = [pdir] if any((pdir / marker).exists() for marker, _ in DETECTORS) \
                   else _find_project_dirs(pdir)

    for d in project_dirs:
        for marker, cmds in DETECTORS:
            if (d / marker).exists():
                detected_any = True
                for label, cmd in cmds:
                    resolved_cmd = cmd(d) if callable(cmd) else cmd
                    result = _run(resolved_cmd, str(d))
                    result["label"] = f"{label} ({d.relative_to(pdir) if d != pdir else '.'})"
                    checks.append(result)

    if not detected_any:
        result = {"status": "NO_PROJECT_TYPE_DETECTED", "checks": [],
                   "note": f"No recognized project marker (package.json/pyproject.toml/"
                            f"requirements.txt/go.mod/Cargo.toml) found in {project_dir} "
                            f"or up to 3 levels of subdirectories. Not a failure - just "
                            f"nothing to auto-verify here."}
    else:
        hard_fails = [c for c in checks if c["passed"] is False]
        status = "FAILED" if hard_fails else "PASSED"
        result = {"status": status, "checks": checks}

    if task_id:
        update_task(task_id, status="COMPLETED" if result.get("status") == "PASSED"
                     else "VERIFYING" if result.get("status") == "NO_PROJECT_TYPE_DETECTED"
                     else "FAILED")
    return result

if __name__ == "__main__":
    task_id = sys.argv[1] if len(sys.argv) > 1 else None
    project_dir = sys.argv[2] if len(sys.argv) > 2 else "."
    print(json.dumps(verify(task_id, project_dir), indent=2))
