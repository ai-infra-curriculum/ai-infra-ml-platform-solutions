# Rollback Procedure — Solution

`rollback.py` finds the most recent prior Production version + transitions
both atomically. Test by promoting v5 → Production, then v6 → Production,
then run `python rollback.py iris-rf` — back to v5.
