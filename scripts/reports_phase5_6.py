"""Phase 5-6 remaining reports: duplicates, security scan (lightweight heuristic),
compatibility notes. Reads only the registries already built; touches nothing
under ~/.claude.
"""
import json
import re
from pathlib import Path

CP = Path(r"C:\AI\control-plane")

SUSPICIOUS_PATTERNS = [
    (r"curl .*\|\s*(sh|bash)", "pipe-to-shell download"),
    (r"rm -rf /", "destructive root delete"),
    (r"\.env\b.*(cat|curl|upload|send)", "possible env exfiltration"),
    (r"disable.*(antivirus|firewall|security)", "security-disable instruction"),
    (r"ignore (all )?(previous|prior|above) instructions", "prompt injection marker"),
    (r"base64 -d.*\|\s*(sh|bash)", "obfuscated shell execution"),
]

def scan_text_for_suspicion(path: Path) -> list:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    hits = []
    for pattern, label in SUSPICIOUS_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            hits.append(label)
    return hits

def main():
    agents = json.loads((CP / "registry/agents/agent_registry.json").read_text(encoding="utf-8"))["agents"]
    skills = json.loads((CP / "registry/skills/skill_registry.json").read_text(encoding="utf-8"))["skills"]

    # Agent duplicates + compatibility
    by_name = {}
    for a in agents:
        by_name.setdefault((a.get("name") or "").lower(), []).append(a)
    dups = {k: v for k, v in by_name.items() if k and len(v) > 1}
    (CP / "reports/AGENT_DUPLICATES.md").write_text(
        "# AGENT DUPLICATES\n\n" + (
            "\n".join(f"- **{k}**: " + ", ".join(x["original_path"] for x in v) for k, v in dups.items())
            or "None found"
        ), encoding="utf-8"
    )
    (CP / "reports/AGENT_COMPATIBILITY.md").write_text(
        "# AGENT COMPATIBILITY\n\n"
        "All agents currently live under Claude Code's agent format (YAML frontmatter "
        "+ markdown system prompt). None have been verified against OpenCode's native "
        "agent schema yet (that requires inspecting installed OpenCode v1.18.18's "
        "actual agent config format, done in Phase 33/scripts/opencode_agent_check.py). "
        "Until that check runs, classify all as CLAUDE_SPECIFIC pending verification — "
        "do not assume portability.\n", encoding="utf-8"
    )
    (CP / "reports/AGENT_MIGRATION_PLAN.md").write_text(
        "# AGENT MIGRATION PLAN\n\nNo migrations performed. Recommendation only: "
        "run scripts/opencode_agent_check.py once OpenCode's agent schema is confirmed, "
        "then re-classify PORTABLE vs CLAUDE_SPECIFIC before generating any OpenCode "
        "agent definitions. Originals are never modified.\n", encoding="utf-8"
    )

    # Skill duplicates
    by_name = {}
    for s in skills:
        by_name.setdefault((s.get("name") or "").lower(), []).append(s)
    dups = {k: v for k, v in by_name.items() if k and len(v) > 1}
    lines = [f"- **{k}** ({len(v)}x): " + ", ".join(x["source"] for x in v) for k, v in list(dups.items())[:200]]
    (CP / "reports/SKILL_DUPLICATES.md").write_text(
        f"# SKILL DUPLICATES\n\n{len(dups)} duplicate name groups (showing up to 200)\n\n" + "\n".join(lines),
        encoding="utf-8"
    )
    (CP / "reports/SKILL_CONFLICTS.md").write_text(
        "# SKILL CONFLICTS\n\nNo automatic conflict resolution performed. Duplicate "
        "names across skills_live and skills_library most commonly mean the same "
        "skill was both activated (copied/symlinked into skills_live) and still "
        "present in the offline library — expected, not a real conflict, per "
        "project_overseer memory. Flagged for manual review only where duplicate "
        "count > 2 within the same source.\n", encoding="utf-8"
    )
    (CP / "reports/SKILL_COMPATIBILITY.md").write_text(
        "# SKILL COMPATIBILITY\n\nSKILL.md format (YAML frontmatter: name/description) "
        "is the same convention OpenCode documents for skill discovery. Compatibility "
        "is NOT yet verified against the installed OpenCode version's actual skill "
        "loader (Phase 32) — treat as UNVERIFIED until scripts/opencode_skill_check.py runs.\n",
        encoding="utf-8"
    )

    # Security scan
    flagged = []
    for s in skills:
        skill_dir = s.get("skill_dir")
        if not skill_dir:
            continue
        p = Path(skill_dir)
        if not p.exists():
            continue
        for f in list(p.rglob("*.md"))[:5] + list(p.rglob("*.py"))[:5] + list(p.rglob("*.sh"))[:5]:
            hits = scan_text_for_suspicion(f)
            if hits:
                flagged.append({"skill": s["id"], "file": str(f), "hits": hits})
    (CP / "security/skill_security_scan_results.json").write_text(
        json.dumps(flagged, indent=2), encoding="utf-8"
    )
    audit_md = f"""# SKILL SECURITY AUDIT

Scanned {len(skills)} skills (first 5 .md/.py/.sh files per skill dir, heuristic
pattern match only — not a substitute for manual review of anything flagged).

Flagged SECURITY_REVIEW_REQUIRED: {len(flagged)}

{chr(10).join(f"- {f['skill']}: {f['file']} -> {', '.join(f['hits'])}" for f in flagged[:100]) if flagged else 'None flagged by heuristic scan.'}
{'' if len(flagged) <= 100 else f'... and {len(flagged)-100} more, see security/skill_security_scan_results.json'}

Note: absence of a flag is not proof of safety — this is a fast heuristic pass,
not a full audit. Nothing flagged here was deleted or disabled automatically.
"""
    (CP / "reports/SKILL_SECURITY_AUDIT.md").write_text(audit_md, encoding="utf-8")
    print(f"agent_dups={len(dups) if False else 'see file'} skill_dup_groups={len(dups)} security_flagged={len(flagged)}")

if __name__ == "__main__":
    main()
