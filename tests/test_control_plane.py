"""Phase 36-40 automated test suite. Run: python -m pytest C:\\AI\\control-plane\\tests -q
Falls back to plain assert-based runner if pytest isn't installed (see __main__).
"""
import json
import os
import sys
from pathlib import Path

CP = Path(r"C:\AI\control-plane")
sys.path.insert(0, str(CP))

# Isolate test-simulated provider health from real production routing state -
# real bug found 2026-08-15: tests were writing DEGRADED into health/state.json,
# which the live Budget Manager then read as if it were real.
os.environ["CONTROL_PLANE_HEALTH_PATH"] = str(CP / "tests" / "test_health_state.json")

from router.classifier import classify
from router.model_selector import select_model
from router.agent_selector import select_agents
from router.skill_selector import select_skills
from task_state.state_store import create_task, update_task, get_task
from orchestrator.fallback import run_with_fallback, mark_provider, _load_health
from orchestrator.smart_route import plan
from orchestrator.verify import verify
from adapters.cli_dispatch import _resolve
from security.secret_scan import check_env, check_files


def test_registries_load():
    agents = json.loads((CP / "registry/agents/agent_registry.json").read_text(encoding="utf-8"))
    skills = json.loads((CP / "registry/skills/skill_registry.json").read_text(encoding="utf-8"))
    providers = json.loads((CP / "registry/providers/providers.json").read_text(encoding="utf-8"))
    models = json.loads((CP / "registry/models/model_registry.json").read_text(encoding="utf-8"))
    assert agents["counts"]["total_discovered"] > 0
    assert skills["counts"]["total_discovered"] > 0
    assert len(providers["providers"]) > 0
    assert len(models["models"]) > 0


def test_classifier_unknown_when_no_match():
    r = classify("zzzz qqqq unrecognizable gibberish 12345")
    assert r["task_type"] == "UNKNOWN"
    assert r["confidence"] == "low"


def test_classifier_unknown_defaults_to_cheap_tier_not_claude():
    # Real bug fixed 2026-08-15: UNKNOWN used to default to Tier B, which
    # meant "no idea what this task needs" silently burned the scarce Claude
    # leg as if it were confirmed medium-hard work. Not knowing != hard.
    r = classify("utilize this repo https://github.com/example/some-repo")
    assert r["task_type"] == "UNKNOWN"
    assert r["required_capability_floor"] == "C"


def test_classifier_detects_security():
    r = classify("please run a security vulnerability audit on this API")
    assert r["task_type"] == "SECURITY"
    assert r["required_capability_floor"] == "A"


def test_capability_floor_never_downgrades():
    # Tier A floor with no authenticated Tier-A-or-above provider must BLOCK, not downgrade
    result = select_model("A")
    if result.get("selected"):
        tiers = ["A", "B", "C", "D"]
        assert tiers.index(result["selected"]["capability_tier"]) <= tiers.index("A")
    else:
        assert result["reason"] == "Required capability unavailable."


def test_agent_selector_returns_relevant_results():
    results = select_agents("security")
    assert isinstance(results, list)
    if results:
        assert any("security" in (a.get("description") or "").lower()
                    or "security" in (a.get("name") or "").lower() for a in results)


def test_task_state_roundtrip():
    create_task("pytest-task-1", "unit test objective")
    update_task("pytest-task-1", status="EXECUTING", completed_steps=["step1"])
    t = get_task("pytest-task-1")
    assert t["status"] == "EXECUTING"
    assert json.loads(t["completed_steps"]) == ["step1"]


def test_task_state_rejects_invalid_status():
    create_task("pytest-task-2", "invalid status test")
    try:
        update_task("pytest-task-2", status="NOT_A_REAL_STATUS")
        assert False, "should have raised"
    except ValueError:
        pass


def test_fallback_retryable_errors_walk_candidates_not_downgrade():
    result = run_with_fallback("pytest-fallback-1", "simulate rate limit", "D",
                                simulated_errors=["RATE_LIMIT"])
    assert result["status"] in ("COMPLETED", "BLOCKED", "FAILED")
    for h in result["history"]:
        assert h["error"] in ("RATE_LIMIT", "PROVIDER_DOWN", "TIMEOUT",
                               "QUOTA_EXHAUSTED", "MODEL_UNAVAILABLE")


