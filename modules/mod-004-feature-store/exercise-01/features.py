"""Feast feature definitions."""
from datetime import timedelta

from feast import Entity, FeatureView, Field, FileSource
from feast.types import Float32, Int64, String


user = Entity(name="user", join_keys=["user_id"])

clicks_src = FileSource(name="clicks_src", path="data/clicks.parquet",
                         timestamp_field="event_ts")

purchase_src = FileSource(name="purchase_src", path="data/purchases.parquet",
                           timestamp_field="event_ts")

user_clicks = FeatureView(
    name="user_clicks", entities=[user], ttl=timedelta(days=7),
    schema=[Field(name="clicks_7d", dtype=Int64),
             Field(name="last_category", dtype=String)],
    source=clicks_src,
)

user_purchase = FeatureView(
    name="user_purchase", entities=[user], ttl=timedelta(days=30),
    schema=[Field(name="purchases_30d", dtype=Int64),
             Field(name="ltv", dtype=Float32)],
    source=purchase_src,
)
