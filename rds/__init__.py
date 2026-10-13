"""rds - Resilient Data Science programming primitives for PySpark."""
from .cli import JobContext, base_parser, context_from_args
from .events import EventLog, read_events
from .policy import (AdaptivePolicy, AlwaysPolicy, NeverPolicy, daly_interval,
                     expected_lost_work, make_policy, young_interval)


def ResilientPipeline(*args, **kwargs):  # noqa: N802 - lazy import keeps pyspark optional for tests
    from .stage import ResilientPipeline as _RP
    return _RP(*args, **kwargs)


__all__ = ["JobContext", "base_parser", "context_from_args", "EventLog", "read_events",
           "AdaptivePolicy", "AlwaysPolicy", "NeverPolicy", "daly_interval", "young_interval",
           "expected_lost_work", "make_policy", "ResilientPipeline"]
