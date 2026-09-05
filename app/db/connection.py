from __future__ import annotations

from pathlib import Path

import duckdb


def rebuild_database(database_path: Path, parquet_files: dict[str, Path]) -> None:
    """Build a fresh DuckDB file; caller atomically publishes it after success."""
    if database_path.exists():
        database_path.unlink()
    with duckdb.connect(str(database_path)) as connection:
        for table, path in dict.fromkeys((name, path) for name, path in parquet_files.items()):
            safe_table = table.replace('"', '""')
            connection.execute(
                f'CREATE TABLE "{safe_table}" AS SELECT * FROM read_parquet(?)', [str(path)]
            )
        connection.execute("CHECKPOINT")


def connect_read_only(database_path: Path) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(database_path), read_only=True)

