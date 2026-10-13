"""Generate the synthetic datasets used by the workloads (run once, before experiments).

  taxi_synth   : NYC-taxi-like trips (with ~1% dirty rows for the cleaning stage)
  graph_edges  : skewed directed graph for the iterative rank job
"""
from __future__ import annotations

import argparse

from pyspark.sql import functions as F

from jobs.common import spark_session

EPOCH_2024_01_01 = 1704067200


def gen_taxi(spark, rows: int, partitions: int):
    base = spark.range(0, rows, numPartitions=partitions)
    dur = F.when(F.rand(7) < 0.01, F.lit(-5.0)).otherwise(120 + F.rand(8) * 2400)
    df = (base
          .withColumn("pickup_s", F.lit(EPOCH_2024_01_01) + (F.rand(1) * 30 * 86400).cast("long"))
          .withColumn("duration_s", dur)
          .withColumn("pickup_ts", F.timestamp_seconds("pickup_s"))
          .withColumn("dropoff_ts", F.timestamp_seconds(F.col("pickup_s") + F.col("duration_s").cast("long")))
          .withColumn("passenger_count", (F.floor(F.rand(2) * 4) + 1).cast("double"))
          .withColumn("trip_distance", F.abs(F.randn(3) * 3 + 2.5))
          .withColumn("pu_zone", (F.floor(F.pow(F.rand(4), 2) * 265) + 1).cast("int"))
          .withColumn("do_zone", (F.floor(F.rand(5) * 265) + 1).cast("int"))
          .withColumn("payment_type", F.when(F.rand(6) < 0.7, 1).otherwise(2))
          .withColumn("fare_amount", 3 + F.col("trip_distance") * 2.5
                      + F.col("duration_s") / 60 * 0.5 + F.randn(9))
          .withColumn("tip_amount", F.when(F.col("payment_type") == 1,
                                           F.col("fare_amount") * F.rand(10) * 0.25).otherwise(0.0))
          .withColumn("total_amount", F.col("fare_amount") + F.col("tip_amount") + 2.5)
          .drop("id", "pickup_s", "duration_s"))
    return df


def gen_graph(spark, nodes: int, edges: int, partitions: int):
    return (spark.range(0, edges, numPartitions=partitions)
            .withColumn("src", F.floor(F.rand(11) * nodes).cast("long"))
            .withColumn("dst", F.floor(F.pow(F.rand(12), 2) * nodes).cast("long"))
            .select("src", "dst").where("src != dst").dropDuplicates())


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data-root", default="s3a://data")
    p.add_argument("--taxi-rows", type=int, default=4_000_000)
    p.add_argument("--graph-nodes", type=int, default=200_000)
    p.add_argument("--graph-edges", type=int, default=2_000_000)
    p.add_argument("--partitions", type=int, default=16)
    a = p.parse_args()

    spark = spark_session("rmc-datagen")
    gen_taxi(spark, a.taxi_rows, a.partitions).write.mode("overwrite").parquet(f"{a.data_root}/taxi_synth")
    gen_graph(spark, a.graph_nodes, a.graph_edges, a.partitions).write.mode("overwrite") \
        .parquet(f"{a.data_root}/graph_edges")
    print("taxi rows:", spark.read.parquet(f"{a.data_root}/taxi_synth").count())
    print("graph edges:", spark.read.parquet(f"{a.data_root}/graph_edges").count())
    spark.stop()


if __name__ == "__main__":
    main()
