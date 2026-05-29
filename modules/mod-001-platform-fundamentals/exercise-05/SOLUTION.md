# SOLUTION — Exercise 05: Case Study Analysis — Michelangelo vs Metaflow

Reference for [learning ex-05](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/lessons/mod-001-platform-fundamentals/exercises/exercise-05-case-study-analysis-michelangelo-metaflow.md).

See also the module-level rationale in [`../SOLUTION.md`](../SOLUTION.md) and the
condensed pros/cons table in [`CASE_STUDY.md`](CASE_STUDY.md).

## 1. Solution overview

The capstone of mod-001 is **not building anything**; it is reading the two
canonical platform-design references — Uber's Michelangelo and Netflix's
Metaflow — and producing a structured written analysis. The deliverable is a
short comparative writeup that follows a fixed four-question template, plus a
"lessons for a platform team" section.

The discipline this exercise teaches: **reading other people's platforms is
the single highest-leverage activity** an ML platform engineer does. Junior
platform engineers consistently under-read; the rubric below is calibrated to
catch that.

## 2. Implementation (worked answer)

The "implementation" of this exercise is producing the written analysis itself.
Follow the four-question template, fill in each subsection below for both
platforms, then close with the cross-cutting lessons. The structure that
follows is the worked reference answer learners' submissions are compared
against.

### Analysis template

Every case-study writeup in this module follows the same four questions
(see [`../SOLUTION.md`](../SOLUTION.md) §Ex-05):

1. What problem did the team solve?
2. What technical decisions did they make?
3. Which decisions would *not* survive a re-derivation today?
4. What did they get wrong, and how did they recover?

### Michelangelo (Uber)

**Pros**

- Unified feature store + training + serving in one platform.
- Strong UX for non-ML engineers — ride-pricing, ETA, and fraud teams ship
  models without owning the ML stack.
- Multi-tenant by design from day one.

**Cons**

- Heavy proprietary stack; not portable outside Uber's infra.
- Vertical platform: opinionated to Uber's data shape and request volume; a
  smaller org adopting the same shape would be over-engineered on day one.

### Metaflow (Netflix)

**Pros**

- DS-friendly decorator API (`@step`, `@batch`) that fits how data scientists
  already write Python.
- Native experiment versioning and reproducibility — every run gets a unique
  ID with frozen dependencies.
- Cleaner ops story than notebook-driven workflows: the same code runs on a
  laptop and on the cluster.

**Cons**

- Smaller community than Airflow for the orchestrator surface.
- "Last mile" production ops — model serving, online inference — requires
  Outerbounds or homegrown additions; Metaflow itself stops at the training
  pipeline.

### Lessons for a platform team

- **DS UX > platform purity.** Data scientists adopt platforms with familiar
  APIs (decorators, Pythonic). A cleaner internal model that doesn't fit the
  user's editor loses.
- **Multi-tenancy is required from day one.** Retrofitting it onto
  Michelangelo would have been ugly; Metaflow's later landing-zone work
  illustrates the same lesson from the opposite direction.
- **Reproducibility wins arguments.** Every Metaflow run has a unique ID and
  frozen deps, which collapses most "it worked on my machine" debates.
- **Choose vertical or horizontal early.** Vertical platforms (Michelangelo)
  optimize one company's workflow; horizontal platforms (Metaflow) generalize
  across orgs. Trying to be both is the failure mode.

## 3. Validation steps

A learner's submission is valid if all of the following hold:

1. It addresses **both** platforms — single-platform writeups do not satisfy
   the exercise.
2. It uses the four-question template above, or covers the same four
   questions under different headings.
3. The "what they got wrong" / critique section is present and **specific**
   — not a generic disclaimer.
4. Claims about the two platforms are tied to a public source (Uber
   Engineering blog, Netflix Tech Blog, Metaflow docs, conference talks).
   Unsourced metrics or incidents are rejected.
5. The writeup ends with at least one explicit takeaway the learner would
   apply to their own platform design.

## 4. Rubric / review checklist

| Dimension | Pass | Fail |
|---|---|---|
| Coverage | Both Michelangelo and Metaflow analyzed | Only one platform |
| Template adherence | All four questions answered | Skips the critique question |
| Specificity | Names concrete features (feature store, `@step`, run IDs, multi-tenant scheduler) | Vague "good DX, good ops" prose |
| Critical reading | Identifies at least one decision that would not survive re-derivation today | No critique, or only restates the marketing claims |
| Sourcing | Every non-trivial claim links to a public reference | Unsourced numbers, invented incidents |
| Transfer | Concludes with platform-design lessons the learner will apply | No "so what" section |

A submission must pass every row to be considered complete.

## 5. Common mistakes

Graders see these repeatedly (see [`../SOLUTION.md`](../SOLUTION.md)
§Common mistakes graders see, item 5):

1. **No critique section.** Reading uncritically is reading badly. A writeup
   that only restates each platform's published strengths does not satisfy
   the exercise.
2. **Treating the two platforms as interchangeable.** Michelangelo is a
   vertical, end-to-end stack; Metaflow is a horizontal pipeline framework
   that stops short of serving. Comparing them on the same axis without
   noting that shape difference misses the point.
3. **Citing only the original launch blog posts.** Both platforms have
   evolved; a writeup grounded only in the 2017 Michelangelo post or the
   2019 Metaflow post will miss everything that happened after.
4. **Inventing metrics.** Specific latency, throughput, or adoption numbers
   that aren't in a public source should not appear. If the number is
   needed but not yet sourced, flag it with an explicit TODO citation
   placeholder rather than guessing.
5. **No "lessons for a platform team" section.** The exercise is a learning
   instrument; without the transfer step it is just a book report.

## 6. References

**Local**

- Module-level rationale: [`../SOLUTION.md`](../SOLUTION.md) §Ex-05.
- Condensed pros/cons table: [`CASE_STUDY.md`](CASE_STUDY.md).
- Learning lesson:
  `lessons/mod-001-platform-fundamentals/exercises/exercise-05-case-study-analysis-michelangelo-metaflow.md`
  in the `ai-infra-ml-platform-learning` repo.

**External primary sources to cite in the writeup**

Graders expect each non-trivial claim to be tied to one of these source
families. Learners are responsible for locating and citing the specific
post or page they relied on; URLs change, so the writeup should link to
the exact resource read at the time of submission.

- Uber Engineering blog posts on Michelangelo (architecture, feature store,
  PyML, serving).
- Netflix Tech Blog and Outerbounds documentation on Metaflow (decorator
  API, run IDs, `@batch`, deployment).
- Metaflow project documentation at the project's official site.