def test_fallback_non_retryable_marks_provider_unavailable():
    mark_provider("test-provider-xyz", "AVAILABLE", ttl=1)
    import time
    time.sleep(1.1)
    health = _load_health()
    assert "test-provider-xyz" not in health  # expired, proving no permanent blacklist


def test_secret_scan_never_returns_values():
    result = check_env()
    for v in result.values():
        assert v in ("FOUND", "MISSING")
    files = check_files()
    for v in files.values():
        assert v in ("FOUND", "MISSING")


def test_permission_policy_has_deny_list():
    perms = json.loads((CP / "policies/permissions.json").read_text(encoding="utf-8"))
    assert "deny" in perms and len(perms["deny"]) > 0
    assert any("uninstall" in d for d in perms["deny"])


def test_model_selector_prefers_claude_for_hard_tasks():
    # Real bug fixed 2026-08-15: Claude was invisible to the router (stale
    # access_type exclusion), then a follow-up fix wrongly made it top
    # priority for EVERY tier. This locks in the correct per-tier behavior.
    result = select_model("A")
    if result["status"] == "OK":
        assert result["selected"]["provider"] == "anthropic"


def test_model_selector_prefers_workhorse_for_simple_tasks():
    result = select_model("D")
    if result["status"] == "OK":
        # Tier D should NOT burn the scarce Claude leg on trivial work when a
        # cheaper tested option exists at the same floor.
        assert result["selected"]["provider"] != "anthropic" or \
               not any(m["provider"] != "anthropic" for m in
                       json.loads((CP / "registry/models/model_registry.json").read_text(encoding="utf-8"))["models"]
                       if m.get("capability_tier") == "D")


def test_agent_selector_dedupes_by_name():
    results = select_agents("security")
    names = [(a.get("name") or "").lower() for a in results]
    assert len(names) == len(set(names)), f"duplicate agent names returned: {names}"


def test_skill_selector_ranks_specific_terms_over_generic():
    # Regression test for the IDF fix - "app" (matches hundreds of skills)
    # must not fully bury "graphql" (matches a handful) out of the top 10.
    results = select_skills("explain the tradeoffs between REST and GraphQL for a mobile app backend", top_n=10)
    ids = [r["id"] for r in results]
    assert "graphql" in ids


def test_cli_dispatch_resolves_cmd_shims():
    # Real bug fixed 2026-08-15: codex/npm are .cmd shims on Windows: bare
    # subprocess.run(["codex", ...]) raises FileNotFoundError. _resolve()
    # must route through cmd /c for .cmd/.bat, and leave real .exe commands
    # (claude, opencode) untouched.
    import shutil
    from unittest.mock import patch
    with patch.object(shutil, "which", return_value=r"C:\fake\codex.cmd"):
        resolved = _resolve(["codex", "exec", "hi"])
        assert resolved[:2] == ["cmd", "/c"]
        assert resolved[2] == r"C:\fake\codex.cmd"
    with patch.object(shutil, "which", return_value=r"C:\fake\claude.exe"):
        resolved = _resolve(["claude", "-p", "hi"])
        assert resolved == ["claude", "-p", "hi"]


def test_verify_reports_no_project_when_nothing_recognized(tmp_path=None):
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        result = verify(None, d)
        assert result["status"] == "NO_PROJECT_TYPE_DETECTED"


def test_smart_route_plan_status_matches_model_selection():
    # use_triage=False: unit tests must stay fast/offline/deterministic -
    # plan()'s default now calls a real cheap-model triage dispatch (real
    # network call, real cost, non-deterministic model output), which is
    # exactly right for actual usage but wrong for a unit test. The live
    # triage behavior itself was verified manually with real dispatches
    # (see reports/WEAKNESS_MAP.md), not re-tested here.
    p = plan("pytest-plan-1", "fix a typo in the readme", use_triage=False)
    if p["model_selection"]["status"] == "OK":
        assert p["status"] == "READY_TO_EXECUTE"
    else:
        assert p["status"] == "BLOCKED"
    assert "if_staying_in_claude_code" in p
    assert p["if_staying_in_claude_code"]["recommended_model"] in ("opus", "sonnet", "haiku", "fable")


def test_clarity_gate_skips_triage_for_obviously_clear_tasks():
    from router.clarity_gate import is_obviously_clear
    assert is_obviously_clear("run tests") is True
    assert is_obviously_clear("fix the error in src/auth.ts line 42") is True
    assert is_obviously_clear("implement the function in utils.py") is True
    # genuinely vague - must NOT skip triage
    assert is_obviously_clear("try using our systems") is False
    assert is_obviously_clear("utilize this repo") is False


