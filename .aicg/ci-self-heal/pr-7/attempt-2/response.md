No file edits applied.

The attempt-2 prompt's "Failed checks" section is empty — `fetch_failed_checks`
returned no entries, so there is no specific annotation to address. Per the
prompt builder's own fallback guidance ("if you cannot tell what's wrong …
exit without editing rather than guessing"), making speculative edits is the
wrong move.

Static verification of the previously-failing surface (MD004 / ul-style):

- `projects/project-03-workflow-orchestration/STEP_BY_STEP.md` contains zero
  lines starting with `- ` after attempt-1; all unordered-list lines start
  with `+`. The file's first list marker (line 42, the `+ [...]` paragraph
  continuation that markdownlint parses as a list start) is `+`, and every
  subsequent list item matches.
- No other markdown file under `projects/**` or `modules/**` uses `+` or `*`
  list markers — they're all `-` and internally consistent, so MD004's
  consistent-style rule passes for each file.
- No nested list markers (`^\s+[-+*] `) exist anywhere, so there's no hidden
  nested-list inconsistency.

Python-syntax and autograder CI jobs only scan `modules/**/*.py` and
`modules/**/exercises/*/check.py` respectively; this PR's Python changes are
under `projects/`, so those checks are not the cause either.

Most likely cause of the empty failed-checks list: a transient GH check-runs
API miss between `wait_for_ci` (which saw a non-success rollup) and
`fetch_failed_checks` (which couldn't enumerate the failing run). A re-run
of CI should resolve it; if it doesn't, the next attempt's prompt should
carry the real annotations.
