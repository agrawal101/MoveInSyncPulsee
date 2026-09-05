from __future__ import annotations

import pandas as pd

from app.data.preprocessing import reconcile_monthly_schemas
from app.data.validators import coerce_numeric, normalize_identifier, parse_datetime


def test_trip_id_normalization() -> None:
    result = normalize_identifier(pd.Series(["1,097,076", " 1123974 ", 123, None]))
    assert result.tolist()[:3] == [1097076, 1123974, 123]
    assert pd.isna(result.iloc[3])


def test_malformed_trip_id_becomes_null() -> None:
    result = normalize_identifier(pd.Series(["bad-id", "12.5", ""] ))
    assert result.isna().all()


def test_numeric_coercion_handles_commas_nulls_and_bad_values() -> None:
    result = coerce_numeric(pd.Series(["1,200.5", " -6.63 ", None, "bad"]))
    assert result.iloc[0] == 1200.5
    assert result.iloc[1] == -6.63
    assert result.iloc[2:].isna().all()


def test_date_conversion_handles_mixed_and_epoch_values() -> None:
    mixed = parse_datetime(pd.Series(["May 1, 2026", "June 3, 2026, 11:00 AM", "bad"]))
    epoch = parse_datetime(pd.Series(["1,777,595,400", None]), epoch=True)
    assert str(mixed.iloc[0]) == "2026-05-01 00:00:00+00:00"
    assert str(mixed.iloc[1]) == "2026-06-03 11:00:00+00:00"
    assert pd.isna(mixed.iloc[2])
    assert str(epoch.iloc[0]) == "2026-05-01 00:30:00+00:00"


def test_monthly_schema_reconciliation_unions_columns() -> None:
    may = pd.DataFrame({"trip_id": [1], "planned_km": [1.0]})
    july = pd.DataFrame({"trip_id": [2], "new_column": ["x"]})
    reconciled = reconcile_monthly_schemas([may, july])
    assert list(reconciled[0].columns) == ["trip_id", "planned_km", "new_column"]
    assert reconciled[0]["new_column"].isna().all()
    assert reconciled[1]["planned_km"].isna().all()
