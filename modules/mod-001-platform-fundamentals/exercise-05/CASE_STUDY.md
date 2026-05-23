# Case Study Analysis: Michelangelo + Metaflow — Solution

Reference for [learning ex-05](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/lessons/mod-001-platform-fundamentals/exercises/exercise-05-case-study-analysis-michelangelo-metaflow.md).

## Michelangelo (Uber)
**Pros**
- Unified feature store + training + serving
- Strong UX for non-ML engineers
- Multi-tenant by design

**Cons**
- Heavy proprietary stack; not portable
- Vertical platform: opinionated to Uber's data shape

## Metaflow (Netflix)
**Pros**
- DS-friendly decorator API (`@step`, `@batch`)
- Native experiment versioning + reproducibility
- Cleaner ops story than notebook-driven workflows

**Cons**
- Smaller community than Airflow
- "Last mile" production ops requires Outerbounds or homegrown additions

## Lessons for a platform team
- **DS UX > platform purity**: data scientists adopt platforms with familiar APIs (decorators, Pythonic)
- **Multi-tenancy is required from day one** — Michelangelo retrofit would have been ugly
- **Reproducibility wins arguments** — every Metaflow run has a unique ID + frozen deps
- **Choose vertical or horizontal early** — vertical platforms (Michelangelo) optimize one company's workflow; horizontal (Metaflow) generalize across orgs
