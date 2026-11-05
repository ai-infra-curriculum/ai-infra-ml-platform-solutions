# SOLUTION — Exercise 04: Streaming Feature

> Per-exercise solution. The cross-exercise rationale lives in
> [`../SOLUTION.md`](../SOLUTION.md); this file factors the Ex-04
> section into a self-contained reference for graders.

## 1. Solution overview

Ex-04 teaches the discipline that keeps a **streaming feature**
— a value whose definition includes "right now", such as
"transactions in the last 5 minutes for this user" — consistent
between what serving reads and what training sees.

A streaming feature cannot be produced by a nightly batch
materialization: by the time the batch finishes, the "last 5
minutes" is 24 hours stale. It cannot be produced by serving-time
computation either: pulling raw transactions from the source of
truth and aggregating per request pushes point-lookup latency and
load back onto the transactional system the feature store was
built to shield.

The reference solution has three moving parts:

1. **A stream aggregator.** A PyFlink job consumes a Kafka
   topic, keys by `user_id`, maintains a 5-minute tumbling
   window aggregate, and writes each window result to Redis
   (the online store from
   [`../exercise-01/feature_store.yaml`](../exercise-01/feature_store.yaml)).
2. **A nightly offline reconciliation.** A batch job computes
   the same 5-minute aggregate over the previous day's
   transactions from the offline store and writes it to the
   feature view's offline source, so training sets built by
   [`../exercise-02/SOLUTION.md`](../exercise-02/SOLUTION.md)-style
   point-in-time joins observe the same values serving did.
3. **A reconciliation diff.** A small job that, for a sample of
   `(user_id, window_end)` keys, compares the stream-produced
   value against the batch-produced value and alerts when the
   drift exceeds a declared tolerance.

Part 3 is the discipline the module calls out in
[`../SOLUTION.md`](../SOLUTION.md) §Ex-04: *streaming features
ship the train-serve skew bug back to the front of the queue; the
aggregator + nightly reconciliation is what prevents it.*

## 2. Worked implementation

### 2.1 Feature definition

The streaming feature joins the existing repo at
[`../exercise-01/`](../exercise-01/). A new `FeatureView` is
added over a batch source whose rows are the
reconciled-per-window aggregates:

```python
# exercise-01/features.py (addition)
from datetime import timedelta
from feast import FeatureView, Field, FileSource
from feast.types import Int64

txns_src = FileSource(
    name="txns_5min_src",
    path="data/txns_5min.parquet",
    timestamp_field="window_end",
)

user_txns_5min = FeatureView(
    name="user_txns_5min",
    entities=[user],              # defined in exercise-01/features.py
    ttl=timedelta(minutes=10),    # 2 windows; miss after ~10 min
    schema=[Field(name="txns_5min", dtype=Int64)],
    source=txns_src,
    online=True,
)
```

Two deliberate choices, both grading signals:

- **`ttl=timedelta(minutes=10)`** — exactly two windows. A
  single-window TTL would misclassify an in-flight window as
  fresh; a many-window TTL would let stale values satisfy
  online reads.
- **`timestamp_field="window_end"`** — the aggregate's timestamp
  is the end of the window it summarizes, not the aggregation
  time. Setting it to anything else breaks point-in-time joins
  in training.

### 2.2 Stream aggregator (PyFlink)

The online path. Reads the Kafka topic of transactions, keys by
`user_id`, maintains a 5-minute tumbling event-time window, and
emits `(user_id, window_end, txns_5min)` to Redis — the same
online store configured in
[`../exercise-01/feature_store.yaml`](../exercise-01/feature_store.yaml).