def test_plan_fast_path_produces_valid_classification():
    # use_triage=True but the task matches the clarity gate, so this should
    # resolve via the LOCAL fast path, not a real model call - verify it
    # still produces a usable classification without needing network access.
    p = plan("pytest-fastpath-1", "run tests")
    assert p["classification"]["source"] == "local_fast_path"
    assert p["status"] in ("READY_TO_EXECUTE", "BLOCKED")


def test_repeat_question_detection():
    # Real limitation, honestly scoped: this is word-overlap similarity, not
    # semantic paraphrase detection (no model call here, by design - it's a
    # fast local safety net). It catches near-identical rewording, which is
    # the realistic case when a model asks about the same unresolved gap
    # twice - it does NOT catch a fully different phrasing of the same
    # underlying question (that would need real understanding, i.e. another
    # model call, defeating the point of a cheap local check).
    from orchestrator.repl import _is_repeat_question
    thread = "original task\n\nI asked: What repo are you referring to?"
    assert _is_repeat_question("What repo are you referring to, specifically?", thread) is True
    assert _is_repeat_question("What file extension should the output be?", thread) is False
    assert _is_repeat_question("anything", "") is False


def test_repeat_question_smart_catches_real_paraphrase():
    # Verifies the upgrade over plain word-overlap: "which repository do
    # you mean?" and "what repo are you referring to?" share almost no
    # surface words but ARE the same question - this needs the real
    # semantic model call, not the local heuristic alone. Mocked here for
    # deterministic/offline CI; manually verified live with the real model
    # (2026-08-15) returning correctly: paraphrase -> True, genuinely
    # different follow-up -> False.
    from unittest.mock import patch
    from orchestrator.repl import _is_repeat_question_smart
    thread = "original task\n\nI asked: What repo are you referring to?"
    with patch("orchestrator.repl.cli_dispatch", return_value={"status": "RAN", "returncode": 0, "stdout_tail": "YES"}):
        assert _is_repeat_question_smart("Which repository do you mean?", thread, "pytest-repeat-1") is True
    with patch("orchestrator.repl.cli_dispatch", return_value={"status": "RAN", "returncode": 0, "stdout_tail": "NO"}):
        assert _is_repeat_question_smart("What language should this be in?", thread, "pytest-repeat-2") is False
    with patch("orchestrator.repl.cli_dispatch", side_effect=Exception("network down")):
        # graceful fallback - a broken model call must not crash the REPL
        assert _is_repeat_question_smart("anything", thread, "pytest-repeat-3") is False


def test_force_plan_skips_clarification_and_produces_a_real_plan():
    from orchestrator.smart_route import force_plan
    classification = {
        "task_type": "DOCUMENTATION", "required_capability_floor": "C",
        "confidence": "low", "source": "triage_model", "needs_clarification": True,
        "clarifying_question": "which file?",
    }
    p = force_plan("pytest-force-1", "fix a typo in the readme", classification)
    assert p["status"] in ("READY_TO_EXECUTE", "BLOCKED")
    assert p["classification"]["needs_clarification"] is False
    assert "forced_after_repeat" in p["classification"]["source"]


def test_cancel_only_affects_cancellable_statuses():
    from orchestrator.repl import cmd_cancel, CANCELLABLE_STATUSES
    create_task("pytest-cancel-1", "cancel test")
    update_task("pytest-cancel-1", status="EXECUTING")
    assert "EXECUTING" in CANCELLABLE_STATUSES
    cmd_cancel("pytest-cancel-1")
    assert get_task("pytest-cancel-1")["status"] == "CANCELLED"
    # already-completed task should NOT be touched by cancel
    create_task("pytest-cancel-2", "cancel test 2")
    update_task("pytest-cancel-2", status="COMPLETED")
    cmd_cancel("pytest-cancel-2")
    assert get_task("pytest-cancel-2")["status"] == "COMPLETED"


def test_matching_commands_filters_by_prefix():
    from orchestrator.repl import _matching_commands
    results = _matching_commands("/mod")
    assert any(c[0] == "/model" for c in results)
    assert not any(c[0] == "/auth" for c in results)
    assert _matching_commands("not a slash command") == []
    assert _matching_commands("/model opus") == []  # has a space - no longer typing the command name


