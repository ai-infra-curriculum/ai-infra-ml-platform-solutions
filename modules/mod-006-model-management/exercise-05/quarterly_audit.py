"""Quarterly compliance audit: every Production model checked for required artifacts."""
from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from mlflow.tracking import MlflowClient


REQUIRED_TAGS = ["model_card_uri", "bias_review_uri"]
STALENESS_DAYS = 90


def main():
    c = MlflowClient()
    models = c.search_registered_models()
    by_team: dict[str, list] = defaultdict(list)
    now = datetime.now(UTC)

    for m in models:
        prod = c.get_latest_versions(m.name, stages=["Production"])
        if not prod:
            continue
        v = prod[0]
        team = v.tags.get("team", "unknown")

        issues = []
        for t in REQUIRED_TAGS:
            if t not in v.tags:
                issues.append(f"missing {t}")

        if "model_card_updated_at" in v.tags:
            updated = datetime.fromisoformat(v.tags["model_card_updated_at"])
            if (now - updated) > timedelta(days=STALENESS_DAYS):
                issues.append(f"model_card stale (>{STALENESS_DAYS}d)")
        else:
            issues.append("model_card_updated_at unset")

        by_team[team].append({
            "model": m.name, "version": v.version, "issues": issues,
        })

    print(f"# Quarterly Compliance Report — {now.date()}\n")
    for team, rows in sorted(by_team.items()):
        bad = [r for r in rows if r["issues"]]
        print(f"\n## Team `{team}` ({len(rows)} models, {len(bad)} non-compliant)\n")
        for r in bad:
            print(f"- {r['model']} v{r['version']}: {', '.join(r['issues'])}")


if __name__ == "__main__":
    main()
