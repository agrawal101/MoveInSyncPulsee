from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import agent, anomalies, cost, data_quality, delays, experience, health, overview, reports, safety, shifts, vendors
from app.llm.provider import LLMConfigurationError
from app.observability import configure_logging

configure_logging()
app = FastAPI(title="MoveInSync Pulse", version="0.4.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)
for router in [health.router, overview.router, anomalies.router, vendors.router, shifts.router, safety.router, delays.router, cost.router, experience.router, data_quality.router, agent.router, reports.router]:
    app.include_router(router, prefix="/api")

@app.exception_handler(LLMConfigurationError)
async def llm_configuration_error(_: Request, exc: LLMConfigurationError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc), "error": "llm_not_configured"})

@app.exception_handler(LookupError)
async def lookup_error(_: Request, exc: LookupError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})

@app.exception_handler(ValueError)
async def value_error(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})