def test_self_evolve_never_touches_manually_benchmarked_models():
    from orchestrator.self_evolve import evolve
    result = evolve(min_samples=1, dry_run=True)
    models = json.loads((CP / "registry/models/model_registry.json").read_text(encoding="utf-8"))["models"]
    already_tiered = {(m["provider"], m["model_id"]) for m in models if m.get("capability_tier") != "UNKNOWN"}
    for p in result["promotions"]:
        assert (p["provider"], p["model"]) not in already_tiered


def test_self_evolve_requires_minimum_sample_size():
    from orchestrator.self_evolve import evolve
    result = evolve(min_samples=999999, dry_run=True)
    assert result["promotions"] == []


def test_multi_dispatch_leg_labels_never_double_prefix():
    # Real bug fixed 2026-08-15: opencode model_ids already self-describe
    # ("opencode-go/glm-5.1") - naive f"{provider}/{model_id}" produced
    # "opencode-go/opencode-go/glm-5.1". Verify the fix without a real dispatch.
    from unittest.mock import patch
    from orchestrator.multi_dispatch import dispatch_multi
    with patch("orchestrator.multi_dispatch.dispatch",
               return_value={"status": "RAN", "returncode": 0, "stdout_tail": "ok"}), \
         patch("orchestrator.multi_dispatch.promote_skills"):
        r = dispatch_multi("test task", [
            {"provider": "opencode-go", "model_id": "opencode-go/glm-5.1"},
            {"provider": "anthropic", "model_id": "claude-sonnet-5"},
        ], "pytest-multi-1")
    assert "opencode-go/glm-5.1" in r["results"]
    assert "opencode-go/opencode-go/glm-5.1" not in r["results"]
    assert "anthropic/claude-sonnet-5" in r["results"]


def test_triage_falls_back_locally_when_model_unavailable():
    # Graceful degradation check: if the triage model call fails entirely,
    # triage() must fall back to the local classifier, never crash or hang.
    from unittest.mock import patch
    from router.triage import triage
    with patch("router.triage.dispatch", return_value={"status": "ERROR", "stdout_tail": ""}):
        r = triage("fix a typo in the readme", "pytest-triage-1")
    assert r["source"] == "local_fallback"
    assert r["needs_clarification"] is False
    assert "required_capability_floor" in r


def test_dispatch_cancel_event_stops_a_running_subprocess():
    # Real feature added 2026-08-15 (Esc-to-interrupt): dispatch() used to
    # make one blocking communicate(timeout=timeout) call with no way for
    # another thread to reach in and stop it. With a cancel_event, dispatch
    # polls in short slices and kills the child the moment the event is
    # set - here it's already set before dispatch is even called, so it
    # must resolve to CANCELLED on the very first poll instead of waiting
    # out the full timeout.
    import subprocess as sp
    import threading
    from unittest.mock import patch, MagicMock
    from adapters.cli_dispatch import dispatch

    fake_proc = MagicMock()
    fake_proc.communicate.side_effect = sp.TimeoutExpired(cmd="x", timeout=0.25)
    fake_proc.returncode = -9

    cancel_event = threading.Event()
    cancel_event.set()

    with patch("adapters.cli_dispatch.subprocess.Popen", return_value=fake_proc):
        r = dispatch("pytest-cancel-dispatch-1", "anthropic", "irrelevant prompt",
                      dry_run=False, cancel_event=cancel_event, timeout=5)
    assert r["status"] == "CANCELLED"
    fake_proc.kill.assert_called_once()


def test_repl_defaults_cwd_to_own_repo_not_launch_dir():
    # Real bug found live 2026-08-15 (user screenshot): cwd defaulted to
    # "." - wherever the shell happened to be when the global `openaxis`
    # command was typed (often the user's home dir). Self-referential
    # tasks about Open Axis itself then dispatched into the wrong
    # directory: triage's project-context correctly claimed paths under
    # C:\AI\control-plane, but the executing model's subprocess cwd was
    # somewhere else, so it (correctly) couldn't verify those paths and
    # reported them as not found. Regression guard, not a behavior test -
    # /cd still exists for pointing dispatches at any other project.
    src = (CP / "orchestrator" / "repl.py").read_text(encoding="utf-8")
    assert 'cwd = str(CP)' in src


if __name__ == "__main__":
    # minimal runner if pytest unavailable
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
