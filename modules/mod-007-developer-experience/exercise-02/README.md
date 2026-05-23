# CLI — Solution

`cli.py` is a Click-based CLI with:
- Subcommands: `ml jobs submit | list | status`
- `--output json|yaml|table` everywhere
- 4-part structured error messages (Error / Cause / Help / Docs)
- Auth from env vars

```bash
pip install click httpx pyyaml
python cli.py jobs submit --config job.yaml
python cli.py jobs list --status failed --output yaml
```
