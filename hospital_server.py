from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import logging
from typing import List, Dict, Optional
import asyncio
from datetime import datetime
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hospital_service")

app = FastAPI(
    title="Hospital Service",
    description="Hospital data management service",
    version="1.0.0"
)

# Request/Response models
class QueryRequest(BaseModel):
    query: str
    user_id: Optional[str] = None

class HospitalResponse(BaseModel):
    status: str
    data: List[Dict]
    timestamp: str
    service: str = "hospital"

# Mock hospital data
HOSPITAL_DATA = [
    {
        "id": "H001",
        "name": "City General Hospital",
        "specialties": ["Cardiology", "Neurology", "Emergency"],
        "location": "Downtown",
        "rating": 4.5,
        "doctors": 150,
        "emergency_services": True
    },
    {
        "id": "H002", 
        "name": "St. Mary's Medical Center",
        "specialties": ["Oncology", "Pediatrics", "Surgery"],
        "location": "North Side",
        "rating": 4.2,
        "doctors": 120,
        "emergency_services": True
    },
    {
        "id": "H003",
        "name": "Regional Specialty Clinic",
        "specialties": ["Dermatology", "Orthopedics"],
        "location": "Suburbs", 
        "rating": 4.0,
        "doctors": 80,
        "emergency_services": False
    }
]

# Health check endpoint
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "hospital",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }

# Hospital search endpoint
@app.post("/search", response_model=HospitalResponse)
async def search_hospitals(request: QueryRequest):
    try:
        logger.info(f"Received hospital search query: {request.query}")
        
        # Simulate processing delay
        await asyncio.sleep(0.5)
        
        query_lower = request.query.lower()
        
        # Search logic
        results = []
        for hospital in HOSPITAL_DATA:
            if (query_lower in hospital["name"].lower() or 
                any(specialty.lower() in query_lower for specialty in hospital["specialties"]) or
                query_lower in hospital["location"].lower()):
                results.append(hospital)
        
        # If no specific matches, return all hospitals
        if not results:
            results = HOSPITAL_DATA
        
        logger.info(f"Found {len(results)} hospital matches")
        
        return HospitalResponse(
            status="success",
            data=results,
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Hospital service error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Hospital service error: {str(e)}"
        )

# Get hospital by ID
@app.get("/hospital/{hospital_id}")
async def get_hospital(hospital_id: str):
    try:
        hospital = next((h for h in HOSPITAL_DATA if h["id"] == hospital_id), None)
        if not hospital:
            raise HTTPException(status_code=404, detail="Hospital not found")
        
        return {
            "status": "success",
            "data": hospital,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching hospital {hospital_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Get all hospitals
@app.get("/hospitals")
async def get_all_hospitals():
    try:
        return HospitalResponse(
            status="success",
            data=HOSPITAL_DATA,
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"Error fetching all hospitals: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(
        "hospital_server:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info"
    )