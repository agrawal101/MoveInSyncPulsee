from fastapi import APIRouter,Depends
from app.agents.service import AgentService
from app.api.deps import get_agent_service
from app.models.agent import AgentQueryRequest,AgentResponse,InvestigationRequest
router=APIRouter(tags=["agent"])
@router.post("/agent/query",response_model=AgentResponse)
def query(request:AgentQueryRequest,service:AgentService=Depends(get_agent_service))->AgentResponse:return service.query(request)
@router.post("/agent/investigate",response_model=AgentResponse)
def investigate(request:InvestigationRequest,service:AgentService=Depends(get_agent_service))->AgentResponse:return service.investigate(request)

