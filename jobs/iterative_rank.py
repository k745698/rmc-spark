"""W3 - Iterative PageRank on a skewed graph (long lineage).

Each iteration is a resilient stage. Without checkpoints the lineage grows with every
iteration, so recovering a lost partition late in the job means recomputing all earlier
iterations - the case where adaptive checkpointing should help most.
"""
from __future__ import annotations

from pyspark.sql import functions as F

from jobs.common import spark_session, write_summary
from rds import ResilientPipeline, base_parser, context_from_args


def main():
    p = base_parser("iterative rank")
    p.add_argument("--iterations", type=int, default=12)
    p.add_argument("--damping", type=float, default=0.85)
    args = p.parse_args()
    ctx = context_from_args(args)
    spark = spark_session(f"iterative_rank-{ctx.job_id}-a{ctx.attempt}")
    pipe = ResilientPipeline(spark, ctx, linear=True)   # iterations form a single chain

    edges = spark.read.parquet(f"{ctx.data_root}/graph_edges").cache()
    out_deg = edges.groupBy("src").agg(F.count("*").alias("deg"))
    links = edges.join(out_deg, "src").cache()
    n = edges.select("src").union(edges.select("dst")).distinct().count()

    @pipe.stage("init")
    def init():
        nodes = edges.select(F.col("src").alias("node")).union(edges.select("dst")).distinct()
        return nodes.withColumn("rank", F.lit(1.0 / n))

    def make_iteration(i):
        @pipe.stage(f"iter_{i:02d}")
        def iterate(ranks):
            contrib = (links.join(ranks.withColumnRenamed("node", "src"), "src")
                            .select(F.col("dst").alias("node"), (F.col("rank") / F.col("deg")).alias("c")))
            summed = contrib.groupBy("node").agg(F.sum("c").alias("s"))
            return (ranks.select("node").join(summed, "node", "left")
                         .select("node", ((1 - args.damping) / n
                                          + args.damping * F.coalesce(F.col("s"), F.lit(0.0))).alias("rank")))
        return iterate

    ranks = init()
    for i in range(1, args.iterations + 1):
        ranks = make_iteration(i)(ranks)

    top = ranks.orderBy(F.desc("rank")).limit(100)
    top.write.mode("overwrite").parquet(f"{ctx.results_root}/{ctx.job_id}/top_ranks")
    write_summary(spark, f"{ctx.results_root}/{ctx.job_id}/_summary.json",
                  {"nodes": n, "iterations": args.iterations})
    pipe.finish(status="ok")
    spark.stop()


if __name__ == "__main__":
    main()
