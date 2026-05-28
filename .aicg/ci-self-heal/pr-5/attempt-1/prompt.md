# Address CI failures on PR #5

## Goal

The PR you just opened failed CI. Fix the failures listed
below by editing files on the current branch. Do NOT regenerate
the content from scratch — make the minimal edit needed to
satisfy each failing check.

## Failed checks

### 1. `Markdown lint` (failure)

- Details: <https://github.com/ai-infra-curriculum/ai-infra-ml-platform-solutions/actions/runs/26588476325/job/78340748214>
- Annotations:
  - `.github:2` (warning): Node.js 20 actions are deprecated. The following actions are running on Node.js 20 and may not work as expected: actions/checkout@v4, DavidAnson/markdownlint-cli2-action@v16. Actions will be forced to run with Node.js 24 by default starting June 2nd, 2026. Node.js 20 will be removed from the runner 
  - `.github:17` (failure): Failed with exit code: 1
  - `projects/project-01-platform-core/rubric.md:18` (failure): projects/project-01-platform-core/rubric.md:18:75 MD056/table-column-count Table column count [Expected: 3; Actual: 6; Too many cells, extra data will be missing] https://github.com/DavidAnson/markdownlint/blob/v0.34.0/doc/md056.md
  - `projects/project-01-platform-core/rubric.md:18` (failure): projects/project-01-platform-core/rubric.md:18:99 MD038/no-space-in-code Spaces inside code span elements [Context: "...h authenticate with a token; `"] https://github.com/DavidAnson/markdownlint/blob/v0.34.0/doc/md038.md

## Output contract

- Edit ONLY files inside this repo on the current branch.
- Preserve the existing structure; do not delete sections.
- Do NOT touch CURRICULUM.md, README.md, or VERSIONS.md.
- One atomic commit covering all fixes is fine.
