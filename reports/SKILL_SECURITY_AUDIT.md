# SKILL SECURITY AUDIT

Scanned 3812 skills (first 5 .md/.py/.sh files per skill dir, heuristic
pattern match only — not a substitute for manual review of anything flagged).

Flagged SECURITY_REVIEW_REQUIRED: 70

- gcp-cloud-run: C:\Users\Zoher\.claude\skills\gcp-cloud-run\SKILL.md -> destructive root delete
- 007: C:\Users\Zoher\.claude\skills-library\007\SKILL.md -> possible env exfiltration
- 007: C:\Users\Zoher\.claude\skills-library\007\references\ai-agent-security.md -> prompt injection marker
- 007: C:\Users\Zoher\.claude\skills-library\007\references\owasp-checklists.md -> prompt injection marker
- 007: C:\Users\Zoher\.claude\skills-library\007\scripts\scanners\dependency_scanner.py -> pipe-to-shell download, possible env exfiltration
- agent-evaluation: C:\Users\Zoher\.claude\skills-library\agent-evaluation\SKILL.md -> prompt injection marker
- apify-actor-development: C:\Users\Zoher\.claude\skills-library\apify-actor-development\SKILL.md -> pipe-to-shell download
- apify-ultimate-scraper: C:\Users\Zoher\.claude\skills-library\apify-ultimate-scraper\SKILL.md -> possible env exfiltration
- audit-skills: C:\Users\Zoher\.claude\skills-library\audit-skills\SKILL.md -> pipe-to-shell download, destructive root delete
- aws-penetration-testing: C:\Users\Zoher\.claude\skills-library\aws-penetration-testing\SKILL.md -> security-disable instruction
- azure-monitor-opentelemetry-ts: C:\Users\Zoher\.claude\skills-library\azure-monitor-opentelemetry-ts\SKILL.md -> possible env exfiltration
- azure-resource-manager-redis-dotnet: C:\Users\Zoher\.claude\skills-library\azure-resource-manager-redis-dotnet\SKILL.md -> security-disable instruction
- bun-development: C:\Users\Zoher\.claude\skills-library\bun-development\SKILL.md -> pipe-to-shell download
- citation-management: C:\Users\Zoher\.claude\skills-library\citation-management\scripts\generate_schematic_ai.py -> possible env exfiltration
- claude-code-expert: C:\Users\Zoher\.claude\skills-library\claude-code-expert\SKILL.md -> pipe-to-shell download
- claude-in-chrome-troubleshooting: C:\Users\Zoher\.claude\skills-library\claude-in-chrome-troubleshooting\SKILL.md -> destructive root delete
- clinical-decision-support: C:\Users\Zoher\.claude\skills-library\clinical-decision-support\scripts\generate_schematic_ai.py -> possible env exfiltration
- cloud-penetration-testing: C:\Users\Zoher\.claude\skills-library\cloud-penetration-testing\SKILL.md -> pipe-to-shell download
- comfyui-gateway: C:\Users\Zoher\.claude\skills-library\comfyui-gateway\references\integration.md -> possible env exfiltration
- configure-ecc: C:\Users\Zoher\.claude\skills-library\configure-ecc\SKILL.md -> destructive root delete
- configure-ecc: C:\Users\Zoher\.claude\skills-library\configure-ecc\configure-ecc\SKILL.md -> destructive root delete
- configure-ecc: C:\Users\Zoher\.claude\skills-library\configure-ecc\configure-ecc\SKILL.md -> destructive root delete
- convex: C:\Users\Zoher\.claude\skills-library\convex\SKILL.md -> possible env exfiltration
- cred-omega: C:\Users\Zoher\.claude\skills-library\cred-omega\SKILL.md -> possible env exfiltration
- electron-development: C:\Users\Zoher\.claude\skills-library\electron-development\SKILL.md -> security-disable instruction
- configure-ecc: C:\Users\Zoher\.claude\skills-library\everything-claude-code\docs\ja-JP\skills\configure-ecc\SKILL.md -> destructive root delete
- configure-ecc: C:\Users\Zoher\.claude\skills-library\everything-claude-code\docs\zh-CN\skills\configure-ecc\SKILL.md -> destructive root delete
- hookify-rules: C:\Users\Zoher\.claude\skills-library\everything-claude-code\docs\zh-CN\skills\hookify-rules\SKILL.md -> destructive root delete
- perl-security: C:\Users\Zoher\.claude\skills-library\everything-claude-code\docs\zh-CN\skills\perl-security\SKILL.md -> destructive root delete
- configure-ecc: C:\Users\Zoher\.claude\skills-library\everything-claude-code\skills\configure-ecc\SKILL.md -> destructive root delete
- hookify-rules: C:\Users\Zoher\.claude\skills-library\everything-claude-code\skills\hookify-rules\SKILL.md -> destructive root delete
- perl-security: C:\Users\Zoher\.claude\skills-library\everything-claude-code\skills\perl-security\SKILL.md -> destructive root delete
- evolution: C:\Users\Zoher\.claude\skills-library\evolution\SKILL.md -> pipe-to-shell download
- careful: C:\Users\Zoher\.claude\skills-library\gstack-careful\SKILL.md -> destructive root delete
- careful: C:\Users\Zoher\.claude\skills-library\gstack-careful\bin\check-careful.sh -> destructive root delete
- hookify-rules: C:\Users\Zoher\.claude\skills-library\hookify-rules\SKILL.md -> destructive root delete
- hookify-rules: C:\Users\Zoher\.claude\skills-library\hookify-rules\hookify-rules\SKILL.md -> destructive root delete
- hookify-rules: C:\Users\Zoher\.claude\skills-library\hookify-rules\hookify-rules\SKILL.md -> destructive root delete
- hypothesis-generation: C:\Users\Zoher\.claude\skills-library\hypothesis-generation\scripts\generate_schematic_ai.py -> possible env exfiltration
- latex-posters: C:\Users\Zoher\.claude\skills-library\latex-posters\scripts\generate_schematic_ai.py -> possible env exfiltration
- linkerd-patterns: C:\Users\Zoher\.claude\skills-library\linkerd-patterns\SKILL.md -> pipe-to-shell download
- linux-privilege-escalation: C:\Users\Zoher\.claude\skills-library\linux-privilege-escalation\SKILL.md -> pipe-to-shell download
- literature-review: C:\Users\Zoher\.claude\skills-library\literature-review\SKILL.md -> pipe-to-shell download
- literature-review: C:\Users\Zoher\.claude\skills-library\literature-review\scripts\generate_schematic_ai.py -> possible env exfiltration
- loki-mode: C:\Users\Zoher\.claude\skills-library\loki-mode\CHANGELOG.md -> destructive root delete
- loki-mode: C:\Users\Zoher\.claude\skills-library\loki-mode\autonomy\run.sh -> destructive root delete
- markitdown: C:\Users\Zoher\.claude\skills-library\markitdown\scripts\generate_schematic_ai.py -> possible env exfiltration
- nestjs-expert: C:\Users\Zoher\.claude\skills-library\nestjs-expert\SKILL.md -> possible env exfiltration
- parallel-web: C:\Users\Zoher\.claude\skills-library\parallel-web\SKILL.md -> pipe-to-shell download
- peer-review: C:\Users\Zoher\.claude\skills-library\peer-review\scripts\generate_schematic_ai.py -> possible env exfiltration
- perl-security: C:\Users\Zoher\.claude\skills-library\perl-security\SKILL.md -> destructive root delete
- perl-security: C:\Users\Zoher\.claude\skills-library\perl-security\perl-security\SKILL.md -> destructive root delete
- perl-security: C:\Users\Zoher\.claude\skills-library\perl-security\perl-security\SKILL.md -> destructive root delete
- pptx-posters: C:\Users\Zoher\.claude\skills-library\pptx-posters\scripts\generate_schematic_ai.py -> possible env exfiltration
- research-grants: C:\Users\Zoher\.claude\skills-library\research-grants\scripts\generate_schematic_ai.py -> possible env exfiltration
- research-lookup: C:\Users\Zoher\.claude\skills-library\research-lookup\SKILL.md -> pipe-to-shell download
- research-lookup: C:\Users\Zoher\.claude\skills-library\research-lookup\scripts\generate_schematic_ai.py -> possible env exfiltration
- scholar-evaluation: C:\Users\Zoher\.claude\skills-library\scholar-evaluation\scripts\generate_schematic_ai.py -> possible env exfiltration
- scientific-critical-thinking: C:\Users\Zoher\.claude\skills-library\scientific-critical-thinking\scripts\generate_schematic_ai.py -> possible env exfiltration
- scientific-schematics: C:\Users\Zoher\.claude\skills-library\scientific-schematics\scripts\generate_schematic_ai.py -> possible env exfiltration
- scientific-slides: C:\Users\Zoher\.claude\skills-library\scientific-slides\scripts\generate_schematic_ai.py -> possible env exfiltration
- scientific-writing: C:\Users\Zoher\.claude\skills-library\scientific-writing\scripts\generate_schematic_ai.py -> possible env exfiltration
- sharp-edges: C:\Users\Zoher\.claude\skills-library\sharp-edges\SKILL.md -> security-disable instruction
- skill-audit: C:\Users\Zoher\.claude\skills-library\skill-audit\SKILL.md -> prompt injection marker
- treatment-plans: C:\Users\Zoher\.claude\skills-library\treatment-plans\scripts\generate_schematic_ai.py -> possible env exfiltration
- uv-package-manager: C:\Users\Zoher\.claude\skills-library\uv-package-manager\resources\implementation-playbook.md -> pipe-to-shell download
- varlock: C:\Users\Zoher\.claude\skills-library\varlock\SKILL.md -> pipe-to-shell download
- venue-templates: C:\Users\Zoher\.claude\skills-library\venue-templates\scripts\generate_schematic_ai.py -> possible env exfiltration
- vulnerability-scanner: C:\Users\Zoher\.claude\skills-library\vulnerability-scanner\SKILL.md -> security-disable instruction
- wordpress-penetration-testing: C:\Users\Zoher\.claude\skills-library\wordpress-penetration-testing\SKILL.md -> prompt injection marker


Note: absence of a flag is not proof of safety — this is a fast heuristic pass,
not a full audit. Nothing flagged here was deleted or disabled automatically.
