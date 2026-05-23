# Quarterly NPS Survey — Plan

## Audience
All users who have submitted at least one training job in the last 30 days
(filter spam). ~150 users at our scale.

## Questions (5 max)

1. **NPS**: "How likely are you to recommend the ML Platform to a peer engineer? (0-10)"
2. **Lead time**: "From decision to train → in production, how long does it take you on average? (< 1 day / 1-3 days / 1-2 weeks / longer)"
3. **Self-serve**: "What % of your platform interactions require help from the platform team? (0 / 1-25 / 26-50 / 50+)"
4. **Top blocker**: "If you could fix one thing in the platform next quarter, what?" (free text)
5. **Single best**: "What part of the platform works best for you?" (free text)

## Distribution
- Email + Slack DM
- 1 reminder after 1 week
- Closes after 2 weeks
- Anonymous results; team-level aggregation only

## How we use it

| Result | Action |
|---|---|
| NPS < 0 | Postmortem; org-level discussion |
| NPS 0-30 | Quarterly retro: top 3 themes from blockers feed roadmap |
| NPS 30+ | Showcase: what users like; double down |
| Lead time trending up | Investigate; root-cause as incident |
| Self-serve % declining | Office hours topic + new tutorial |

## What we don't do
- Punish low scores publicly
- Tie individual responses to identities
- Treat NPS as the only success metric (paired with lead time + self-serve)
