"""Phase 33: generates OpenCode-native agent files from the Claude Code agent
registry, instead of a flat copy. `~/.claude/agents` remains the single
source of truth - nothing there is ever written to.

Why not a plain copy:
- Claude's frontmatter (name/color/emoji/vibe) isn't OpenCode's schema
  (description/mode/model/temperature/permission) - a raw copy carries dead
  keys and misses real ones.
- OpenCode's filename IS the agent name, so Claude's `name:` key is redundant
  there and can drift from the filename if copied verbatim.
- Model assignment: OpenCode's `model` field is meant to say which model this
  agent should run on. That decision belongs to the router's capability-floor
  logic (router/classifier.py + registry/models), not a hardcoded copy. Right
  now (2026-08-15) no provider is authenticated in OpenCode, so `model` is
  deliberately left unset (inherit global default) and the classified
  capability_tier is stamped into `metadata` instead - once you run
  `opencode auth login` and real models are verified, a second pass can fill
  in `model` per tier without re-deriving anything.
- Idempotent via content hash: re-running only rewrites agents whose source
  .md actually changed, so this can be re-run any time without churn.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

CP = Path(r"C:\AI\control-plane")
sys.path.insert(0, str(CP))
from router.classifier import classify

OUT_DIR = Path.home() / ".config" / "opencode" / "agents"
MANIFEST_PATH = CP / "integrations" / "opencode_agent_sync_manifest.json"

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
SLUG_RE = re.compile(r"[^a-z0-9-]")

def slugify(name: str) -> str:
    s = SLUG_RE.sub("-", name.lower().strip()).strip("-")
    s = re.sub(r"-+", "-", s)
    return s[:64] or "agent"

def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

def build_opencode_md(name: str, description: str, body: str, tier: str) -> str:
    desc_escaped = (description or "").replace('"', "'")
    fm = (
        "---\n"
        f'description: "{desc_escaped}"\n'
        "mode: subagent\n"
        "metadata:\n"
        f"  source: claude-code\n"
        f"  capability_tier: {tier}\n"
        f"  synced_by: control-plane opencode_agent_sync.py\n"
        "# model: intentionally unset - no authenticated provider yet, see docs/OPENCODE-HANDOFF.md\n"
        "---\n\n"
    )
    return fm + body.strip() + "\n"

def main():
    registry = json.loads((CP / "registry/agents/agent_registry.json").read_text(encoding="utf-8"))
    manifest = {}
    if MANIFEST_PATH.exists():
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written, skipped, errors = [], [], []

    for a in registry["agents"]:
        if a["source"] != "agents_live" or a["status"] != "ACTIVE":
            continue
        src = Path(a["original_path"])
        try:
            text = src.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            errors.append({"agent": a["id"], "error": str(e)})
            continue
        m = FRONTMATTER_RE.match(text)
        body = m.group(2) if m else text
        content_hash = sha(text)

        slug = slugify(a.get("name") or src.stem)
        prev_hash = manifest.get(slug, {}).get("source_hash")
        if prev_hash == content_hash:
            skipped.append(slug)
            continue

        cls = classify(a.get("description") or "")
        tier = cls["required_capability_floor"]
        out_text = build_opencode_md(slug, a.get("description"), body, tier)
        out_path = OUT_DIR / f"{slug}.md"
        out_path.write_text(out_text, encoding="utf-8")

        manifest[slug] = {
            "source_path": str(src),
            "source_hash": content_hash,
            "output_path": str(out_path),
            "capability_tier": tier,
        }
        written.append(slug)

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({
        "written": len(written), "skipped_unchanged": len(skipped),
        "errors": len(errors), "total_tracked": len(manifest),
        "output_dir": str(OUT_DIR),
    }, indent=2))

if __name__ == "__main__":
    main()
