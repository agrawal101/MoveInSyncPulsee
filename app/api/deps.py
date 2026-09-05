from app.agents.service import AgentService
from app.llm.factory import create_llm_provider

def get_agent_service() -> AgentService:
    return AgentService(create_llm_provider())

