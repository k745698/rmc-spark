"""ResilientPipeline: idempotent, resumable PySpark stages backed by shared (S3/MinIO) storage.

Usage inside a job:

    pipe = ResilientPipeline(spark, ctx)          # ctx from rds.cli.parse_context()

    @pipe.stage("clean")
    def clean(df):
        return df.filter(...)

    out = clean(raw_df)        # computed once; on a re-run (same job_id, any cluster) it is restored

Commit protocol: a stage's data is written to <base>/<stage>/data and only afterwards a small
marker file <base>/<stage>/_RDS_COMMIT is created. A stage counts as checkpointed only when
the marker exists, so output half-written by a crashed attempt is never read back.
"""
from __future__ import annotations

import json
import time
from functools import wraps

from .events import EventLog
from .policy import Ewma, make_policy


class SkippedStage:
    """Placeholder returned for a stage made redundant by a later committed stage (linear mode)."""

    def __init__(self, name: str):
        self.name = name

    def __repr__(self):
        return f"<skipped stage {self.name}>"


class ResilientPipeline:
    def __init__(self, spark, ctx, write_cost_prior_s: float = 3.0, linear: bool = False):
        """linear=True: stages form one chain (each consumes only the previous one). On a re-run,
        stages before the latest committed stage are then skipped instead of recomputed."""
        self.spark = spark
        self.ctx = ctx
        self.base = f"{ctx.checkpoint_root.rstrip('/')}/{ctx.job_id}"
        self.policy = make_policy(ctx.policy, ctx.mtbf_s)
        self.write_cost = Ewma(write_cost_prior_s)
        self.uncheckpointed_work_s = 0.0
        self.linear = linear
        self._seq = 0
        self.events = EventLog(ctx.events_file, job_id=ctx.job_id, attempt=ctx.attempt,
                               cluster=ctx.cluster, policy=self.policy.name)
        self._jvm = spark._jvm
        self._hconf = spark._jsc.hadoopConfiguration()
        self.committed = self._load_commits()
        self.events.emit("attempt_started", mtbf_s=ctx.mtbf_s, committed_stages=sorted(self.committed))

    def _load_commits(self) -> dict:
        """name -> sequence number of every committed stage of this job (from earlier attempts)."""
        fs_path = self._path(f"{self.base}/*/_RDS_COMMIT")
        fs = fs_path.getFileSystem(self._hconf)
        statuses = fs.globStatus(fs_path)
        found = {}
        for st in statuses or []:
            reader = self._jvm.java.io.BufferedReader(
                self._jvm.java.io.InputStreamReader(fs.open(st.getPath()), "UTF-8"))
            try:
                meta = json.loads(reader.readLine())
                found[meta["stage"]] = int(meta.get("seq", -1))
            except Exception:  # unreadable marker -> treat stage as not committed
                pass
            finally:
                reader.close()
        return found

    # ------------------------------------------------------------------ storage helpers
    def _path(self, uri: str):
        return self._jvm.org.apache.hadoop.fs.Path(uri)

    def _exists(self, uri: str) -> bool:
        p = self._path(uri)
        return bool(p.getFileSystem(self._hconf).exists(p))

    def _write_marker(self, uri: str, payload: dict) -> None:
        p = self._path(uri)
        out = p.getFileSystem(self._hconf).create(p, True)
        try:
            out.write(bytearray(json.dumps(payload).encode("utf-8")))
        finally:
            out.close()

    def stage_uri(self, name: str) -> str:
        return f"{self.base}/{name}"

    def is_committed(self, name: str) -> bool:
        return name in self.committed or self._exists(f"{self.stage_uri(name)}/_RDS_COMMIT")

    # ------------------------------------------------------------------ the decorator
    def stage(self, name: str, kind: str = "dataframe", loader=None, force_checkpoint: bool = False):
        """kind='dataframe' for DataFrames, kind='model' for pyspark.ml models (pass loader=ModelClass)."""
        if kind == "model" and loader is None:
            raise ValueError("model stages need loader=<pyspark.ml model class>")

        def decorator(fn):
            @wraps(fn)
            def wrapper(*args, **kwargs):
                return self._run_stage(name, kind, loader, force_checkpoint, fn, args, kwargs)
            return wrapper
        return decorator

    def _run_stage(self, name, kind, loader, force, fn, args, kwargs):
        uri = self.stage_uri(name)
        seq = self._seq
        self._seq += 1
        if self.linear and name not in self.committed and self.committed \
                and max(self.committed.values()) > seq:
            self.events.emit("stage_skipped", stage=name, seq=seq)
            return SkippedStage(name)
        if self.is_committed(name):
            t0 = time.time()
            result = loader.load(f"{uri}/data") if kind == "model" else self.spark.read.parquet(f"{uri}/data")
            self.uncheckpointed_work_s = 0.0
            self.events.emit("stage_restored", stage=name, restore_s=time.time() - t0)
            return result

        self.events.emit("stage_started", stage=name)
        t0 = time.time()
        result = fn(*args, **kwargs)
        rows = None
        if kind == "dataframe":
            from pyspark import StorageLevel
            result = result.persist(StorageLevel.MEMORY_AND_DISK)
            rows = result.count()          # materialise so stage time is real compute time
        compute_s = time.time() - t0
        self.uncheckpointed_work_s += compute_s

        decision = self.policy.decide(self.uncheckpointed_work_s, self.write_cost.value, force)
        if not decision.checkpoint:
            self.events.emit("stage_completed", stage=name, compute_s=compute_s, rows=rows,
                             uncheckpointed_work_s=self.uncheckpointed_work_s,
                             checkpoint=False, reason=decision.reason, tau_s=decision.interval_s)
            return result

        t1 = time.time()
        if kind == "model":
            result.write().overwrite().save(f"{uri}/data")
        else:
            result.write.mode("overwrite").parquet(f"{uri}/data")
        write_s = time.time() - t1
        self._write_marker(f"{uri}/_RDS_COMMIT", {"stage": name, "seq": seq, "job_id": self.ctx.job_id,
                                                  "attempt": self.ctx.attempt, "ts": time.time()})
        self.committed[name] = seq
        self.write_cost.update(write_s)
        lost_if_failed = self.uncheckpointed_work_s
        self.uncheckpointed_work_s = 0.0
        if kind == "dataframe":
            restored = self.spark.read.parquet(f"{uri}/data")   # truncates lineage
            result.unpersist()
            result = restored
        self.events.emit("stage_completed", stage=name, compute_s=compute_s, rows=rows,
                         uncheckpointed_work_s=lost_if_failed, checkpoint=True, write_s=write_s,
                         reason=decision.reason, tau_s=decision.interval_s)
        return result

    def finish(self, **summary) -> None:
        self.events.emit("attempt_finished", **summary)
