# Relationship to the existing OVERSEER/OmniRoute system

`~/.claude/overseer` is a pre-existing, Claude-Code-specific skill routing/bundling
layer (built 2026-07 to 2026-08, per user memory `project_overseer` and
`project_skill_bundle_system_2026`). It already does on-demand skill
loading/routing inside Claude Code sessions.

Per your decision to do the full 45-phase build treating it as a separate asset:
- It is **left completely untouched** (backed up in full to
  `C:\AI\bootstrap\backups\20260815_000737\dot-claude\overseer\`).
- The control plane's `registry/skills/skill_index.json` is a superset covering both
  live and offline skills, independent of OVERSEER's own `index.tsv`/`BUNDLE-REGISTRY.tsv`.
- OVERSEER keeps doing its job for Claude Code sessions. This control plane's
  router/skill selection is what OpenCode (and any future non-Claude-Code client)
  will use instead, since OVERSEER's scripts (`persistent_activation.py`,
  `task_interceptor.py`, etc.) are wired specifically into Claude Code's hook system,
  not verified to run inside OpenCode.
- If later you *do* want to unify them instead of running two parallel skill
  routers, that's a deliberate follow-up decision, not something done silently here.
