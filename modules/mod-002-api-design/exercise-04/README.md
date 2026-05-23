# Python SDK — Solution

Reference for [learning ex-04](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/lessons/mod-002-api-design/exercises/exercise-04-build-python-sdk.md).

```python
from sdk import Client
c = Client()
job = c.jobs.submit_and_wait({"model_uri": "...", "dataset_uri": "..."},
                              on_status=print)
for j in c.jobs.list(status="failed"):    # transparent pagination
    print(j["id"])
```

Adds to the generated client: retry+backoff, pagination iterator, idempotency
key auto-gen, typed exceptions, `submit_and_wait` helper, auth from env.
