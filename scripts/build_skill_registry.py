"""Phase 6: Skill forensic inventory. Read-only against source; never
moves/renames/deletes/rewrites/deduplicates skills. Writes
registry/skills/skill_registry.json + skill_index.json (lightweight index for
on-demand loading per Phase 7) and reports/SKILL_INVENTORY.md / SKILL_STATISTICS.md.
"""
import json
import os
import re
from pathlib import Path

HOME = Path(os.environ["USERPROFILE"])
CLAUDE = HOME / ".claude"
CP = Path(r"C:\AI\control-plane")

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

def parse_frontmatter(text: str) -> dict:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    block = m.group(1)
    out = {}
    cur_key = None
    for raw in block.splitlines():
        if raw.startswith((" ", "\t")) and cur_key:
            out[cur_key] += " " + raw.strip()
            continue
        if ":" not in raw:
            continue
        k, _, v = raw.partition(":")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k:
            out[k] = v
            cur_key = k
    return out

def scan(dirpath: Path, source: str) -> list:
    out = []
    if not dirpath.exists():
        return out
    for root, _, files in os.walk(dirpath):
        for fn in files:
            if fn.lower() != "skill.md":
                continue
            fp = Path(root) / fn
            skill_dir = fp.parent
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                out.append({"id": skill_dir.name, "source": source, "original_path": str(fp),
                            "status": "BROKEN", "error": str(e)})
                continue
            fm = parse_frontmatter(text)
            supporting = [str(p) for p in skill_dir.rglob("*") if p.is_file() and p.name.lower() != "skill.md"]
            out.append({
                "id": fm.get("name", skill_dir.name),
                "source": source,
                "original_path": str(fp),
                "skill_dir": str(skill_dir),
                "name": fm.get("name"),
                "description": fm.get("description"),
                "origin": fm.get("origin"),
                "supporting_file_count": len(supporting),
                "size_bytes": fp.stat().st_size,
                "status": "ACTIVE" if fm.get("name") else "NEEDS_REVIEW",
            })
    return out

def main():
    live = scan(CLAUDE / "skills", "skills_live")
    library = scan(CLAUDE / "skills-library", "skills_library")
    all_skills = live + library

    by_name = {}
    for s in all_skills:
        by_name.setdefault((s.get("name") or "").lower(), []).append(s)
    duplicates = {k: v for k, v in by_name.items() if k and len(v) > 1}

    registry = {
        "generated_from": "read-only scan, no files modified",
        "counts": {
            "skills_live": len(live),
            "skills_library_offline": len(library),
            "total_discovered": len(all_skills),
        },
        "skills": all_skills,
    }
    (CP / "registry" / "skills" / "skill_registry.json").write_text(
        json.dumps(registry, indent=2), encoding="utf-8"
    )

    # lightweight index for on-demand loading (Phase 7): id/name/description/source only
    index = [
        {"id": s["id"], "name": s.get("name"), "description": s.get("description"),
         "source": s["source"], "skill_dir": s.get("skill_dir")}
        for s in all_skills
    ]
    (CP / "registry" / "skills" / "skill_index.json").write_text(
        json.dumps(index, indent=2), encoding="utf-8"
    )

    inv_md = f"""# SKILL INVENTORY

Discovered: {len(all_skills)} (live: {len(live)}, offline library: {len(library)})
Spec claim of ~3,400+: {'CONFIRMED' if len(all_skills) >= 3400 else 'CLOSE - actual is ' + str(len(all_skills))}

## Duplicate names across live + library ({len(duplicates)} groups)
{chr(10).join(f'- {k} ({len(v)}x)' for k, v in list(duplicates.items())[:50]) if duplicates else 'None found'}
{'' if len(duplicates) <= 50 else f'... and {len(duplicates)-50} more'}
"""
    (CP / "reports" / "SKILL_INVENTORY.md").write_text(inv_md, encoding="utf-8")

    stats_md = f"""# SKILL STATISTICS

Total: {len(all_skills)}
Live (~/.claude/skills): {len(live)}
Offline library (~/.claude/skills-library): {len(library)}
Duplicate name groups: {len(duplicates)}
"""
    (CP / "reports" / "SKILL_STATISTICS.md").write_text(stats_md, encoding="utf-8")

    print(f"skills total={len(all_skills)} live={len(live)} library={len(library)} dup_groups={len(duplicates)}")

if __name__ == "__main__":
    main()
