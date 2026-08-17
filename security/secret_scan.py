"""Phase 26: secret existence check. Reports FOUND/MISSING/UNVERIFIED only -
never reads or prints a value."""
import os
from pathlib import Path

CANDIDATE_ENV_VARS = [
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY",
    "GROQ_API_KEY", "MISTRAL_API_KEY", "COHERE_API_KEY", "DEEPSEEK_API_KEY",
    "XAI_API_KEY", "OPENROUTER_API_KEY", "AZURE_OPENAI_API_KEY",
]

CANDIDATE_FILES = [
    Path(os.environ["USERPROFILE"]) / ".claude" / ".credentials.json",
    Path(os.environ["USERPROFILE"]) / ".local" / "share" / "opencode" / "auth.json",
]

def check_env() -> dict:
    return {v: ("FOUND" if v in os.environ else "MISSING") for v in CANDIDATE_ENV_VARS}

def check_files() -> dict:
    out = {}
    for f in CANDIDATE_FILES:
        out[str(f)] = "FOUND" if f.exists() else "MISSING"
    return out

if __name__ == "__main__":
    import json
    print(json.dumps({"env_vars": check_env(), "credential_files": check_files()}, indent=2))
