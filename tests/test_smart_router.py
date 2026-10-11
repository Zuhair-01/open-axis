import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from router import smart  # noqa: E402
from router.classifier import classify  # noqa: E402


def test_risk_raises_floor_and_marks_critical():
    t = "add a refund button to the ShamCash payment flow"
    a = smart.assess(t, classify(t))
    assert a["floor"] == "A" and a["critical"] and a["risk"]
    assert smart.effort(a["floor"], a["critical"], "anthropic") == "xhigh"


def test_risk_never_lowers():
    t = "design a system for analytics"
    assert smart.assess(t, classify(t))["floor"] == "A"


def test_cascade_only_with_oracle_and_safe_type(tmp_path):
    t = "implement a new function to parse csv rows"
    c = classify(t)
    assert smart.assess(t, c, cwd=tmp_path)["try_floors"] == [c["required_capability_floor"]]  # no oracle
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    (tmp_path / "tests").mkdir()
    a = smart.assess(t, c, cwd=tmp_path)
    assert a["oracle"] and a["try_floors"] == ["C", "B"]


def test_no_cascade_for_risky_work_even_with_oracle(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "tests").mkdir()
    t = "implement the login password reset endpoint"
    a = smart.assess(t, classify(t), cwd=tmp_path)
    assert a["try_floors"] == ["A"] and a["critical"]


def test_learning_reranks_only_after_enough_evidence(tmp_path):
    log = tmp_path / "o.jsonl"
    cands = [{"model_id": "m1"}, {"model_id": "m2"}]
    rows = [{"task_type": "IMPLEMENTATION", "model": "m2", "verdict": "PASS"}] * 2
    log.write_text("\n".join(json.dumps(r) for r in rows))
    assert [m["model_id"] for m in smart.rerank(cands, "IMPLEMENTATION", log)] == ["m1", "m2"]  # n=2 < 3
    rows += [{"task_type": "IMPLEMENTATION", "model": "m2", "verdict": "PASS"},
             {"task_type": "IMPLEMENTATION", "model": "m1", "verdict": "FAIL"}] * 3
    log.write_text("\n".join(json.dumps(r) for r in rows))
    assert [m["model_id"] for m in smart.rerank(cands, "IMPLEMENTATION", log)] == ["m2", "m1"]
