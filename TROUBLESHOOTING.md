# Troubleshooting

- **Router picks no model / "Required capability unavailable"**: expected behavior
  when no provider meets a task's capability floor — this is a hard safety rule
  (spec Phase 16), not a bug. Check `registry/providers/providers.json` health.
- **OpenCode doesn't see a skill/agent**: check `docs/OVERSEER-RELATIONSHIP.md` —
  OVERSEER-managed skills live under `~/.claude`, not automatically visible to
  OpenCode. Use `registry/skills/skill_registry.json` to find portability status.
- **Backup verification failed**: do not proceed past Phase 1. Check
  `C:\AI\bootstrap\backups\<timestamp>\BACKUP_REPORT.md` for the failure list.