```python
# streaming/flink_features.py
from pyflink.common import Types, WatermarkStrategy, Duration
from pyflink.common.serialization import SimpleStringSchema
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import KafkaSource, KafkaOffsetsInitializer
from pyflink.datastream.window import TumblingEventTimeWindows
from pyflink.common.time import Time
import json, redis

env = StreamExecutionEnvironment.get_execution_environment()
env.enable_checkpointing(60_000)                    # exactly-once state, 60s
env.set_parallelism(4)

kafka = (KafkaSource.builder()
         .set_bootstrap_servers("kafka:9092")
         .set_topics("transactions")
         .set_group_id("feast-txns-5min")
         .set_starting_offsets(KafkaOffsetsInitializer.earliest())
         .set_value_only_deserializer(SimpleStringSchema())
         .build())

watermarks = (WatermarkStrategy
              .for_bounded_out_of_orderness(Duration.of_seconds(30))
              .with_timestamp_assigner(
                  lambda event, _ts: json.loads(event)["event_ts_ms"]))

def parse(raw):
    r = json.loads(raw)
    return (r["user_id"], 1)      # (key, count contribution)

def sink(rows):
    # rows: Iterable[(user_id, count, window_end_ms)]
    r = redis.Redis(host="redis", port=6379)
    pipe = r.pipeline()
    for user_id, count, window_end_ms in rows:
        pipe.set(f"user_txns_5min:{user_id}", count, ex=600)  # TTL matches FeatureView
    pipe.execute()

(env
 .from_source(kafka, watermarks, "transactions")
 .map(parse, output_type=Types.TUPLE([Types.STRING(), Types.INT()]))
 .key_by(lambda kv: kv[0])
 .window(TumblingEventTimeWindows.of(Time.minutes(5)))
 .reduce(lambda a, b: (a[0], a[1] + b[1]),
         window_function=lambda key, window, inputs, out:
             out.collect((key, sum(i[1] for i in inputs), window.end)))
 .add_sink(sink))

env.execute("txns_5min")
```

Grading signals in this snippet:

- **Event-time windows with a bounded-out-of-orderness
  watermark**, not processing-time windows. Processing-time
  windows produce silently-wrong aggregates whenever consumer
  lag spikes.
- **Checkpointing enabled.** The window state is in Flink;
  without checkpointing a job restart loses in-flight windows
  and the Redis values briefly drop to pre-window-start.
- **Redis key TTL matches the FeatureView TTL.** If the Redis
  TTL is longer than the FeatureView's declared TTL, serving
  returns stale values that the training-side PIT join would
  have refused.

### 2.3 Nightly reconciliation

The offline path. Each night, batch over yesterday's
transactions, compute the same 5-minute tumbling aggregate, and
land the result at the path declared in `txns_src.path`:

```python
# batch/reconcile_txns_5min.py
import duckdb
from datetime import date, timedelta

yesterday = date.today() - timedelta(days=1)

duckdb.sql(f"""
COPY (
  SELECT
    user_id,
    time_bucket(INTERVAL '5 minutes', event_ts) AS window_start,
    time_bucket(INTERVAL '5 minutes', event_ts)
      + INTERVAL '5 minutes'                    AS window_end,
    COUNT(*)::BIGINT                            AS txns_5min
  FROM read_parquet('warehouse/transactions/dt={yesterday}/*.parquet')
  GROUP BY 1, 2, 3
) TO 'data/txns_5min.parquet' (FORMAT PARQUET);
""")
```

The batch output's schema must match `txns_src` exactly
(`user_id`, `window_end`, `txns_5min`). The entity-dataframe
timestamp used for training joins — the label timestamp —
compares against `window_end`, so the PIT join from
[`../exercise-02/SOLUTION.md`](../exercise-02/SOLUTION.md) picks
the most recent closed window whose `window_end <= label_ts`,
which is exactly what serving would have returned at `label_ts`.

### 2.4 Reconciliation diff

The alerting path. Draw a sample of `(user_id, window_end)` keys
from yesterday's batch output and, for each, compare the batch
value against the stream value that was emitted for the same
window. The stream value is recovered by replaying the Kafka
offsets that fall inside the window (Kafka retention must cover
at least one reconciliation lag):

