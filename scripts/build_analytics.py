from __future__ import annotations
import argparse, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from app.analytics.aggregates import build_aggregate_tables

def main() -> None:
    parser = argparse.ArgumentParser(description="Build deterministic analytics aggregates")
    parser.add_argument("--database", type=Path, default=Path("data/processed/mobility.duckdb"))
    args = parser.parse_args(); build_aggregate_tables(args.database.resolve())
    print(f"Analytics aggregates built: {args.database}")
if __name__ == "__main__": main()

