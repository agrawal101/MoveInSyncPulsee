from fastapi import APIRouter
from app.analytics.service import get_data_quality_report
from app.models.agent import DataQualityResponse
router=APIRouter(tags=["data-quality"])
@router.get("/data-quality",response_model=DataQualityResponse)
def data_quality()->DataQualityResponse:return DataQualityResponse.model_validate(get_data_quality_report())

