"""Phase 4-5: Agent forensic inventory. Read-only against source; never
moves/renames/deletes/rewrites agents. Writes registry/agents/agent_registry.json
and reports/AGENT_INVENTORY.md / AGENT_STATISTICS.md.
"""
import json
import os
import re
from pathlib import Path

HOME = Path(os.environ["USERPROFILE"])
CLAUDE = HOME / ".claude"
CP = Path(r"C:\AI\control-plane")

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# crude but dependency-free YAML-ish key: value extractor for simple frontmatter
def parse_frontmatter(text: str) -> dict:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    block = m.group(1)
    out = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and v and k not in out:
            out[k] = v
    return out

def classify(fm: dict, path: Path, source: str) -> str:
    if not fm.get("name") and not fm.get("description"):
        return "INVALID"
    if source == "agents-library":
        return "NEEDS_REVIEW"  # offline library: not currently loaded, needs a look before activation
    desc = (fm.get("description") or "").lower()
    if "claude" in desc and "opencode" not in desc:
        return "NEEDS_REVIEW"
    return "ACTIVE"

def scan(dirpath: Path, source: str) -> list:
    out = []
    if not dirpath.exists():
        return out
    for root, _, files in os.walk(dirpath):
        for fn in files:
            if not fn.endswith(".md"):
                continue
            fp = Path(root) / fn
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                out.append({
                    "id": fn, "source": source, "original_path": str(fp),
                    "status": "BROKEN", "error": str(e),
                })
                continue
            fm = parse_frontmatter(text)
            out.append({
                "id": fm.get("name", fp.stem),
                "source": source,
                "original_path": str(fp),
                "name": fm.get("name"),
                "description": fm.get("description"),
                "color": fm.get("color"),
                "emoji": fm.get("emoji"),
                "size_bytes": fp.stat().st_size,
                "status": classify(fm, fp, source),
            })
    return out

def main():
    live = scan(CLAUDE / "agents", "agents_live")
    library = scan(CLAUDE / "agents-library", "agents_library")
    all_agents = live + library

    # duplicate detection by name
    by_name = {}
    for a in all_agents:
        by_name.setdefault((a.get("name") or "").lower(), []).append(a)
    duplicates = {k: v for k, v in by_name.items() if k and len(v) > 1}

    registry = {
        "generated_from": "read-only scan, no files modified",
        "counts": {
            "agents_live": len(live),
            "agents_library_offline": len(library),
            "total_discovered": len(all_agents),
            "claim_356_confirmed": len(all_agents) == 356,
        },
        "agents": all_agents,
    }
    (CP / "registry" / "agents" / "agent_registry.json").write_text(
        json.dumps(registry, indent=2), encoding="utf-8"
    )

    status_counts = {}
    for a in all_agents:
        status_counts[a["status"]] = status_counts.get(a["status"], 0) + 1

    inv_md = f"""# AGENT INVENTORY

Discovered: {len(all_agents)} (live: {len(live)}, offline library: {len(library)})
Spec claim of ~356: {'CONFIRMED' if len(all_agents)==356 else 'NOT CONFIRMED - actual is ' + str(len(all_agents))}

## Status breakdown
{chr(10).join(f'- {k}: {v}' for k, v in sorted(status_counts.items()))}

## Duplicate names (same `name:` across files)
{chr(10).join(f'- {k} ({len(v)}x): ' + ', '.join(x['source'] for x in v) for k, v in list(duplicates.items())[:50]) if duplicates else 'None found'}
{'' if len(duplicates) <= 50 else f'... and {len(duplicates)-50} more'}
"""
    (CP / "reports" / "AGENT_INVENTORY.md").write_text(inv_md, encoding="utf-8")

    stats_md = f"""# AGENT STATISTICS

Total: {len(all_agents)}
Live (~/.claude/agents): {len(live)}
Offline library (~/.claude/agents-library): {len(library)}
Duplicate name groups: {len(duplicates)}
"""
    (CP / "reports" / "AGENT_STATISTICS.md").write_text(stats_md, encoding="utf-8")

    print(f"agents total={len(all_agents)} live={len(live)} library={len(library)} dup_groups={len(duplicates)}")

if __name__ == "__main__":
    main()
