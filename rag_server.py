from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
import uvicorn
import logging
from typing import List, Dict, Optional, Any
import asyncio
import httpx
from datetime import datetime
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rag_service")

app = FastAPI(
    title="RAG Service",
    description="Retrieval Augmented Generation service for healthcare queries",
    version="1.0.0"
)

# Configuration
HOSPITAL_SERVICE_URL = "http://localhost:8001"
INSURANCE_SERVICE_URL = "http://localhost:8002"
REQUEST_TIMEOUT = 10.0

# Request/Response models
class QueryRequest(BaseModel):
    query: str
    user_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

class RAGResponse(BaseModel):
    status: str
    answer: str
    sources: Dict[str, Any]
    confidence: float
    timestamp: str
    service: str = "rag"

class ServiceStatus(BaseModel):
    hospital: bool = False
    insurance: bool = False
    rag: bool = True

# Global service status tracking
service_status = ServiceStatus()

# Health check endpoint
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "rag",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
        "dependencies": {
            "hospital_service": service_status.hospital,
            "insurance_service": service_status.insurance
        }
    }

# Service health checker
async def check_service_health(service_url: str, service_name: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{service_url}/health")
            if response.status_code == 200:
                logger.info(f"{service_name} service is healthy")
                return True
            else:
                logger.warning(f"{service_name} service returned {response.status_code}")
                return False
    except Exception as e:
        logger.error(f"{service_name} service health check failed: {str(e)}")
        return False

# Background task to monitor service health
async def monitor_services():
    while True:
        service_status.hospital = await check_service_health(HOSPITAL_SERVICE_URL, "Hospital")
        service_status.insurance = await check_service_health(INSURANCE_SERVICE_URL, "Insurance")
        await asyncio.sleep(30)  # Check every 30 seconds

# Start monitoring on startup
@app.on_event("startup")
async def startup_event():
    # Initial health check
    service_status.hospital = await check_service_health(HOSPITAL_SERVICE_URL, "Hospital")
    service_status.insurance = await check_service_health(INSURANCE_SERVICE_URL, "Insurance")
    
    # Start background monitoring
    asyncio.create_task(monitor_services())
    logger.info("RAG service started with service monitoring")

# Safe service call with fallback
async def safe_service_call(service_url: str, endpoint: str, data: Dict, service_name: str) -> Optional[Dict]:
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            url = f"{service_url}/{endpoint}"
            logger.info(f"Calling {service_name} service: {url}")
            
            response = await client.post(url, json=data)
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"{service_name} service responded successfully")
            return result
            
    except httpx.TimeoutException:
        logger.error(f"{service_name} service timeout")
        return None
    except httpx.RequestError as e:
        logger.error(f"{service_name} service connection error: {str(e)}")
        return None
    except httpx.HTTPStatusError as e:
        logger.error(f"{service_name} service HTTP error: {e.response.status_code}")
        return None
    except Exception as e:
        logger.error(f"{service_name} service unexpected error: {str(e)}")
        return None

# Generate AI-like response based on available data
def generate_response(query: str, hospital_data: Optional[Dict], insurance_data: Optional[Dict]) -> tuple[str, float]:
    query_lower = query.lower()
    
    # Determine query intent
    is_hospital_query = any(word in query_lower for word in ['hospital', 'doctor', 'medical', 'treatment', 'emergency'])
    is_insurance_query = any(word in query_lower for word in ['insurance', 'plan', 'coverage', 'premium', 'deductible'])
    
    response_parts = []
    confidence = 0.0
    
    # Process hospital data
    if hospital_data and hospital_data.get('status') == 'success':
        hospitals = hospital_data.get('data', [])
        if hospitals:
            confidence += 0.4
            if is_hospital_query or not is_insurance_query:
                response_parts.append(f"I found {len(hospitals)} relevant hospitals for you:")
                for hospital in hospitals[:3]:  # Limit to top 3
                    response_parts.append(f"• {hospital['name']} - {hospital['location']}, Rating: {hospital['rating']}/5")
    
    # Process insurance data
    if insurance_data and insurance_data.get('status') == 'success':
        insurance_plans = insurance_data.get('data', [])
        if insurance_plans:
            confidence += 0.4
            if is_insurance_query or not is_hospital_query:
                response_parts.append(f"I found {len(insurance_plans)} relevant insurance plans:")
                for plan in insurance_plans[:3]:  # Limit to top 3
                    response_parts.append(f"• {plan['plan_name']} by {plan['provider']} - ${plan['monthly_premium']}/month")
    
    # Fallback responses
    if not response_parts:
        if not service_status.hospital and not service_status.insurance:
            return "I'm sorry, but our healthcare services are temporarily unavailable. Please try again later.", 0.1
        elif not service_status.hospital:
            return "Hospital information is currently unavailable, but other services are working. Please try again later.", 0.2
        elif not service_status.insurance:
            return "Insurance information is currently unavailable, but other services are working. Please try again later.", 0.2
        else:
            return "I couldn't find specific information for your query, but our services are available. Could you please rephrase your question?", 0.3
    
    # Add general advice
    if confidence > 0.5:
        response_parts.append("\nFor the most accurate and up-to-date information, please contact the providers directly.")
        confidence = min(confidence + 0.2, 0.9)
    
    return "\n".join(response_parts), confidence

