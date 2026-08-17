"""Phase 12: deterministic-first task classifier. Falls back to UNKNOWN rather
than guessing when confidence is low - never pretend certainty (spec rule).
"""
import re

TASK_TYPE_KEYWORDS = {
    "ARCHITECTURE": [r"\barchitect", r"system design", r"\bADR\b", r"\bmicroservices?\b",
                      r"\bscalab", r"\bmonolith", r"design a system", r"schema design"],
    "SECURITY": [r"\bsecurity\b", r"\bvulnerab", r"\bCVE\b", r"pentest", r"threat model",
                 r"\bexploit", r"\bauth(entication|orization)?\b.*(bug|flaw|bypass)",
                 r"\bencrypt", r"\binjection\b", r"\bxss\b", r"\brace condition\b"],
    "DEBUGGING": [r"\bdebug", r"\bbug\b", r"\bcrash", r"\bfails?\b", r"stack trace",
                  r"\bbroken\b", r"\bnot working\b", r"\bexception\b", r"\berror\b.*\bwhy\b",
                  r"\bunexpected behav"],
    "REFACTOR": [r"\brefactor", r"\bclean\s*up\b", r"\bsimplify\b", r"\bdry\b.*code",
                 r"reduce duplication", r"technical debt"],
    "RESEARCH": [r"\bresearch\b", r"\binvestigate\b", r"compare .* options", r"\btradeoffs?\b",
                 r"\bpros and cons\b", r"\bvs\.?\b", r"which (is|should|approach)", r"\bevaluate\b",
                 r"what('s| is) the (best|difference)"],
    "DOCUMENTATION": [r"\bdocs?\b", r"\breadme\b", r"document", r"\bcomment(s|ing)?\b",
                       r"\bexplain\b", r"\bwrite up\b"],
    "TESTING": [r"\btest(s|ing)?\b", r"\bpytest\b", r"\bjest\b", r"\bunit test", r"\bcoverage\b",
                r"\bmock(s|ing)?\b", r"\be2e\b", r"integration test"],
    "DEVOPS": [r"\bci/?cd\b", r"\bdeploy", r"\bdocker", r"\bkubernetes\b", r"\bpipeline\b",
               r"\binfrastructure\b", r"\bterraform\b", r"\brollout\b"],
    "SIMPLE_EDIT": [r"\brename\b", r"\btypo\b", r"\bformat(ting)?\b", r"\btype hints?\b",
                     r"\blint\b", r"\bstyle\b.*fix"],
    "IMPLEMENTATION": [r"\bimplement", r"\badd feature", r"\bbuild\b", r"\bcreate\b.*(function|endpoint|feature|class)",
                        r"\bapi\b", r"\bendpoint\b", r"\bintegrate\b", r"\bwrite a\b.*(function|script|class)"],
    "PERFORMANCE": [r"\boptimi[sz]e\b", r"\bperformance\b", r"\bslow\b", r"\blatency\b",
                     r"\bbottleneck\b", r"\bmemory leak\b", r"\bN\+1\b"],
}

CAPABILITY_FLOOR_BY_TYPE = {
    "ARCHITECTURE": "A", "SECURITY": "A", "DEBUGGING": "B", "REFACTOR": "B",
    "RESEARCH": "B", "DOCUMENTATION": "C", "TESTING": "C", "DEVOPS": "B",
    "SIMPLE_EDIT": "D", "IMPLEMENTATION": "B", "PERFORMANCE": "B",
    # Real design flaw fixed 2026-08-15: UNKNOWN used to default to Tier B,
    # which meant "I have no idea what this task needs" silently routed to
    # Claude (the scarce/premium leg) as if it were confirmed medium-hard
    # work. Not knowing what a task is isn't evidence it's hard - it's
    # evidence to start cheap (Tier C: haiku / mimo / glm) and let the
    # user escalate (/model opus, etc.) if the cheap attempt falls short.
    "UNKNOWN": "C",
}

def classify(task_description: str) -> dict:
    text = task_description.lower()
    scores = {}
    for task_type, patterns in TASK_TYPE_KEYWORDS.items():
        hits = sum(1 for p in patterns if re.search(p, text))
        if hits:
            scores[task_type] = hits

    if not scores:
        return {
            "task_type": "UNKNOWN",
            "confidence": "low",
            "required_capability_floor": CAPABILITY_FLOOR_BY_TYPE["UNKNOWN"],
            "reason": "no keyword match - do not pretend certainty",
        }

    best = max(scores, key=scores.get)
    total_hits = sum(scores.values())
    confidence = "high" if scores[best] >= 2 and len(scores) == 1 else \
                 "medium" if scores[best] > total_hits / max(len(scores), 1) else "low"
    return {
        "task_type": best,
        "confidence": confidence,
        "required_capability_floor": CAPABILITY_FLOOR_BY_TYPE.get(best, "B"),
        "all_matches": scores,
    }

if __name__ == "__main__":
    import sys, json
    print(json.dumps(classify(" ".join(sys.argv[1:]) or "fix the login bug"), indent=2))
