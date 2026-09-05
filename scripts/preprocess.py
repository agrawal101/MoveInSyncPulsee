from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Permit both `python scripts/preprocess.py` and module-style execution.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data.preprocessing import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Build normalized Parquet and DuckDB mobility data")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--chunk-size", type=int, default=100_000)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    report = run_pipeline(args.raw_dir.resolve(), args.processed_dir.resolve(), chunk_size=args.chunk_size)
    print("\nDATA QUALITY SUMMARY")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
