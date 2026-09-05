from fastapi import APIRouter,Query
from app.analytics.service import get_shift_readiness
from app.models.analytics import ShiftReadiness
router=APIRouter(tags=["operations"])
@router.get("/shifts/readiness",response_model=ShiftReadiness)
def shifts(month:str=Query(pattern=r"^\d{4}-\d{2}$"))->ShiftReadiness:return get_shift_readiness(month)

