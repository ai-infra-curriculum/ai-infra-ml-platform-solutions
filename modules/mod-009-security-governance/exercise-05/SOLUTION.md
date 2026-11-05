# SOLUTION — Exercise 05: Quarterly Compliance Audit

> Per-exercise solution. The module-level rationale lives in
> [`../SOLUTION.md`](../SOLUTION.md) §Ex-05; this file factors that
> section into a self-contained reference for graders and learners.
> Companion artifact in this directory: [`README.md`](./README.md)
> (quick-pointer: the per-team compliance script lives at
> [`../../mod-006-model-management/exercise-05/quarterly_audit.py`](../../mod-006-model-management/exercise-05/quarterly_audit.py)).
> The audit is the capstone: it reads outputs from Ex-01 (identity),
> Ex-02 (rotation evidence), Ex-03 (signing coverage), and Ex-04
> (gate decisions) to produce a single document.

## 1. Solution overview

The deliverable is **a quarterly compliance report that a regulator
can read without a tour guide**. It aggregates evidence from the
other four exercises along a fixed five-section outline — identity
hygiene, secrets hygiene, supply chain, governance gate,
access reviews — and names every non-compliant artifact by owner.

The reference solution commits to five design decisions:

1. **The report is a generated artifact, not a hand-written
   document.** A Markdown document that any team member could edit
   is a document no auditor will trust. The reference generates
   the report from code (`quarterly_audit.py` + its siblings) on a
   schedule the audit cadence runs against
   ([`../SOLUTION.md`](../SOLUTION.md) §Ex-05 — "a platform that
   can't produce it is a platform that's failing the compliance
   job").
2. **Every section cites a data source the earlier exercises
   produced.** Identity hygiene reads the OIDC provider; secrets
   hygiene reads Vault's audit device (from Ex-02); supply chain
   reads the registry's cosign+attestation records (from Ex-03);
   governance-gate stats come from `PolicyReport` + the Registry
   (from Ex-04). The report is a join over those tables; nothing
   is invented.
3. **Non-compliance is grouped by owning team.** A regulator wants
   "who is accountable for X"; the platform wants to route the
   remediation ask. Grouping by team is the enabling join.
4. **The cadence is quarterly, not annual.** Drift accumulates at
   the sprint level; annual audits miss everything that was
   non-compliant for eleven months of the twelve
   ([`../SOLUTION.md`](../SOLUTION.md) §Common mistakes #5).
5. **The report is append-only.** Last quarter's report is not
   overwritten; it is preserved so a reviewer can compare Q3 to
   Q4 and see whether non-compliance is trending up or down. "Drift"
   is only observable across reports.

A submission that produces a one-off report, or reads data sources
that the earlier exercises did not emit, is not solving the
exercise: the integration across exercises is the whole point.

## 2. Worked answer or implementation

The reference solution composes a report from five generators. The
Model-Registry generator is the one that already ships in the repo
([`../../mod-006-model-management/exercise-05/quarterly_audit.py`](../../mod-006-model-management/exercise-05/quarterly_audit.py));
the other four generators are described below with the same shape
so a submission can assemble the complete report.

### 2.1 The model-registry generator (reused)

```python
"""Quarterly compliance audit: every Production model checked for required artifacts."""
from mlflow.tracking import MlflowClient
from datetime import UTC, datetime, timedelta
from collections import defaultdict

REQUIRED_TAGS = ["model_card_uri", "bias_review_uri"]
STALENESS_DAYS = 90

def main():
    c = MlflowClient()
    models = c.search_registered_models()
    by_team: dict[str, list] = defaultdict(list)
    now = datetime.now(UTC)

    for m in models:
        prod = c.get_latest_versions(m.name, stages=["Production"])
        if not prod: continue
        v = prod[0]
        team = v.tags.get("team", "unknown")
        issues = []
        for t in REQUIRED_TAGS:
            if t not in v.tags: issues.append(f"missing {t}")
        if "model_card_updated_at" in v.tags:
            updated = datetime.fromisoformat(v.tags["model_card_updated_at"])
            if (now - updated) > timedelta(days=STALENESS_DAYS):
                issues.append(f"model_card stale (>{STALENESS_DAYS}d)")
        else:
            issues.append("model_card_updated_at unset")
        by_team[team].append({"model": m.name, "version": v.version, "issues": issues})

    print(f"# Quarterly Compliance Report — {now.date()}\n")
    for team, rows in sorted(by_team.items()):
        bad = [r for r in rows if r["issues"]]
        print(f"\n## Team `{team}` ({len(rows)} models, {len(bad)} non-compliant)\n")
        for r in bad:
            print(f"- {r['model']} v{r['version']}: {', '.join(r['issues'])}")
```

Why each line matters:

- **`get_latest_versions(..., stages=["Production"])`.** Only
  Production models are in scope. A model that never left
  Staging is a QA artifact, not a compliance one.
- **`team` defaulted to `"unknown"`.** The Ex-04 gate was supposed
  to prevent promotion without the tag, so `"unknown"` showing up
  is itself a compliance signal (the gate was bypassed or
  predates the gate).
- **Staleness check mirrors the Ex-04 gate.** Same threshold, same
  tag name. The audit cannot find a violation the gate did not
  also find — the audit is the post-hoc view of the gate.
- **Group-by-team output.** The report is structured for a
  routing step (file a remediation ticket per team) rather than a
  single global list that nobody owns.

### 2.2 Identity-hygiene generator (OIDC + RBAC)

Reads the OIDC provider's user and group APIs — the Ex-01 identity
source. Flags:

- **Dormant accounts.** A human account with `last_login_at`
  older than 60 days.
- **Service accounts without ownership tags.** Every service
  account must have `owner_team` in its claims; absence is a
  violation.
- **Over-privileged accounts.** Accounts in the `platform-admin`
  group whose job function does not require it; the baseline is
  "only staff SREs in `platform-admin`."
- **Rotation evidence.** Every service-account credential was
  rotated in the last quarter.

The shape of the generator:

```python
from collections import defaultdict
from datetime import datetime, timezone, timedelta

DORMANT_DAYS = 60
# oidc_client is the module from ../exercise-01 adapted for admin API.

def main(oidc_client, now=None):
    now = now or datetime.now(timezone.utc)
    by_team = defaultdict(list)

    for u in oidc_client.list_users():
        team = u.attrs.get("team", "unknown")
        issues = []
        if u.last_login_at and (now - u.last_login_at) > timedelta(days=DORMANT_DAYS):
            issues.append(f"dormant >{DORMANT_DAYS}d (last_login={u.last_login_at.date()})")
        if "platform-admin" in u.groups and not u.attrs.get("admin_justification"):
            issues.append("platform-admin without justification tag")
        if issues:
            by_team[team].append({"subject": u.email, "issues": issues})

    for sa in oidc_client.list_service_accounts():
        issues = []
        if "owner_team" not in sa.claims:
            issues.append("service-account missing owner_team claim")
        if sa.credential_rotated_at is None or \
           (now - sa.credential_rotated_at) > timedelta(days=90):
            issues.append("credential not rotated in last quarter")
        if issues:
            by_team[sa.claims.get("owner_team", "unknown")].append(
                {"subject": sa.name, "issues": issues})
    return by_team
```

Why these rules:

- **60-day dormancy.** Longer than one PTO window, shorter than
  one hiring cycle. A human that hasn't logged in for 60 days has
  either left or doesn't need the access.
- **`admin_justification`.** The `platform-admin` group is the
  blast-radius concern; requiring a text tag forces whoever
  granted admin to record *why*.
- **Service-account rotation in quarter.** Matches the §1 cadence.
  A service account whose credential has not rotated this quarter
  is not covered by the rotation discipline.

### 2.3 Secrets-hygiene generator (Vault)

Reads Vault's audit device (the file / socket enabled in
[`../exercise-02/SOLUTION.md`](../exercise-02/SOLUTION.md) §2.1)
and computes:

- **Rotation evidence** per static secret path. For every
  KV-v2 path tagged as a static secret, the latest version's
  `rotated_at` must be within the quarter.
- **Leaked-secret incident count.** Number of alerts fired by the
  secret-scanning pipeline (truffleHog / gitleaks) in the quarter
  that correspond to a Vault-managed path.
- **Un-rotated dynamic backends.** Backends whose `rotate-root`
  was not called this quarter.
- **TTL coverage.** Any secret role whose `max_ttl == 0`
  (unbounded) is a compliance violation.

Output lives under a `## Secrets hygiene` section grouped by team
in the same `team` field pattern as §2.1.

### 2.4 Supply-chain generator (Ex-03)

Reads the registry's attestation store (OCI referrers) and the
admission-time denial log from Ex-04. Computes:

- **Attestation coverage.** Percentage of images deployed to any
  platform namespace in the quarter that had a valid signature
  *and* a valid provenance attestation at admission time.
- **Unsigned-image attempt count.** `PolicyReport` denials with
  policy `require-attested-images` from Ex-04. Grouped by the
  namespace's `owner` label.
- **Stale base images.** Production-admitted images whose SBOM
  shows a base image older than 90 days. Baseline rule is
  informational, not a hard violation, but it feeds remediation.
- **CVE regressions.** Production images where the `grype` scan
  in CI flagged a High/Critical finding that was then waived.
  Waivers must have an expiry; expired waivers are violations.

### 2.5 Governance-gate generator (Ex-04)

Reads `PolicyReport` resources and the Registry's transition log.
Computes:

- **Violations attempted vs blocked.** Number of `fail` results
  in `PolicyReport` resources for the quarter. Partitioned by
  policy name so the team can see which rules are catching the
  most.
- **Policies in Audit mode past their bake.** Any
  `ClusterPolicy` with `validationFailureAction: Audit` whose age
  exceeds the agreed bake period from
  [`../exercise-04/SOLUTION.md`](../exercise-04/SOLUTION.md)
  §1.5. These are governance-debt entries, not Pod-level
  violations.
- **Promote-time gate bypass.** Any Production model version
  created in the quarter without the full §2.1 tag set. This
  should be zero if the gate is actually running on every promote;
  non-zero rows tell the regulator exactly where the promote path
  was bypassed.

### 2.6 Access-review generator

- **Access reviews completed in quarter.** Number of team-scoped
  access reviews signed off by team leads. Baseline is "one per
  team per quarter."
- **Pending reviews older than one cycle.** Unsigned reviews that
  have been open more than 90 days — this is the "nobody has
  actually reviewed access" failure mode.
- **Group membership delta.** Net additions to `platform-admin`
  and other elevated groups in the quarter, grouped by the
  granting identity.

### 2.7 Composition into the report

```python
# audit.py — composes the five generators into one report.
from datetime import datetime, timezone

SECTIONS = [
    ("Identity hygiene",     identity_hygiene.main),
    ("Secrets hygiene",      secrets_hygiene.main),
    ("Supply chain",         supply_chain.main),
    ("Governance gate",      governance_gate.main),
    ("Access reviews",       access_reviews.main),
    ("Model Registry",       mlflow_audit.main),   # from Ex-05/mod-006
]

def render():
    now = datetime.now(timezone.utc)
    print(f"# Quarterly Compliance Report — {now.date()}")
    print(f"\n*Reporting period: Q{(now.month-1)//3 + 1} {now.year}.*\n")
    for title, generator in SECTIONS:
        print(f"\n## {title}\n")
        rows = generator()                 # returns dict[team, list[dict]]
        for team in sorted(rows):
            issues = [r for r in rows[team] if r.get("issues")]
            if not issues: continue
            print(f"\n### Team `{team}` — {len(issues)} findings\n")
            for r in issues:
                subj = r.get("model") or r.get("subject") or r.get("name")
                print(f"- **{subj}**: {', '.join(r['issues'])}")
```

Three properties of this composition matter to the rubric:

- **A single invariant output format.** Every generator returns
  `dict[team, list[dict]]` with an `issues` key. The report
  layer is dumb concatenation; adding a new section is one
  function + one `SECTIONS` entry.
- **Deterministic ordering** via `sorted(rows)`. The same input
  produces the same bytes; `diff Q3.md Q4.md` is meaningful.
- **Section titles match the five-section outline** in
  [`../SOLUTION.md`](../SOLUTION.md) §Ex-05 exactly. The Registry
  section is an addition the module covers in mod-006.

### 2.8 Decision rationale

- **Why generate the report, not write it?** A hand-written
  report is a narrative; a generated report is evidence. A
  regulator wants evidence that remains evidence when the author
  is on vacation.
- **Why quarterly?** Quarterly matches most regulatory cadences
  (SOC 2 continuous-monitoring intervals, ISO 27001 management
  reviews), and quarterly is short enough that a drift between
  reports is still cheap to fix. Monthly is operational noise;
  annual is systemic drift.
- **Why five sections, not ten?** Each section corresponds to one
  exercise in this module. Adding sections that don't map to a
  control the platform actually operates produces aspirational
  compliance — a report whose content nobody can defend.
- **Why group by team?** Platforms have 10–40 teams; "20
  violations exist" is unactionable, "team-fraud has 4
  violations and team-rec has 1" is a remediation ticket.
- **Why append-only history?** The quarter-over-quarter delta is
  the signal; mutating history destroys the signal.

## 3. Validation steps

Each check names the exact command a grader runs against a
populated environment (OIDC provider, Vault, Registry, cluster).

1. **Script runs without error on a healthy environment.**
   `python audit.py > reports/$(date +%Y-%m-%d).md` produces a
   non-empty Markdown document and exits 0.
2. **Report contains all five sections, in the specified order.**
   `grep -E '^## ' reports/*.md` returns the six headings (five
   sections + Model Registry) in the order from §2.7.
3. **Report cites, not invents.** Every row traces to a real
   underlying record: for each line under "Model Registry," the
   named `model` + `version` is resolvable via
   `MlflowClient.get_model_version`; for each line under
   "Governance gate," the named `policy` + `subject` is in the
   `PolicyReport` the cluster emitted.
4. **Non-compliant artifacts show up.** Deliberately regress the
   environment (unset a `bias_review_uri` tag, let a service-
   account credential go unrotated for > 90 days, deploy a Pod
   without an `owner` label, etc.) and rerun. Every regression
   appears in the report under the team that owns it.
5. **No false positives on a clean environment.** Set every
   governance tag, rotate every credential, close every access
   review, and rerun. Every section header remains but its team
   subsections are empty. The report is not an empty file —
   "0 findings" is itself evidence.
6. **Report is reproducible.** Running the script twice on the
   same inputs produces byte-identical output (modulo the
   `generated_at` timestamp). `diff` on two runs shows no row
   churn.
7. **Historical comparison works.** Commit Q3's report; regenerate
   Q4's; `git diff reports/q3.md reports/q4.md` shows additions
   and removals cleanly because row ordering is deterministic.
8. **Running on a schedule produces an artifact nobody edits.**
   The CI cron job writes to `reports/<ISO-date>.md` on a
   branch that pushes without force; the file is read-only after
   write. `git log --follow reports/q3-2026.md` shows exactly one
   commit from the automation identity.
9. **Owner-team tag survives absence.** Teams-of-unknown are
   rendered under `unknown`; this bucket's non-zero row count is
   the signal that the Ex-04 gate's `team` tag requirement was
   bypassed somewhere.
10. **Auditor dry-run.** A reviewer reads the report with no
    other context and can point at every finding's raw source
    (Registry tag, Vault audit log line, PolicyReport, OIDC admin
    record). If a reviewer cannot locate the source, the report
    is fiction.

## 4. Rubric / review checklist

| Dimension | Pass criterion | Fail signal |
|---|---|---|
| Generated, not written | Report is produced by a script; the raw script is in the repo; running it reproduces the published report. | Markdown edited by hand; the repo has a `report.md` template with blanks. |
| Section coverage | Five sections from §1 outline, plus the Model-Registry section. | Any section missing; order shuffled. |
| Data sources tie to earlier exercises | Identity hygiene reads OIDC (Ex-01); Secrets reads Vault audit (Ex-02); Supply chain reads attestations (Ex-03); Governance gate reads PolicyReport + Registry (Ex-04); Registry reads MLflow (mod-006). | A section reads a data source that the exercises did not produce (e.g. the auditor's spreadsheet). |
| Owner-team grouping | Every finding is attributed to a team. Unknowns are called out explicitly. | Flat global list; no ownership. |
| Cadence | Script runs quarterly, scheduled, with evidence of prior runs. | One-off run on the grader's laptop. |
| Append-only history | Prior reports are preserved and diffable. | Prior quarter's report is overwritten. |
| Deterministic output | Byte-identical output on same inputs; ordering stable. | Row-order changes between runs with no input change. |
| Zero-finding render | A clean environment produces a non-empty report with empty team subsections. | Clean run produces an empty file or an error. |
| Regression surfaces | Every deliberately-induced violation appears in the expected section. | Regressions go undetected; a secret unrotated for 180 days doesn't appear. |
| Authorship | Report is written by the automation identity; no human commits to `reports/`. | PRs to `reports/` from humans; stray manual edits. |
| Traceability | Every row is traceable to the underlying record (Registry URL, audit log line, PolicyReport name). | Rows contain summaries with no back-reference. |

A passing submission scores Pass on every row. The two most common
near-misses are (a) implementing the Registry section only and
calling it a compliance report, and (b) generating the report but
letting humans edit it before publication.

## 5. Common mistakes

Inherited from the module-level list
([`../SOLUTION.md`](../SOLUTION.md) §Common mistakes graders see,
item 5) and narrowed to this exercise:

1. **Annual cadence.** Drift accumulates at the sprint level;
   annual audits miss every violation that was non-compliant for
   eleven months of the twelve. Quarterly is the minimum.
2. **Hand-written report.** A regulator trusts evidence, not
   prose. A document anyone could have edited is a document no
   one can defend.
3. **One section only.** Registry compliance is not "security and
   governance" — it is one surface out of five. Submissions that
   ship only `quarterly_audit.py` are incomplete.
4. **Data sources that don't trace.** A row that says
   "iris-rf non-compliant" with no back-reference to a Registry
   record is unfalsifiable; the reviewer cannot refute it, which
   means the reviewer cannot trust it either.
5. **No zero-finding render.** A clean quarter produces no file
   at all; the next quarter the team can't tell whether
   "no findings" means "everything's great" or "the script
   didn't run."
6. **Overwritten history.** Each quarter's report overwrites the
   last. Trends are invisible; drift is not observable.
7. **Humans editing the generated file.** Erodes the "generated"
   property. Authorship should be exclusively the automation
   identity.
8. **Compliance theater — rows copied from last quarter without
   re-generation.** If the Q4 report has the same rows as the Q3
   report, the remediation step did nothing; the audit catches
   this explicitly by using a deterministic generator.
9. **Unknown-team rows ignored.** The `unknown` bucket's non-zero
   count is the single most important signal in the report: it
   says the Ex-04 gate's `team` tag requirement was bypassed
   somewhere. Ignoring it is ignoring the primary bypass channel.
10. **Report that doesn't name the policy that caught the
    violation.** Rows need to carry the policy name so remediation
    can target the specific gate; "violation" without a policy
    name loops back to hand-written audits.

## 6. References

**Official sources**

- [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)
  — Govern 4 (accountability) and Manage 4 (continuous
  monitoring) directly scope the audit cadence and the five-section
  outline the report mirrors.
- [NIST AI 600-1 — Generative AI Profile](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf)
  — GAI-specific Measure and Manage actions add generation-time
  disclosure items (model card currency, provenance trail) that
  the Registry and governance-gate sections report on.
- [OWASP Machine Learning Security Top 10](https://owasp.org/www-project-machine-learning-security-top-10/)
  — the audit's Supply Chain section tracks ML06; the Governance
  Gate section tracks ML09 (output-integrity) controls in place.
- [MITRE ATLAS](https://atlas.mitre.org/) — the attack-technique
  taxonomy the Governance Gate and Supply Chain sections report
  coverage against; non-coverage is a gap the audit surfaces.
- [MLflow — Model Registry search API](https://mlflow.org/docs/latest/model-registry.html#model-registry-search).
  Authoritative for the `search_registered_models` +
  `get_latest_versions` calls the Registry generator uses.
- [HashiCorp Vault — Audit devices](https://developer.hashicorp.com/vault/docs/audit).
  Authoritative for the log format the Secrets-hygiene generator
  reads.
- [Kubernetes Policy WG — PolicyReport CRD](https://github.com/kubernetes-sigs/wg-policy-prs).
  Authoritative for the data source the Governance-gate generator
  consumes.

**Practitioner references**

- [VeriSwarm Trust Center](https://veriswarm.ai/trust) — example of
  a practitioner-run trust surface where a quarterly compliance
  report is the regulator-facing artifact. Use as an implementation
  exemplar, not an authoritative source.

**Local**

- Module rationale: [`../SOLUTION.md`](../SOLUTION.md) §Ex-05.
- Registry-section generator (reused):
  [`../../mod-006-model-management/exercise-05/quarterly_audit.py`](../../mod-006-model-management/exercise-05/quarterly_audit.py).
- Data sources the report joins:
  - Identity (Ex-01): [`../exercise-01/`](../exercise-01/).
  - Secrets (Ex-02): [`../exercise-02/SOLUTION.md`](../exercise-02/SOLUTION.md).
  - Supply chain (Ex-03): [`../exercise-03/SOLUTION.md`](../exercise-03/SOLUTION.md).
  - Governance gates (Ex-04): [`../exercise-04/SOLUTION.md`](../exercise-04/SOLUTION.md).
- Quick-pointer: [`README.md`](./README.md).
- Learning exercise prompt:
  `lessons/mod-009-security-governance/exercises/exercise-05-quarterly-compliance-audit.md`
  in the `ai-infra-ml-platform-learning` repo.
