from pathlib import Path

from pydantic import BaseModel, Field


class PreprocessingConfig(BaseModel):
    raw_dir: Path
    processed_dir: Path = Path("data/processed")
    chunk_size: int = Field(default=100_000, gt=0)

