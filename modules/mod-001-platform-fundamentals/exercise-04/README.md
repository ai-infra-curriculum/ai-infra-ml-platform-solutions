# Plugin System — Solution

Reference for [learning ex-04](https://github.com/ai-infra-curriculum/ai-infra-ml-platform-learning/blob/main/lessons/mod-001-platform-fundamentals/exercises/exercise-04-build-a-simple-plugin-system.md).

Demonstrates Python entry-points as a plugin discovery mechanism:
- Core defines `StoragePlugin` Protocol
- Plugins are separate packages declaring `entry_points = {"ml_platform.storage": ["s3 = my_s3_plugin:S3Storage"]}`
- Core loads via `importlib.metadata.entry_points(group="ml_platform.storage")`

A LocalFSStorage example ships in `plugins.py`. To add S3 / GCS / Azure, ship them as separate pip packages with an entry point.
