from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager

from .config import settings
from .core.middleware import InputSanitizationMiddleware, RequestLoggingMiddleware, SecurityHeadersMiddleware
from .core.rate_limit import limiter
from .core.realtime import analysis_ws_manager
from .routers import auth, datasets, analysis, reports, ai_swarm

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
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# Middlewares
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(InputSanitizationMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

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
async def health_check(request: Request):
    return {"status": "ok", "environment": settings.ENVIRONMENT}

@app.websocket("/ws/analysis/{analysis_id}")
async def websocket_endpoint(websocket: WebSocket, analysis_id: str):
    await analysis_ws_manager.connect(analysis_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await analysis_ws_manager.disconnect(analysis_id, websocket)
