"""
UniResolve — Gen-AI Powered Unified Complaint Intelligence
Main FastAPI application
"""

import asyncio

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.services.cbs import get_customer_profile

from app.api.complaints import router as complaints_router
from app.api.complaints import limiter
from app.config import ALLOWED_ORIGINS
from app.services.store import get_store
from app.services.triage import get_triage_service

app = FastAPI(
    title="UniResolve API",
    description="Gen-AI Powered Unified Complaint Intelligence for Union Bank of India",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.state.limiter = limiter
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded. Please retry after a minute."})

app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(complaints_router)


async def _sla_monitor():
    while True:
        get_store().mark_sla_breaches()
        await asyncio.sleep(300)


@app.on_event("startup")
async def startup_tasks():
    from app.connectors.orchestrator import run_orchestrator
    asyncio.create_task(_sla_monitor())
    asyncio.create_task(run_orchestrator())


@app.get("/", tags=["health"])
async def root():
    return {
        "service": "UniResolve",
        "status": "running",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health", tags=["health"])
async def health():
    return {"status": "healthy", "model_ready": get_triage_service()._model_ready}


@app.post("/admin/seed")
async def reseed_demo():
    try:
        from app.seed import main as seed_main
        seed_main()
        return {"seeded": True, "message": "Demo data reset successfully."}
    except Exception as e:
        return {"seeded": False, "error": str(e)}


@app.get("/customers/{customer_id}", tags=["cbs"])
async def get_customer(customer_id: str):
    profile = get_customer_profile(customer_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Customer profile not found in CBS")
    return profile

