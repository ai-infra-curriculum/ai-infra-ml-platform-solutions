# Train Your First Model on the Platform

## Goal
By the end of this 15-minute tutorial, you'll have a trained model running on
the platform with a versioned record in the registry.

## Prereqs
- Platform CLI installed: `pip install ml-platform-cli`
- API key + tenant: `export ML_PLATFORM_API_KEY=...; export ML_PLATFORM_TENANT=acme`

## 1. Define your training job (1 min)

```yaml
# my-first-job.yaml
model_uri: ghcr.io/me/iris-trainer:0.1
dataset_uri: s3://ml-public-datasets/iris/
gpu_count: 1
hyperparams: { n_estimators: 200, max_depth: 12 }
```

## 2. Submit (10 seconds)

```bash
ml jobs submit --config my-first-job.yaml
# → returns: id=abc123  status=pending
```

## 3. Watch it run (5-10 min for a trivial model)

```bash
ml jobs status abc123 --output json | jq .status
# → "running" → "succeeded"
```

When it's done, the model is automatically registered.

## 4. Find it in the registry

```bash
ml models list --owner $ML_PLATFORM_TENANT
# → iris-rf v1  Staging
```

## 5. Promote to Production

```bash
ml models promote iris-rf --version 1 --to production
```

## What just happened

- Your job ran on a platform-managed GPU pod (no Kubernetes knowledge needed).
- Metrics were logged to MLflow (browse them at the UI).
- The trained model was registered + tagged with your job ID for traceability.
- The promotion to Production triggered the deployment pipeline.

## Next steps

- [Add monitoring](https://docs.example.com/monitoring)
- [Set up A/B testing](https://docs.example.com/ab-testing)
- [Add custom metrics to your training](https://docs.example.com/custom-metrics)

## Got stuck?

Post in `#ml-platform-help` with: your job id, what you expected, what you saw.
Office hours every Thursday 14:00 UTC.
