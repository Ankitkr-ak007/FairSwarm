from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager
from typing import Dict

from .config import settings
from .routers import auth, datasets, analysis, reports, ai_swarm

limiter = Limiter(key_func=get_remote_address, default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"])

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting up FairSwarm Backend...")
    yield
    print("Shutting down FairSwarm Backend...")

app = FastAPI(
    title="FairSwarm API",
    description="Swarm Intelligence AI Bias Detection Platform",
    version="1.0.0",
    lifespan=lifespan
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Middlewares
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

@app.middleware("http")
async def jwt_auth_middleware(request: Request, call_next):
    public_paths = ["/docs", "/openapi.json", "/api/v1/auth/login", "/api/v1/auth/register", "/health"]
    if request.url.path in public_paths or request.url.path.startswith("/ws/"):
        return await call_next(request)
    
    auth_header = request.headers.get("Authorization")
    if not auth_header and request.url.path.startswith("/api/v1/"):
        pass # The Depends(get_current_user) will handle granular 401s
    
    response = await call_next(request)
    return response

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred. Please try again later."},
    )

# Routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(datasets.router, prefix="/api/v1/datasets", tags=["Datasets"])
app.include_router(analysis.router, prefix="/api/v1/analysis", tags=["Analysis"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["Reports"])
app.include_router(ai_swarm.router, prefix="/api/v1/ai", tags=["AI Swarm"])

@app.get("/health", tags=["Health"])
@limiter.limit("5/minute")
async def health_check(request: Request):
    return {"status": "ok", "environment": settings.ENVIRONMENT}

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, analysis_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[analysis_id] = websocket

    def disconnect(self, analysis_id: str):
        if analysis_id in self.active_connections:
            del self.active_connections[analysis_id]

    async def send_personal_message(self, message: dict, analysis_id: str):
        if analysis_id in self.active_connections:
            await self.active_connections[analysis_id].send_json(message)

manager = ConnectionManager()

@app.websocket("/ws/analysis/{analysis_id}")
async def websocket_endpoint(websocket: WebSocket, analysis_id: str):
    await manager.connect(analysis_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(analysis_id)
