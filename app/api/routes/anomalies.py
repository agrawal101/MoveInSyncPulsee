from typing import Literal
from fastapi import APIRouter,Query
from app.analytics.anomaly_detection import detect_anomalies
from app.models.analytics import Anomaly
router=APIRouter(tags=["anomalies"])
@router.get("/anomalies",response_model=list[Anomaly])
def anomalies(month:str=Query(pattern=r"^\d{4}-\d{2}$"),severity:Literal["low","medium","high","positive"]|None=None,limit:int=Query(10,ge=1,le=100))->list[Anomaly]:
    rows=detect_anomalies(month);return [row for row in rows if severity is None or row.severity==severity][:limit]