```python
# batch/reconcile_diff.py
# For a sample of (user_id, window_end), the stream and batch
# aggregates must agree. A discrepancy that exceeds the declared
# tolerance pages the on-call. The tolerance is NOT zero: stream
# late data and watermark misses produce small, bounded drift.
TOLERANCE_ROWS_PER_1000 = 1  # 0.1% keys may diverge by 1
```

The tolerance is declared, not discovered. Discovering it after
an incident means the alert was decorative.

### 2.5 Decision rationale

- **Lambda-architecture-style stream + batch, not stream-only.**
  Without the nightly batch, training sets point at the empty
  feature view path and PIT joins return nulls; the model trains
  without `txns_5min` and then serving reads a value for it,
  which is the exact train-serve skew the module exists to
  prevent.
- **Redis TTL == FeatureView TTL == 2 windows.** All three TTLs
  are the same number because they describe the same guarantee:
  "a value is fresh for the duration of exactly two windows".
  Letting them drift apart is where the bugs come from.
- **Event-time windows, not processing-time.** Processing-time
  windows produce reproducibility only in the absence of
  consumer lag — i.e. never, in production. Event-time windows
  are reproducible from the Kafka log, which is the property the
  reconciliation diff depends on.
- **Reconciliation is a separate job, not a flag on the batch
  job.** A single job that computes both and silently writes
  "matched" without surfacing the diff is worse than no
  reconciliation at all; the alert would never fire.

## 3. Validation steps

A learner's submission is valid if all of the following hold:

1. **Online path runs.** The PyFlink job consumes from Kafka and
   writes to Redis under the key `user_txns_5min:{user_id}`.
   `redis-cli GET user_txns_5min:<id>` returns an integer for an
   active user.
2. **Offline path runs.** A single invocation of the nightly
   batch job produces `data/txns_5min.parquet` with the expected
   columns and `window_end` dtype timestamp.
3. **Feast reads both.** `fs.get_online_features` for
   `user_txns_5min:txns_5min` returns the Redis value;
   `fs.get_historical_features` for the same reference returns
   the parquet value point-in-time-joined against the entity
   DataFrame.
4. **TTLs agree.** `ttl` in `user_txns_5min`, Redis `EX` in the
   sink, and the reconciliation window span use the same
   duration (2 windows = 10 minutes).
5. **Reconciliation diff reports within tolerance.** For a
   sample of ≥ 1,000 `(user_id, window_end)` keys from a closed
   day, the stream vs. batch values agree within the declared
   tolerance (§2.4). A zero-divergence result on a non-trivial
   sample means either the sample is degenerate or the batch is
   secretly reading Redis — investigate.
6. **A deliberate failure test is included.** Kill the Flink
   job mid-window, wait for a Kafka restart, and show that
   checkpointed state is recovered and the window emits once,
   not twice. A submission that has not demonstrated this has
   not shown the online path is actually exactly-once.

## 4. Rubric / review checklist

| Dimension | Pass | Fail |
|---|---|---|
| Streaming substrate | PyFlink / Faust / equivalent stateful stream processor with event-time windows | Loop + `sleep` polling Kafka, or processing-time windows |
| Window shape | Tumbling, 5-minute, keyed by `user_id`, emits `(user_id, window_end, count)` | Sliding windows, un-keyed aggregates, or ad-hoc intervals |
| Watermarks | Bounded-out-of-orderness strategy with a declared lag budget | Default / no watermark strategy |
| Online write | Redis (or declared online store from `feature_store.yaml`), TTL matches FeatureView TTL | Online writes land in the offline store, or TTLs disagree |
| Offline reconciliation | Batch job computes the same aggregate from the offline source nightly and lands at the FeatureView's declared `path` | Streaming-only; PIT join returns nulls |
| Reconciliation diff | Separate job, sample-based, declared tolerance, alerts on breach | No diff, or diff silently writes "ok" |
| Failure-recovery evidence | Checkpointing enabled and a documented kill-and-restart test showing exactly-once emission | No evidence the job survives restart |
| Feast integration | A real `FeatureView` with `timestamp_field="window_end"` and `ttl` = 2 windows | Hard-coded Redis keys read without going through Feast |

