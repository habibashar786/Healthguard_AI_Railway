from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn
import httpx
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import asyncio
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gateway_service")

app = FastAPI(
    title="Healthcare Gateway Service",
    description="Main gateway for healthcare application",
    version="1.0.0"
)

# CORS middleware for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Service URLs
SERVICES = {
    "hospital": "http://localhost:8001",
    "insurance": "http://localhost:8002", 
    "rag": "http://localhost:8003"
}

REQUEST_TIMEOUT = 15.0

# Request models
class QueryRequest(BaseModel):
    query: str
    user_id: Optional[str] = None

class HealthCheckResponse(BaseModel):
    status: str
    services: Dict[str, Dict[str, Any]]
    timestamp: str

# Circuit breaker state
circuit_breaker = {
    "hospital": {"failures": 0, "last_failure": None, "open": False},
    "insurance": {"failures": 0, "last_failure": None, "open": False},
    "rag": {"failures": 0, "last_failure": None, "open": False}
}

MAX_FAILURES = 3
CIRCUIT_TIMEOUT = 60  # seconds

def should_call_service(service_name: str) -> bool:
    """Check if service should be called based on circuit breaker state"""
    breaker = circuit_breaker[service_name]
    
    if not breaker["open"]:
        return True
    
    # Check if circuit should be reset
    if breaker["last_failure"]:
        time_since_failure = (datetime.now() - breaker["last_failure"]).total_seconds()
        if time_since_failure > CIRCUIT_TIMEOUT:
            breaker["failures"] = 0
            breaker["open"] = False
            breaker["last_failure"] = None
            logger.info(f"Circuit breaker reset for {service_name}")
            return True
    
    return False

def record_service_failure(service_name: str):
    """Record service failure and potentially open circuit breaker"""
    breaker = circuit_breaker[service_name]
    breaker["failures"] += 1
    breaker["last_failure"] = datetime.now()
    
    if breaker["failures"] >= MAX_FAILURES:
        breaker["open"] = True
        logger.warning(f"Circuit breaker opened for {service_name}")

def record_service_success(service_name: str):
    """Record service success and reset failure count"""
    breaker = circuit_breaker[service_name]
    if breaker["failures"] > 0:
        breaker["failures"] = 0
        breaker["last_failure"] = None
        breaker["open"] = False

async def call_service(service_name: str, endpoint: str, method: str = "GET", data: Optional[Dict] = None) -> Optional[Dict]:
    """Make a resilient call to a service with circuit breaker pattern"""
    
    if not should_call_service(service_name):
        logger.warning(f"Circuit breaker open for {service_name}, skipping call")
        return None
    
    try:
        service_url = SERVICES[service_name]
        url = f"{service_url}/{endpoint.lstrip('/')}"
        
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            if method.upper() == "POST":
                response = await client.post(url, json=data or {})
            else:
                response = await client.get(url)
            
            response.raise_for_status()
            result = response.json()
            
            record_service_success(service_name)
            logger.info(f"Successfully called {service_name} service")
            return result
            
    except httpx.TimeoutException:
        logger.error(f"{service_name} service timeout")
        record_service_failure(service_name)
    except httpx.RequestError as e:
        logger.error(f"{service_name} service connection error: {str(e)}")
        record_service_failure(service_name)
    except httpx.HTTPStatusError as e:
        logger.error(f"{service_name} service HTTP error: {e.response.status_code}")
        record_service_failure(service_name)
    except Exception as e:
        logger.error(f"{service_name} service unexpected error: {str(e)}")
        record_service_failure(service_name)
    
    return None

# Health check endpoint
@app.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """Comprehensive health check for all services"""
    services_health = {}
    
    # Check all services
    for service_name in SERVICES.keys():
        health_data = await call_service(service_name, "health")
        
        services_health[service_name] = {
            "status": "healthy" if health_data else "unhealthy",
            "circuit_breaker": {
                "open": circuit_breaker[service_name]["open"],
                "failures": circuit_breaker[service_name]["failures"]
            },
            "last_response": health_data
        }
    
    # Overall system status
    all_healthy = all(service["status"] == "healthy" for service in services_health.values())
    
    return HealthCheckResponse(
        status="healthy" if all_healthy else "degraded",
        services=services_health,
        timestamp=datetime.now().isoformat()
    )

# Main query endpoint - calls RAG service which orchestrates everything
@app.post("/api/query")
async def process_query(request: QueryRequest):
    """Main query endpoint that routes through RAG service"""
    try:
        logger.info(f"Gateway received query: {request.query}")
        
        # Call RAG service which will handle hospital and insurance integration
        rag_response = await call_service("rag", "query", "POST", request.dict())
        
        if rag_response:
            logger.info("Successfully processed query through RAG service")
            return {
                "status": "success",
                "data": rag_response,
                "timestamp": datetime.now().isoformat(),
                "gateway": "main"
            }
        else:
            # Fallback when RAG service is down
            logger.warning("RAG service unavailable, providing fallback response")
            return {
                "status": "degraded",
                "data": {
                    "answer": "Our intelligent query system is temporarily unavailable. You can still access individual services through the direct search options.",
                    "confidence": 0.1,
                    "sources": {"error": "RAG service unavailable"}
                },
                "timestamp": datetime.now().isoformat(),
                "gateway": "main"
            }
            
    except Exception as e:
        logger.error(f"Gateway query processing error: {str(e)}")
        return {
            "status": "error",
            "data": {
                "answer": "I'm experiencing technical difficulties. Please try again later.",
                "confidence": 0.0,
                "sources": {"error": str(e)}
            },
            "timestamp": datetime.now().isoformat(),
            "gateway": "main"
        }

# Direct service endpoints for fallback
@app.post("/api/hospital/search")
async def search_hospitals_direct(request: QueryRequest):
    """Direct hospital search when RAG is unavailable"""
    result = await call_service("hospital", "search", "POST", request.dict())
    
    if result:
        return {"status": "success", "data": result}
    else:
        return {
            "status": "error", 
            "data": {"message": "Hospital service is currently unavailable"}
        }

@app.post("/api/insurance/search")
async def search_insurance_direct(request: QueryRequest):
    """Direct insurance search when RAG is unavailable"""
    result = await call_service("insurance", "search", "POST", request.dict())
    
    if result:
        return {"status": "success", "data": result}
    else:
        return {
            "status": "error",
            "data": {"message": "Insurance service is currently unavailable"}
        }

# Service status endpoint
@app.get("/api/status")
async def get_system_status():
    """Get detailed system status"""
    return {
        "gateway": "healthy",
        "timestamp": datetime.now().isoformat(),
        "circuit_breakers": circuit_breaker,
        "services": SERVICES
    }

# Reset circuit breakers endpoint (for admin use)
@app.post("/api/admin/reset-breakers")
async def reset_circuit_breakers():
    """Reset all circuit breakers"""
    for service_name in circuit_breaker:
        circuit_breaker[service_name] = {
            "failures": 0,
            "last_failure": None,
            "open": False
        }
    
    return {"message": "All circuit breakers reset", "timestamp": datetime.now().isoformat()}

# Serve static files (for frontend)
# Uncomment if you have a static frontend
# app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "service": "Healthcare Gateway",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "main_query": "/api/query",
            "health_check": "/health",
            "status": "/api/status",
            "direct_hospital": "/api/hospital/search",
            "direct_insurance": "/api/insurance/search"
        },
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )