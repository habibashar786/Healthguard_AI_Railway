from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import logging
from typing import List, Dict, Optional
import asyncio
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("insurance_service")

app = FastAPI(
    title="Insurance Service",
    description="Insurance plans management service",
    version="1.0.0"
)

# Request/Response models
class QueryRequest(BaseModel):
    query: str
    user_id: Optional[str] = None

class InsuranceResponse(BaseModel):
    status: str
    data: List[Dict]
    timestamp: str
    service: str = "insurance"

# Mock insurance data
INSURANCE_DATA = [
    {
        "id": "INS001",
        "provider": "HealthFirst Insurance",
        "plan_name": "Premium Care Plus",
        "type": "HMO",
        "monthly_premium": 450,
        "deductible": 1000,
        "coverage": ["Emergency", "Surgery", "Prescription", "Dental"],
        "network_hospitals": ["H001", "H002"],
        "rating": 4.3
    },
    {
        "id": "INS002",
        "provider": "MediCare Solutions",
        "plan_name": "Family Health Plan",
        "type": "PPO",
        "monthly_premium": 650,
        "deductible": 500,
        "coverage": ["Emergency", "Surgery", "Prescription", "Mental Health", "Vision"],
        "network_hospitals": ["H001", "H003"],
        "rating": 4.1
    },
    {
        "id": "INS003",
        "provider": "Basic Health Co",
        "plan_name": "Essential Coverage",
        "type": "Bronze",
        "monthly_premium": 250,
        "deductible": 2500,
        "coverage": ["Emergency", "Basic Surgery"],
        "network_hospitals": ["H002"],
        "rating": 3.8
    },
    {
        "id": "INS004",
        "provider": "Elite Medical Insurance",
        "plan_name": "Platinum Select",
        "type": "Platinum",
        "monthly_premium": 850,
        "deductible": 200,
        "coverage": ["Emergency", "Surgery", "Prescription", "Dental", "Vision", "Mental Health", "Alternative Medicine"],
        "network_hospitals": ["H001", "H002", "H003"],
        "rating": 4.7
    }
]

# Health check endpoint
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "insurance",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }

# Insurance search endpoint
@app.post("/search", response_model=InsuranceResponse)
async def search_insurance(request: QueryRequest):
    try:
        logger.info(f"Received insurance search query: {request.query}")
        
        # Simulate processing delay
        await asyncio.sleep(0.3)
        
        query_lower = request.query.lower()
        
        # Search logic
        results = []
        for insurance in INSURANCE_DATA:
            if (query_lower in insurance["provider"].lower() or
                query_lower in insurance["plan_name"].lower() or
                query_lower in insurance["type"].lower() or
                any(coverage.lower() in query_lower for coverage in insurance["coverage"])):
                results.append(insurance)
        
        # Budget-based filtering
        if "cheap" in query_lower or "affordable" in query_lower or "budget" in query_lower:
            results = sorted(INSURANCE_DATA, key=lambda x: x["monthly_premium"])[:2]
        elif "premium" in query_lower or "best" in query_lower or "high" in query_lower:
            results = sorted(INSURANCE_DATA, key=lambda x: x["rating"], reverse=True)[:2]
        
        # If no specific matches, return all insurance plans
        if not results:
            results = INSURANCE_DATA
        
        logger.info(f"Found {len(results)} insurance matches")
        
        return InsuranceResponse(
            status="success",
            data=results,
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Insurance service error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Insurance service error: {str(e)}"
        )

# Get insurance by ID
@app.get("/insurance/{insurance_id}")
async def get_insurance(insurance_id: str):
    try:
        insurance = next((ins for ins in INSURANCE_DATA if ins["id"] == insurance_id), None)
        if not insurance:
            raise HTTPException(status_code=404, detail="Insurance plan not found")
        
        return {
            "status": "success",
            "data": insurance,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching insurance {insurance_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Get compatible insurance for hospital
@app.get("/compatible/{hospital_id}")
async def get_compatible_insurance(hospital_id: str):
    try:
        compatible_plans = [
            ins for ins in INSURANCE_DATA 
            if hospital_id in ins.get("network_hospitals", [])
        ]
        
        return InsuranceResponse(
            status="success",
            data=compatible_plans,
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"Error finding compatible insurance: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Get all insurance plans
@app.get("/insurance")
async def get_all_insurance():
    try:
        return InsuranceResponse(
            status="success",
            data=INSURANCE_DATA,
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"Error fetching all insurance: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(
        "insurance_server:app",
        host="0.0.0.0",
        port=8002,
        reload=True,
        log_level="info"
    )