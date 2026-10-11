import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import sync_models as s  # noqa: E402


def _m(provider, mid, tier="B", access="SUBSCRIPTION_ACCESS"):
    return {"provider": provider, "model_id": mid, "display_name": mid, "capability_tier": tier,
            "access_type": access, "task_types": []}


def test_reconcile_retires_adds_and_keeps_judgements():
    models = [_m("opencode-go", "opencode-go/kimi-k3", "A"), _m("opencode-go", "opencode-go/old-model", "B"),
              _m("ollama", "qwen2.5-coder:7b", "C"), _m("anthropic", "claude-opus-5", "A"),
              _m("openai", "gpt-5.6-terra", "B")]
    out, changes = s.reconcile(models, opencode={"opencode-go/kimi-k3", "opencode-go/new-model"},
                               ollama={"qwen2.5-coder:7b"}, codex={"gpt-6-sol"})
    by = {m["model_id"]: m for m in out}
    assert "NOT CONFIGURED" in by["opencode-go/old-model"]["access_type"]          # vanished -> unroutable
    assert "NOT CONFIGURED" in by["claude-opus-5"]["access_type"]                   # superseded Claude id
    assert "NOT CONFIGURED" in by["gpt-5.6-terra"]["access_type"]                   # Codex moved to gpt-6-sol
    assert by["opencode-go/kimi-k3"]["capability_tier"] == "A"                      # human judgement untouched
    assert "NOT CONFIGURED" not in by["opencode-go/kimi-k3"]["access_type"]
    assert by["opencode-go/new-model"]["capability_tier"] == "UNKNOWN"              # new = never routed yet
    assert by["gpt-6-sol"]["capability_tier"] == "UNKNOWN"
    assert by["claude-opus-5-5"]["capability_tier"] == "A"
    assert "NOT CONFIGURED" in by["claude-fable-5-1"]["access_type"]                # credits -> not routed


def test_reconcile_is_idempotent():
    models = [_m("ollama", "qwen2.5-coder:7b", "C")]
    once, _ = s.reconcile(models, set(), {"qwen2.5-coder:7b"}, set())
    twice, changes = s.reconcile(once, set(), {"qwen2.5-coder:7b"}, set())
    assert changes == [] and len(once) == len(twice)
