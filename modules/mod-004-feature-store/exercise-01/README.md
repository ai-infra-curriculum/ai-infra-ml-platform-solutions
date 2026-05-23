# Feast Quickstart — Solution

```bash
pip install "feast[duckdb,redis]"
feast apply
python -c "from datetime import datetime, timedelta; from feast import FeatureStore; fs=FeatureStore('.'); fs.materialize(datetime.now()-timedelta(days=7), datetime.now())"
```

Companion: engineer-solutions/mod-106 ex-07 for full materialization + PIT join + online serve.