A submission passes if every row is at Pass; any Fail row is sent
back regardless of how polished the rest is.

## 5. Common mistakes

Carried forward from
[`../SOLUTION.md`](../SOLUTION.md#common-mistakes-graders-see)
items 2 and 4, plus patterns specific to this exercise:

1. **Streaming feature with no nightly reconciliation.** The
   online store has the value; the offline store never does.
   Training sees nulls for the feature at every label
   timestamp, then serving reads a value, and the model is
   quietly worse — the item 4 failure from the module's
   common-mistakes list.
2. **Same store for online and offline.** Redis cannot hold a
   multi-year training window; Postgres/DuckDB cannot serve
   single-digit-millisecond point lookups. Trying to do both
   from one store fails on cost on one side and latency on the
   other.
3. **Processing-time windows.** The aggregate is a function of
   the stream processor's clock rather than the event clock; a
   consumer-lag spike produces silently-wrong values, and the
   reconciliation diff cannot distinguish "stream was wrong"
   from "batch was right".
4. **Mismatched TTLs.** Redis `EX` longer than the FeatureView
   TTL means serving returns values the training-side PIT join
   would have refused. Redis `EX` shorter means legitimate
   online reads miss while the FeatureView still claims the
   value is fresh.
5. **No watermark, or a watermark of zero.** Late-arriving
   events are either dropped (artificially low aggregates) or
   wait forever (windows never emit). A declared lag budget is
   required; the right number is deployment-specific, but there
   must be a number.
6. **Reconciliation diff without a declared tolerance.** A
   nonzero diff is expected (late data, retries). A diff job
   that pages on any difference pages constantly and gets
   silenced; a diff job that pages only on zero differences
   never pages at all. The tolerance is a design decision,
   recorded in code.
7. **`timestamp_field` set to the stream processing time rather
   than `window_end`.** The PIT join uses this field to decide
   which window value was observable at label time; getting it
   wrong reintroduces leakage even though every other part of
   the pipeline looks correct.

## 6. References

**Local**

- Module-level rationale:
  [`../SOLUTION.md`](../SOLUTION.md) §Ex-04 and
  §"Common mistakes graders see".
- Feature repo the streaming view extends:
  [`../exercise-01/features.py`](../exercise-01/features.py),
  [`../exercise-01/feature_store.yaml`](../exercise-01/feature_store.yaml).
- Companion PIT-join discipline the offline path feeds into:
  [`../exercise-02/SOLUTION.md`](../exercise-02/SOLUTION.md).
- Materialization / backfill job the batch reconciliation
  parallels: [`../exercise-03/materialize_dag.py`](../exercise-03/materialize_dag.py).
- Learning exercise prompt:
  `lessons/mod-004-feature-store/exercises/exercise-04-streaming-feature.md`
  in the `ai-infra-ml-platform-learning` repo.

**Official project documentation**

- Apache Flink — *Windows* (tumbling / sliding / session, event
  vs. processing time):
  <https://nightlies.apache.org/flink/flink-docs-stable/docs/dev/datastream/operators/windows/>
- Apache Flink — *Generating Watermarks* (bounded out-of-orderness
  strategy):
  <https://nightlies.apache.org/flink/flink-docs-stable/docs/dev/datastream/event-time/generating_watermarks/>
- Apache Flink — *Checkpointing* (exactly-once state recovery):
  <https://nightlies.apache.org/flink/flink-docs-stable/docs/dev/datastream/fault-tolerance/checkpointing/>
- Feast — *Push sources / streaming ingestion*:
  <https://docs.feast.dev/reference/data-sources/push>
- Feast — *FeatureView and TTL semantics*:
  <https://docs.feast.dev/getting-started/concepts/feature-view>

**Official standards (where applicable)**

- NIST AI Risk Management Framework — MEASURE function on
  validity and reliability of AI systems (stream/batch
  reconciliation is the operational control that keeps the
  training distribution and the serving distribution consistent):
  <https://www.nist.gov/itl/ai-risk-management-framework>
