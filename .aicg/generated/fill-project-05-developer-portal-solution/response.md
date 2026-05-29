The workspace blocks `python3` execution (the SOLUTION.md notes this — graders run the validation commands with their own toolchain). All artifacts are statically authored against the upstream schemas referenced.

## Summary

Authored the project-05-developer-portal capstone solution under `projects/project-05-developer-portal/`:

- `SOLUTION.md` (459 lines) — 6-section AICG contract: catalog as source of truth, golden-path scaffolder, TechDocs, scorecards (advisory, not gating), OIDC + RFC 8693 token exchange, per-component plugin model, adoption funnel KPIs.
- `README.md` / `STEP_BY_STEP.md` / `rubric.md` — index, 8-phase build sequence (~68 h), F1–F8 + NF + 8-step acceptance demo.
- Curated artifacts the SOLUTION points at: `catalog/{catalog-info.yaml,entity-kinds.md,processors.md}`, `scaffolder/{templates.md,training-run-template.yaml}`, `techdocs/{architecture.md,mkdocs.example.yml}`, `scorecards/{scorecards.md,scorecard-definitions.yaml}`, `auth/identity.md`, `plugins/plugin-architecture.md`, `observability/adoption-metrics.md`.
- `SOLUTIONS_INDEX.md` updated to mark project-05 ✅ (2 / 5 projects).

Sources cited are official (Backstage docs, CNCF Platforms White Paper, RFC 6749 / 8693 / 9700, OIDC Core, MkDocs, Prometheus naming, SPIFFE); VeriSwarm used only as a labeled practitioner example. One `<!-- needs-research: ... -->` block flagged in SOLUTION.md for the unconfirmed acceptance-demo step list in the paired learning repo — this blocks auto-merge per source policy.
