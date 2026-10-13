"""W1 - Batch ETL on taxi trips (shuffle-heavy): clean -> enrich -> aggregate -> rank -> write."""
from __future__ import annotations

from pyspark.sql import Window
from pyspark.sql import functions as F

from jobs.common import load_trips, spark_session, write_summary, zone_lookup
from rds import ResilientPipeline, base_parser, context_from_args


def main():
    p = base_parser("taxi ETL")
    p.add_argument("--source", default="synthetic", choices=["synthetic", "tlc"])
    args = p.parse_args()
    ctx = context_from_args(args)
    spark = spark_session(f"etl_taxi-{ctx.job_id}-a{ctx.attempt}")
    pipe = ResilientPipeline(spark, ctx)

    @pipe.stage("clean")
    def clean(df):
        return (df.withColumn("duration_min",
                              (F.unix_timestamp("dropoff_ts") - F.unix_timestamp("pickup_ts")) / 60.0)
                  .where((F.col("duration_min") > 1) & (F.col("duration_min") < 180))
                  .where((F.col("trip_distance") > 0) & (F.col("trip_distance") < 100))
                  .where(F.col("fare_amount") > 0)
                  .withColumn("speed_mph", F.col("trip_distance") / (F.col("duration_min") / 60.0))
                  .where(F.col("speed_mph") < 80)
                  .withColumn("pickup_hour", F.date_trunc("hour", "pickup_ts"))
                  .withColumn("tip_rate", F.when(F.col("fare_amount") > 0,
                                                 F.col("tip_amount") / F.col("fare_amount"))))

    @pipe.stage("enrich")
    def enrich(df):
        # two independent lookup relations, so the self-join has no ambiguous columns
        pu = zone_lookup(spark).toDF("pu_zone_id", "pu_borough")
        do = zone_lookup(spark).toDF("do_zone_id", "do_borough")
        return (df.join(F.broadcast(pu), F.col("pu_zone") == F.col("pu_zone_id"), "left")
                  .join(F.broadcast(do), F.col("do_zone") == F.col("do_zone_id"), "left")
                  .drop("pu_zone_id", "do_zone_id"))

    @pipe.stage("hourly_agg")
    def hourly(df):
        return (df.groupBy("pickup_hour", "pu_borough")
                  .agg(F.count("*").alias("trips"),
                       F.avg("fare_amount").alias("avg_fare"),
                       F.expr("percentile_approx(fare_amount, 0.95)").alias("p95_fare"),
                       F.avg("speed_mph").alias("avg_speed"),
                       F.avg("tip_rate").alias("avg_tip_rate")))

    @pipe.stage("zone_rank")
    def zone_rank(df):
        per_zone = df.groupBy("pu_zone", "do_borough").agg(F.sum("total_amount").alias("revenue"),
                                                          F.count("*").alias("trips"))
        w = Window.partitionBy("do_borough").orderBy(F.desc("revenue"))
        return per_zone.withColumn("rank", F.row_number().over(w)).where("rank <= 20")

    cleaned = clean(load_trips(spark, ctx.data_root, args.source))
    enriched = enrich(cleaned)
    agg = hourly(enriched)
    ranked = zone_rank(enriched)

    out = f"{ctx.results_root}/{ctx.job_id}"
    agg.write.mode("overwrite").parquet(f"{out}/hourly")
    ranked.write.mode("overwrite").parquet(f"{out}/zone_rank")
    write_summary(spark, f"{out}/_summary.json", {"hourly_rows": agg.count(), "rank_rows": ranked.count()})
    pipe.finish(status="ok")
    spark.stop()


if __name__ == "__main__":
    main()
