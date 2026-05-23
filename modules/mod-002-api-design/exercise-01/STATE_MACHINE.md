# Training Job State Machine

```
                ┌────────┐
        ────────▶ pending │
                └───┬────┘
                    │ scheduler assigns to a node
                    ▼
              ┌─────────┐
              │scheduled│
              └─────┬───┘
                    │ container starts
                    ▼
              ┌────────┐
              │running │ ◀── (extend allowed)
              └───┬────┘
       ┌──────┬──┴──┬──────┐
       │      │     │      │
       ▼      ▼     ▼      ▼
  succeeded failed cancelled (lifetime expired → failed)
```

Cancel allowed in: pending, scheduled, running.
Retry allowed in: failed, cancelled (creates new job with same spec).
