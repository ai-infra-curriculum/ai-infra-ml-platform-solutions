# SOLUTION — Module 07: Developer Experience

> Read after the per-exercise solutions. Cross-exercise rationale.

## What the module is really teaching

Platform teams ship products to internal developers. If your
internal developers prefer to roll their own infrastructure
rather than use yours, **the platform has failed**, regardless of
how sophisticated the implementation is.

The five exercises are shaped around the four DX failures that
make platforms fail their adoption test:

1. **The platform team doesn't know what consumers actually
   need** (customer interviews).
2. **The platform's CLI is harder to use than `kubectl`** (CLI
   ergonomics).
3. **There's no tutorial that gets a new user to a working state
   in 10 minutes** (onboarding friction).
4. **Error messages are useless** (recovery cost).

## Exercise-by-exercise rationale

### Ex-01 — Customer interviews

The reference solution is the **interview discipline**, not the
interviews. Sections:

- Who to interview: a stratified sample across tiers + tenure.
- What to ask: open-ended ("describe your last week"), never
  closed ("how do you like the new API?").
- What to look for: the things they did *not* mention that you
  expected them to. The platform feature they bypassed silently.
- How to act: every recurring complaint becomes a roadmap item;
  every "I'm doing X because the platform doesn't do Y" is a
  product opportunity.

The unstated point: platform teams under-interview. Most of them
build from assumptions about what users want. The teams that
ship adopted platforms interview every quarter.

### Ex-02 — Build a CLI

The reference CLI:

- Uses `click` (or `typer`) — not argparse + manual parsing.
- Has a top-level help string a new user can read in 30 seconds.
- Every subcommand has examples.
- Error messages tell the user **what to do next**, not just
  what went wrong.
- The CLI uses the same SDK from `mod-002/ex-04`. Dogfood is the
  test.

### Ex-03 — Tutorial write-up

The reference tutorial:

- Starts from "you have nothing installed."
- Ends with "your first ML job completed."
- Takes 10 minutes for a competent engineer.
- Has *every* command shown verbatim, no "do the obvious thing"
  steps.
- The author runs it on a fresh laptop before considering it
  done.

The 10-minute test is a hard constraint. Tutorials that take
30 minutes get abandoned at minute 20.

### Ex-04 — Error message audit

The deliverable: a CSV of every error message the platform's
CLI + API can produce, scored on:

- **Specificity**: does it tell the user *what* failed?
- **Actionability**: does it tell the user *what to do*?
- **Stability**: does it have a stable error code?

The reference audit found ~40% of error messages failed at least
one of the three. Every error that fails gets a follow-up issue.
Error message quality is the highest-leverage DX investment per
LOC.

### Ex-05 — NPS survey design

The reference survey:

- One question (NPS-classic): "how likely are you to recommend
  this platform to a colleague?"
- One open-ended follow-up: "what's the one thing we should
  change?"
- Sampled quarterly across the population.
- The result is a tracked metric on the platform team's roadmap
  doc.

DX is measurable. NPS is the canonical instrument because it
correlates with churn and recovery cost. Surveys that ask 30
questions get 5% response rates; one-question surveys get 60%.

## Cross-exercise design decisions

- **Dogfood**: the platform team's tools use the same SDK they
  ship.
- **Tutorial-as-test**: a tutorial isn't done until it passes
  fresh-laptop.
- **Error messages are product**, not implementation detail.
- **DX is measured**, not asserted.

## Common mistakes graders see

1. **Interviews with leading questions**. "How does the platform
   help you?" surfaces nothing.
2. **CLI that requires reading documentation to use**. If `--help`
   isn't enough for the basics, the design is wrong.
3. **Tutorials that skip steps**. "Set up your environment as in
   the README" is the killer line.
4. **Generic error messages** (`internal error`, `bad request`).
   No recovery information.
5. **No DX measurement**. The team can't tell if it's improving.

## Related curriculum touchpoints

- `ml-platform/mod-002/ex-04` — the SDK the CLI is built on.
- `engineer/mod-110/ex-01` — OpenAI-compatible API is itself a
  DX bet.
- `architect/project-301` — DX at enterprise scale.
- `team-lead/mod-704` — coordinating with downstream teams
  (the DX consumers).
