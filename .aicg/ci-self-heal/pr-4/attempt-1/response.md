The two file edits are applied locally; the sandbox is refusing the git commit invocations. Working-tree state:

- `modules/mod-005-workflow-orchestration/exercise-01/DECISION.md`: line 4–6 rewrap so `+ cron` no longer starts at column 1.
- `modules/mod-007-developer-experience/SOLUTION.md`: line 72–73 rewrap so `+ API` no longer starts at column 1.

Both changes are minimal and address the MD004 failures. Please approve the commit (or run `git commit -am "fix(docs): avoid line-leading '+'…"` yourself) — I'm unable to land it from here.
