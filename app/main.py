"""OptiMark - FastAPI main application."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import engine, Base
from app.routers import auth, exams, scan, subscription, admin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: create tables on startup."""
    logger.info("Starting OptiMark API")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    yield
    await engine.dispose()
    logger.info("OptiMark API shutdown complete")


app = FastAPI(
    title="OptiMark",
    description="Automated OMR Grading System API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS - required for frontend to call API
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions. Preserve HTTPException, log and return 500 for others."""
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please try again."},
    )

# Mount uploads for serving scanned images (optional)
upload_path = Path(settings.UPLOAD_DIR)
upload_path.mkdir(parents=True, exist_ok=True)
app.mount(f"/{settings.UPLOAD_DIR}", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

# Include routers (mounted at /api for frontend compatibility)
app.include_router(auth.router, prefix="/api")
app.include_router(exams.router, prefix="/api")
app.include_router(scan.router, prefix="/api")
app.include_router(subscription.router, prefix="/api")
app.include_router(admin.router, prefix="/api")


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"message": "OptiMark OMR Grading API", "status": "ok"}