# Main RAG endpoint
@app.post("/query", response_model=RAGResponse)
async def process_query(request: QueryRequest):
    try:
        logger.info(f"Processing RAG query: {request.query}")
        
        query_data = {"query": request.query, "user_id": request.user_id}
        
        # Parallel calls to both services with fallback handling
        tasks = []
        
        if service_status.hospital:
            tasks.append(safe_service_call(HOSPITAL_SERVICE_URL, "search", query_data, "Hospital"))
        else:
            tasks.append(asyncio.create_task(asyncio.sleep(0, result=None)))
            
        if service_status.insurance:
            tasks.append(safe_service_call(INSURANCE_SERVICE_URL, "search", query_data, "Insurance"))
        else:
            tasks.append(asyncio.create_task(asyncio.sleep(0, result=None)))
        
        # Wait for both services (or timeouts)
        hospital_result, insurance_result = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle exceptions
        if isinstance(hospital_result, Exception):
            logger.error(f"Hospital service exception: {hospital_result}")
            hospital_result = None
            
        if isinstance(insurance_result, Exception):
            logger.error(f"Insurance service exception: {insurance_result}")
            insurance_result = None
        
        # Generate response
        answer, confidence = generate_response(request.query, hospital_result, insurance_result)
        
        # Prepare sources
        sources = {
            "hospital": {
                "available": hospital_result is not None,
                "data": hospital_result if hospital_result else {"status": "unavailable", "message": "Hospital service is currently down"}
            },
            "insurance": {
                "available": insurance_result is not None,
                "data": insurance_result if insurance_result else {"status": "unavailable", "message": "Insurance service is currently down"}
            }
        }
        
        logger.info(f"RAG response generated with confidence: {confidence}")
        
        return RAGResponse(
            status="success",
            answer=answer,
            sources=sources,
            confidence=confidence,
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        logger.error(f"RAG service error: {str(e)}")
        # Return graceful error response instead of HTTP exception
        return RAGResponse(
            status="error",
            answer="I'm experiencing some technical difficulties right now. Please try again in a moment.",
            sources={"error": str(e)},
            confidence=0.0,
            timestamp=datetime.now().isoformat()
        )

# Service status endpoint
@app.get("/status")
async def get_service_status():
    return {
        "rag_service": "healthy",
        "dependencies": {
            "hospital_service": "healthy" if service_status.hospital else "unhealthy",
            "insurance_service": "healthy" if service_status.insurance else "unhealthy"
        },
        "timestamp": datetime.now().isoformat()
    }

# Manual service health refresh
@app.post("/refresh-services")
async def refresh_service_status():
    service_status.hospital = await check_service_health(HOSPITAL_SERVICE_URL, "Hospital")
    service_status.insurance = await check_service_health(INSURANCE_SERVICE_URL, "Insurance")
    
    return {
        "message": "Service status refreshed",
        "status": {
            "hospital": service_status.hospital,
            "insurance": service_status.insurance
        }
    }

if __name__ == "__main__":
    uvicorn.run(
        "rag_server:app",
        host="0.0.0.0",
        port=8003,
        reload=True,
        log_level="info"
    )