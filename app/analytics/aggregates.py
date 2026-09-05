from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from app.analytics.sql import AGGREGATE_SQL

logger = logging.getLogger(__name__)


def build_aggregate_tables(database_path: Path) -> None:
    """Idempotently materialize deterministic aggregate tables."""
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(AGGREGATE_SQL)
        connection.execute("CHECKPOINT")
    logger.info("Analytics aggregates rebuilt in %s", database_path)

