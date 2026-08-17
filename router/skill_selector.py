"""Phase 7's actual point: the 3,812-skill registry is a capability library,
not something dumped into every prompt. Given a task description, score all
skills by lexical overlap between the task text and each skill's
name+description, return the top N. Dependency-free (no embeddings) - good
enough for keyword-shaped queries; swap in a real embedding index later if
recall turns out to matter more than this session can verify.
"""
import json
import re
import sys
from pathlib import Path

CP = Path(r"C:\AI\control-plane")
STOPWORDS = {"the", "a", "an", "and", "or", "for", "to", "of", "in", "on", "with",
             "this", "that", "is", "are", "please", "i", "want", "need", "using"}

def _tokens(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS and len(w) > 2}

def load_index():
    return json.loads((CP / "registry/skills/skill_index.json").read_text(encoding="utf-8"))

def _build_idf(index: list) -> dict:
    """Real bug found 2026-08-15: a plain overlap-count score let generic
    tokens like 'app' (matches hundreds of skills: mobile-app,
    app-store-optimization, gamified-app...) drown out specific ones like
    'graphql'/'rest' for a query about REST vs GraphQL tradeoffs. IDF fixes
    this dependency-free: a token that appears in almost every skill
    contributes almost nothing to the score; a token that appears in 2 skills
    is a strong, specific signal."""
    import math
    df = {}
    for s in index:
        hay = f"{s.get('name') or ''} {s.get('description') or ''}"
        for tok in _tokens(hay):
            df[tok] = df.get(tok, 0) + 1
    n = len(index)
    return {tok: math.log((n + 1) / (count + 1)) + 1 for tok, count in df.items()}

def select_skills(task_description: str, top_n: int = 10) -> list:
    task_tokens = _tokens(task_description)
    if not task_tokens:
        return []
    index = load_index()
    idf = _build_idf(index)
    scored = []
    for s in index:
        hay = f"{s.get('name') or ''} {s.get('description') or ''}"
        skill_tokens = _tokens(hay)
        overlap = task_tokens & skill_tokens
        if not overlap:
            continue
        name_tokens = _tokens(s.get("name") or "")
        # weight name matches higher than description-only matches, both scaled by IDF
        score = sum(idf.get(t, 1.0) for t in overlap) \
              + 2 * sum(idf.get(t, 1.0) for t in (task_tokens & name_tokens))
        scored.append((score, s))
    scored.sort(key=lambda x: x[0], reverse=True)
    seen_ids, deduped = set(), []
    for _, s in scored:
        if s["id"] in seen_ids:
            continue
        seen_ids.add(s["id"])
        deduped.append(s)
        if len(deduped) >= top_n:
            break
    return deduped

if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) or "set up stripe payment webhook integration"
    for s in select_skills(query):
        line = f"{s['id']:35s} [{s['source']}]  {(s.get('description') or '')[:80]}"
        print(line.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8", errors="replace"))
