import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from adapters.cli_dispatch import dispatch  # noqa: E402


def _cmd(**kw):
    r = dispatch("t-flags", prompt="hi", dry_run=True, **kw)
    assert r["status"] == "DRY_RUN", r
    return r["command_preview"]


def test_claude_gets_model_and_effort():
    c = _cmd(provider="anthropic", model_id="claude-haiku-5-5", effort="low")
    assert c[:2] == ["claude", "-p"] and c[c.index("--model") + 1] == "claude-haiku-5-5"
    assert c[c.index("--effort") + 1] == "low"


def test_codex_gets_model_and_effort():
    c = _cmd(provider="openai", model_id="gpt-6-sol", effort="high")
    assert c[c.index("-m") + 1] == "gpt-6-sol" and "model_reasoning_effort=high" in c


def test_no_model_means_no_flag():
    assert "--model" not in _cmd(provider="anthropic")


def test_effort_follows_floor_and_criticality():
    from router.smart import effort
    assert effort("C", False, "anthropic") == "low"
    assert effort("A", False, "anthropic") == "high"
    assert effort("A", True, "anthropic") == "xhigh"
    assert effort("A", True, "openai") == "high"
    assert effort("B", False, "opencode-go") is None


def test_npm_shim_bypasses_cmd_so_newlines_survive(tmp_path):
    import subprocess
    from adapters.cli_dispatch import _resolve
    r = _resolve(["codex", "exec", "line1\nline2"])
    if r[0] == "codex":
        return  # codex not installed on this machine: nothing to check
    assert r[0] != "cmd", f"still routed through cmd.exe: {r[:3]}"
    # end-to-end: node receives a multi-line argument intact
    probe = tmp_path / "echo_args.js"
    probe.write_text("process.stdout.write(JSON.stringify(process.argv.slice(2)))")
    out = subprocess.run([r[0], str(probe), "a\nb"], capture_output=True, text=True).stdout
    import json
    assert json.loads(out) == ["a" + chr(10) + "b"], out
