# Address CI failures on PR #4

## Goal

The PR you just opened failed CI. Fix the failures listed
below by editing files on the current branch. Do NOT regenerate
the content from scratch — make the minimal edit needed to
satisfy each failing check.

## Failed checks

### 1. `Markdown lint` (failure)

- Details: <https://github.com/ai-infra-curriculum/ai-infra-ml-platform-solutions/actions/runs/26557957199/job/78233823855>
- Annotations:
  - `.github:2` (warning): Node.js 20 actions are deprecated. The following actions are running on Node.js 20 and may not work as expected: actions/checkout@v4, DavidAnson/markdownlint-cli2-action@v16. Actions will be forced to run with Node.js 24 by default starting June 2nd, 2026. Node.js 20 will be removed from the runner 
  - `.github:19` (failure): Failed with exit code: 1
  - `modules/mod-007-developer-experience/SOLUTION.md:73` (failure): modules/mod-007-developer-experience/SOLUTION.md:73:1 MD004/ul-style Unordered list style [Expected: dash; Actual: plus] https://github.com/DavidAnson/markdownlint/blob/v0.34.0/doc/md004.md
  - `modules/mod-005-workflow-orchestration/exercise-01/DECISION.md:29` (failure): modules/mod-005-workflow-orchestration/exercise-01/DECISION.md:29:1 MD004/ul-style Unordered list style [Expected: plus; Actual: dash] https://github.com/DavidAnson/markdownlint/blob/v0.34.0/doc/md004.md
  - `modules/mod-005-workflow-orchestration/exercise-01/DECISION.md:28` (failure): modules/mod-005-workflow-orchestration/exercise-01/DECISION.md:28:1 MD004/ul-style Unordered list style [Expected: plus; Actual: dash] https://github.com/DavidAnson/markdownlint/blob/v0.34.0/doc/md004.md
  - `modules/mod-005-workflow-orchestration/exercise-01/DECISION.md:27` (failure): modules/mod-005-workflow-orchestration/exercise-01/DECISION.md:27:1 MD004/ul-style Unordered list style [Expected: plus; Actual: dash] https://github.com/DavidAnson/markdownlint/blob/v0.34.0/doc/md004.md

## Output contract

- Edit ONLY files inside this repo on the current branch.
- Preserve the existing structure; do not delete sections.
- Do NOT touch CURRICULUM.md, README.md, or VERSIONS.md.
- One atomic commit covering all fixes is fine.
