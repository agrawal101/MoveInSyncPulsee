from fastapi import APIRouter
from app.llm.factory import is_llm_configured
from app.models.agent import HealthResponse
router=APIRouter(tags=["system"])
@router.get("/health",response_model=HealthResponse)
def health()->HealthResponse:return HealthResponse(status="ok",llm_configured=is_llm_configured())

