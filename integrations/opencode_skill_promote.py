"""Makes selected skills discoverable to OpenCode. Live skills (~/.claude/skills)
are ALREADY in OpenCode's native discovery path per its own docs - nothing to
do for those. Offline-library skills (~/.claude/skills-library) are NOT in any
discovery path, so for those specifically we create a directory junction
(Windows, no admin required) into ~/.config/opencode/skills/<name> pointing
back at the original skill dir. Additive only: originals are never moved,
copied, or edited; junctions are trivially removable.
"""
import subprocess
import sys
from pathlib import Path

CP = Path(r"C:\AI\control-plane")
sys.path.insert(0, str(CP))
from router.skill_selector import select_skills

OPENCODE_SKILLS_DIR = Path.home() / ".config" / "opencode" / "skills"

def promote(task_description: str, top_n: int = 10) -> dict:
    selected = select_skills(task_description, top_n=top_n)
    OPENCODE_SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    already_native, promoted, failed = [], [], []
    for s in selected:
        if s["source"] == "skills_live":
            already_native.append(s["id"])  # OpenCode already reads ~/.claude/skills natively
            continue
        target = OPENCODE_SKILLS_DIR / s["id"]
        if target.exists():
            promoted.append(s["id"])  # already junctioned from a prior task
            continue
        src = s["skill_dir"]
        try:
            subprocess.run(["cmd", "/c", "mklink", "/J", str(target), src],
                            check=True, capture_output=True, text=True)
            promoted.append(s["id"])
        except subprocess.CalledProcessError as e:
            failed.append({"id": s["id"], "error": e.stderr})

    return {
        "task": task_description,
        "selected_count": len(selected),
        "already_native_live_skills": already_native,
        "newly_or_previously_promoted_library_skills": promoted,
        "failed": failed,
    }

if __name__ == "__main__":
    import json
    query = " ".join(sys.argv[1:]) or "audit react app for accessibility WCAG issues"
    print(json.dumps(promote(query), indent=2))
