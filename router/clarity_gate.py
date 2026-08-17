"""Stage A of the two-stage triage system: a LOCAL, deterministic, free,
side-effect-free risk filter that decides whether a task is obviously clear
enough to skip the real triage model call.

Why this exists: every task was paying a real ~5-15s cheap-model round trip
before this, even for "run tests" or "fix the bug in src/auth.ts line 42" -
things with no genuine ambiguity to resolve. That latency/cost is pure
waste for obviously-specified tasks.

Core safety principle (asymmetric cost, by design):
  FALSE POSITIVE (ambiguous task incorrectly marked clear) -> wrong routing,
    no clarifying question ever asked, real work potentially wasted. DANGEROUS.
  FALSE NEGATIVE (clear task sent to triage anyway) -> a few extra seconds
    of latency. ACCEPTABLE.
So every rule here is deliberately narrow. When genuinely uncertain, this
returns clear=False and lets the real triage model handle it - never the
other way around.

Why a file path alone is NOT sufficient evidence: "analyze src/main.py",
"should we refactor utils.py?", and "what do you think about auth.ts?" all
mention a real file but are open-ended, conceptual, or interrogative - they
need real judgment, not a rubber-stamp bypass. A file path only counts as
evidence when paired with either (a) a line-level reference, or (b) a
recognized, execution-oriented action verb at the start of a short,
non-interrogative request.

Deterministic, local, extremely fast, no network, no filesystem access, no
model calls - classification is from the task string alone.
"""
import re
from dataclasses import dataclass

@dataclass(frozen=True)
class ClarityDecision:
    clear: bool
    confidence: float  # advisory only, NOT a calibrated probability
    reason: str
    gate_type: str

# --- utility commands: exact, tightly-bounded deterministic requests -------
# Deliberately narrow - "show status" bypasses, "what do you think about the
# status?" must not. Optional "please"/"me"/"the" padding is allowed since
# it doesn't add ambiguity, only politeness/filler.
_UTILITY_TARGETS = r"(tests?|test suite|status|usage|budget|health|routing|providers|tasks|models|auth)"
UTILITY_RE = re.compile(
    rf"^(please\s+)?(run|show|list|check)(\s+me)?(\s+the)?\s+{_UTILITY_TARGETS}$",
    re.IGNORECASE,
)

# --- file path detection: conservative, avoids version numbers/domains -----
# Requires EITHER a path separator (src/auth.ts, backend\api.py, ./x.py)
# OR a recognized code/config extension - "v2.5", "3.14", and "example.com"
# must never match (no separator, and .5/.com aren't in this whitelist).
_CODE_EXTENSIONS = (
    r"py|ts|tsx|js|jsx|go|rs|java|rb|php|c|cpp|h|hpp|cs|kt|swift|"
    r"yaml|yml|json|toml|ini|cfg|conf|md|txt|html|htm|css|scss|"
    r"sql|sh|bash|ps1|bat|env|xml|vue|svelte"
)
FILE_PATH_RE = re.compile(
    rf"(?:[\w\-]+[/\\])+[\w\-]+\.(?:{_CODE_EXTENSIONS})\b"  # has a path separator
    rf"|\b[\w\-]+\.(?:{_CODE_EXTENSIONS})\b",                # bare filename, whitelisted ext only
    re.IGNORECASE,
)

LINE_REF_RE = re.compile(r"\b(around\s+)?lines?\s+\d+\b", re.IGNORECASE)

# --- action vocabulary -------------------------------------------------------
# Execution/inspection/mutation verbs where "VERB + real file path" is
# unambiguous. Deliberately excludes vague quality/direction verbs
# (improve, optimize, analyze, redesign, build) that spec explicitly wants
# routed to real triage - "analyze config.py" needs judgment, "edit
# config.py" doesn't.
ACTION_VERBS = {
    "fix", "edit", "modify", "change", "update", "implement", "add",
    "remove", "delete", "rename", "refactor", "debug", "test", "run",
    "inspect", "check", "open", "review", "lint", "format",
}

# Narrower still: verbs safe enough for a BARE short command with no file
# path at all ("run pytest", "lint backend"). Excludes "fix"/"edit"/etc
# deliberately - "fix performance" must NOT bypass (vague target, real
# judgment needed), while "run pytest" safely can (execution-only verb,
# no quality judgment implied).
SHORT_COMMAND_VERBS = {"run", "lint", "inspect", "check", "open", "test"}
VAGUE_TARGETS = {
    "performance", "architecture", "everything", "quality", "code", "it",
    "things", "app", "application", "system", "systems",
}

QUESTION_STARTERS = {
    "what", "why", "should", "how", "do", "does", "is", "are", "would",
    "could", "can", "will",
}

def _is_question(task: str) -> bool:
    if "?" in task:
        return True
    first_word = task.strip().split(" ", 1)[0].lower().strip(",.") if task.strip() else ""
    return first_word in QUESTION_STARTERS

def classify_clarity(task) -> ClarityDecision:
    if not isinstance(task, str) or not task.strip():
        return ClarityDecision(False, 0.99, "empty_or_invalid_input", "model_triage_required")

    t = task.strip()
    t_lower = t.lower()

    if UTILITY_RE.match(t_lower):
        return ClarityDecision(True, 0.99, "exact_utility_command", "utility")

    # Safety override: anything phrased as a question needs real judgment,
    # regardless of what else it mentions (a file, a keyword, etc).
    if _is_question(t):
        return ClarityDecision(False, 0.95, "interrogative_phrasing", "model_triage_required")

    has_path = FILE_PATH_RE.search(t) is not None
    has_line_ref = LINE_REF_RE.search(t) is not None

    if has_path and has_line_ref:
        return ClarityDecision(True, 0.97, "file_and_line_reference", "targeted_file_task")

    words = t_lower.split()
    first_word = words[0].strip(",.") if words else ""

    if has_path and first_word in ACTION_VERBS and len(words) <= 15:
        return ClarityDecision(True, 0.95, "direct_action_with_specific_file", "targeted_file_task")

    if (not has_path and 2 <= len(words) <= 3 and first_word in SHORT_COMMAND_VERBS
            and not any(w.strip(",.") in VAGUE_TARGETS for w in words[1:])):
        return ClarityDecision(True, 0.9, "short_deterministic_command", "short_command")

    return ClarityDecision(False, 0.9, "insufficient_deterministic_evidence", "model_triage_required")

def is_obviously_clear(task: str) -> bool:
    """Backwards-compatible boolean API - existing callers (smart_route.py)
    keep working unchanged."""
    return classify_clarity(task).clear

if __name__ == "__main__":
    import sys
    task = " ".join(sys.argv[1:]) or "run tests"
    d = classify_clarity(task)
    print(f"clear={d.clear} confidence~{d.confidence} reason={d.reason} gate_type={d.gate_type}")
