"""Ledger logic against an in-memory fake GitHub (no network)."""
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "board"))
import ledger  # noqa: E402


class FakeGH:
    def __init__(self):
        self.issues, self.n = {}, 0

    def __call__(self, *args, input_text=None):
        a = list(args)
        if a[:2] == ["issue", "create"]:
            self.n += 1
            labels = [a[i + 1] for i, v in enumerate(a) if v == "--label"]
            self.issues[self.n] = {"number": self.n, "title": a[a.index("--title") + 1], "body": input_text,
                                   "labels": labels, "state": "OPEN", "comments": []}
            return f"https://github.com/x/y/issues/{self.n}\n"
        n = int(a[2])
        i = self.issues[n]
        if a[:2] == ["issue", "view"]:
            return json.dumps({**i, "labels": [{"name": l} for l in i["labels"]]})
        if a[:2] == ["issue", "edit"]:
            if "--body-file" in a:
                i["body"] = input_text
            for k, v in zip(a, a[1:]):
                if k == "--add-label" and v not in i["labels"]:
                    i["labels"].append(v)
                if k == "--remove-label" and v in i["labels"]:
                    i["labels"].remove(v)
            return ""
        if a[:2] == ["issue", "comment"]:
            i["comments"].append({"body": input_text})
            return ""
        if a[:2] == ["issue", "close"]:
            i["state"] = "CLOSED"
            return ""
        raise AssertionError(a)


@pytest.fixture
def fake(monkeypatch):
    f = FakeGH()
    monkeypatch.setattr(ledger, "gh", f)
    return f


def run(*argv):
    ledger.main(list(argv))


def test_limit_hit_relay_no_step_done_twice(fake, capsys):
    run("new", "Build export", "--steps", "S1 schema;S2 parser;S3 tests;S4 docs", "--tier", "B")
    run("claim", "1", "--engine", "claude", "--session", "a")
    run("check", "1", "S1", "--evidence", "abc123")
    run("check", "1", "S2", "--evidence", "pytest tests/test_parser.py")
    # Codex cannot steal a live lease
    with pytest.raises(SystemExit) as e:
        run("claim", "1", "--engine", "codex", "--session", "b")
    assert e.value.code == 2
    # Claude hits its limit -> handoff checkpoint
    run("handoff", "1", "--next", "S3: write tests for parser edge cases")
    assert "status:handoff" in fake.issues[1]["labels"]
    run("claim", "1", "--engine", "codex", "--session", "b")
    capsys.readouterr()
    run("resume", "1")
    out = capsys.readouterr().out
    assert "done: S1, S2" in out and "todo: S3" in out and "S3: write tests" in out
    # ticking a done step again is refused (no double work)
    with pytest.raises(SystemExit):
        run("check", "1", "S2", "--evidence", "again")
    run("check", "1", "S3", "--evidence", "def456")
    run("check", "1", "S4", "--evidence", "README.md")
    run("close", "1")
    i = fake.issues[1]
    assert i["state"] == "CLOSED" and "status:done" in i["labels"] and "status:handoff" not in i["labels"]
    assert len(re.findall(r"- \[x\] S\d", i["body"])) == 4


def test_expired_lease_can_be_taken(fake):
    run("new", "T", "--steps", "S1 a", "--tier", "C")
    run("claim", "1", "--engine", "claude", "--session", "a", "--lease-min", "0")
    run("claim", "1", "--engine", "opencode", "--session", "z")
    assert ledger.load(1)["lease"]["claimed_by"] == "opencode:z"
