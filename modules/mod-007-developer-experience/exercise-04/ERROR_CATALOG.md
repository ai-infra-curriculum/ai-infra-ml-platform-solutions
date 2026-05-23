# Error Message Audit — Reference

## Catalog

| Trigger | Current message | Replacement (4-part) | Fix location |
|---|---|---|---|
| Submit with invalid GPU type | `400` | `Error: failed to submit / Cause: gpu_type 'foo' not in [t4,a10,l4,l40s,a100,h100] / Help: see allowed types in docs / Docs: ...` | server |
| Submit over quota | `429` | `Error: failed to submit / Cause: tenant quota exceeded (16/16 GPUs used) / Help: wait for jobs to complete or request quota increase / Docs: ...` | server |
| Get non-existent job | `404` | `Error: get status / Cause: job <id> not found / Help: check job id; you may not have permission for this tenant / Docs: ...` | CLI |
| Network timeout | unhandled traceback | `Error: connect to platform / Cause: connection timed out / Help: check VPN / API endpoint; status page: ... / Docs: ...` | SDK |
| Invalid API key | `401` | `Error: authenticate / Cause: invalid or expired API key / Help: rotate via 'ml auth rotate' / Docs: ...` | SDK |
| Cancel completed job | `409` | `Error: cancel / Cause: job is in status 'succeeded' (terminal) / Help: cancelling only allowed while pending or running / Docs: ...` | server |
| YAML parse error | `yaml.YAMLError` | `Error: parse spec / Cause: invalid YAML at line N / Help: validate with 'yamllint' / Docs: ...` | CLI |
| Missing required field | `422` | `Error: submit / Cause: field 'model_uri' is required / Help: add to your spec; see example / Docs: ...` | server |
| Pod scheduling timeout | `Pending forever` | (server emits event) `Error: schedule / Cause: 0 GPUs available in your namespace's pool / Help: wait or escalate / Docs: ...` | server |
| Model image pull failure | `ImagePullBackOff` | `Error: start training / Cause: image 'ghcr.io/...' not found or unauthorized / Help: check tag + registry credentials / Docs: ...` | server |

All 10 improved + the surrounding context (logging, structured error
responses) hardened.
