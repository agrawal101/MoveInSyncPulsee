from fastapi import APIRouter,Depends
from app.agents.service import AgentService
from app.api.deps import get_agent_service
from app.models.agent import AgentResponse,ExecutiveSummaryRequest
router=APIRouter(tags=["reports"])
@router.post("/reports/executive-summary",response_model=AgentResponse)
def executive_summary(request:ExecutiveSummaryRequest,service:AgentService=Depends(get_agent_service))->AgentResponse:return service.executive_summary(request)

