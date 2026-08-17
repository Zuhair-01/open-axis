"""Full test corpus per the clarity-gate hardening spec (2026-08-15).
Run: python tests/test_clarity_gate.py  (or via pytest)
"""
import sys
from pathlib import Path

CP = Path(r"C:\AI\control-plane")
sys.path.insert(0, str(CP))
from router.clarity_gate import is_obviously_clear, classify_clarity

# ---- SAFE TRUE CASES -------------------------------------------------------
TRUE_CASES = [
    "run tests", "run the tests", "run test suite", "run the test suite",
    "show status", "show the status", "show usage", "show budget",
    "list tasks", "list models", "check auth", "check status", "show health",
    "fix src/auth.ts line 42",
    "fix the error in src/auth.ts line 42",
    "check backend/api.py around line 81",
    "edit config.py",
    "implement the function in utils.py",
    "inspect src/main.py",
    "lint backend/config.py",
    "run pytest", "lint backend", "run build",
]

# ---- MUST REMAIN FALSE -----------------------------------------------------
FALSE_CASES = [
    "what do you think about src/auth.ts?",
    "analyze src/main.py",
    "should we refactor utils.py?",
    "redesign the architecture in backend/api.py",
    "make the application better",
    "improve the architecture",
    "fix performance",
    "what is v2.5?",
    "compare version 2.5",
    "what does example.com mean?",
    "analyze config.py before we change the architecture",
    "build the best possible version of auth.py",
    "optimize everything",
    "why are the tests failing?",
    "what do you think about the status?",
    "analyze usage patterns",
    "how should we improve the test suite?",
    "should we refactor auth.py?",
    "why is auth.py important?",
    "compare auth.py with server.py",
    "analyze auth.py",
]

def test_true_cases():
    failures = [c for c in TRUE_CASES if not is_obviously_clear(c)]
    assert not failures, f"expected clear=True, got False for: {failures}"

def test_false_cases():
    failures = [c for c in FALSE_CASES if is_obviously_clear(c)]
    assert not failures, f"expected clear=False, got True for: {failures}"

# ---- EDGE CASES -------------------------------------------------------------
def test_empty_and_none():
    assert is_obviously_clear("") is False
    assert is_obviously_clear("   ") is False
    assert is_obviously_clear(None) is False

def test_very_long_task_stays_false():
    long_task = "please help me understand and think through " * 20 + "the codebase"
    assert is_obviously_clear(long_task) is False

def test_mixed_case():
    assert is_obviously_clear("RUN TESTS") is True
    assert is_obviously_clear("Fix Src/Auth.ts Line 42".lower()) is True

def test_windows_and_unix_paths():
    assert is_obviously_clear(r"edit C:\project\config.py") is True
    assert is_obviously_clear("edit ./config.py") is True
    assert is_obviously_clear("edit ../src/main.ts") is True

def test_hyphen_and_underscore_filenames():
    assert is_obviously_clear("edit my-config.py") is True
    assert is_obviously_clear("edit my_config.py") is True

def test_multiple_paths_and_line_refs_still_clear():
    assert is_obviously_clear("fix src/a.py line 10 and src/b.py line 20") is True

def test_quoted_filename():
    assert is_obviously_clear('edit "config.py"') is True

def test_question_words_containing_trigger_keywords_stay_false():
    assert is_obviously_clear("why are the tests failing?") is False
    assert is_obviously_clear("what do you think about the status?") is False
    assert is_obviously_clear("analyze usage patterns") is False

# ---- PROPERTY / SAFETY: file mention alone is never sufficient ------------
def test_file_mention_alone_never_sufficient():
    conceptual_with_file = [
        "should we refactor auth.py?",
        "why is auth.py important?",
        "compare auth.py with server.py",
        "analyze auth.py",
    ]
    for task in conceptual_with_file:
        d = classify_clarity(task)
        assert d.clear is False, f"file mention alone bypassed triage for: {task!r} ({d})"

def test_decision_object_shape():
    d = classify_clarity("run tests")
    assert d.clear is True
    assert 0.0 <= d.confidence <= 1.0
    assert d.reason == "exact_utility_command"
    assert d.gate_type == "utility"

def test_no_network_or_filesystem_access():
    # deterministic/local: same input, same output, no side effects to check
    # for - just verify repeated calls are stable and fast is implicit
    # (no I/O in the module at all - inspected by code review, not testable
    # generically here beyond determinism).
    task = "fix src/auth.ts line 42"
    results = {classify_clarity(task) for _ in range(5)}
    assert len(results) == 1

if __name__ == "__main__":
    import traceback
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    passed, failed = 0, []
    for t in tests:
        try:
            t()
            passed += 1
            print(f"PASS {t.__name__}")
        except Exception as e:
            failed.append((t.__name__, str(e)))
            print(f"FAIL {t.__name__}: {e}")
            traceback.print_exc()
    print(f"\n{passed}/{len(tests)} passed")
    if failed:
        sys.exit(1)
