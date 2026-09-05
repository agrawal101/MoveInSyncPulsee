from fastapi import APIRouter,Query
from app.analytics.service import analyze_vendor,compare_vendor_performance
from app.models.analytics import VendorAnalysis,VendorResult
router=APIRouter(tags=["vendors"])
@router.get("/vendors",response_model=VendorAnalysis)
def vendors(month:str=Query(pattern=r"^\d{4}-\d{2}$"),baseline_month:str=Query(pattern=r"^\d{4}-\d{2}$"))->VendorAnalysis:return compare_vendor_performance(month,baseline_month)
@router.get("/vendors/{vendor_name}",response_model=VendorResult)
def vendor(vendor_name:str,month:str=Query(pattern=r"^\d{4}-\d{2}$"),baseline_month:str|None=Query(None,pattern=r"^\d{4}-\d{2}$"))->VendorResult:return analyze_vendor(vendor_name,month,baseline_month)

