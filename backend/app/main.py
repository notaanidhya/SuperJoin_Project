import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.stats import router as stats_router
from app.api.documents import router as documents_router
from app.api.facts import router as facts_router
from app.api.relationships import router as relationships_router
from app.api.showcase import router as showcase_router
from app.database import init_db

# Initialize database on startup
init_db("data/fact_layer.db")

app = FastAPI(
    title="Fact Knowledge Layer API",
    description="Automated Fact Extraction, Grounding, and Cross-Document Reasoning Knowledge Layer for Unstructured PDFs",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(stats_router)
app.include_router(documents_router)
app.include_router(facts_router)
app.include_router(relationships_router)
app.include_router(showcase_router)

# Static files for Inspection UI
static_dir = Path(__file__).resolve().parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/")
def serve_ui():
    """Serves the Inspection Dashboard UI."""
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {
        "message": "Fact Knowledge Layer API is running. Access interactive docs at /docs or /api/stats",
        "docs_url": "/docs"
    }

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "fact-knowledge-layer"}
