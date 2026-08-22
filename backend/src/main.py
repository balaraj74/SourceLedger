"""SourceLedger backend — FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes_conflicts import router as conflicts_router
from .api.routes_copilot import router as copilot_router
from .api.routes_dashboard import router as dashboard_router
from .api.routes_export import router as export_router
from .api.routes_fields import router as fields_router
from .api.routes_graph import router as graph_router
from .api.routes_ingest import router as ingest_router
from .api.routes_ocr import router as ocr_router
from .api.routes_products import router as products_router
from .api.routes_review import router as review_router

app = FastAPI(
    title="SourceLedger",
    description="AI-Powered Product Intelligence Engine — every product fact, ledgered back to its source.",
    version="0.1.0",
)

# CORS — allow the React frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


import asyncio

@app.on_event("startup")
async def startup_event():
    """Startup event — starts with clean catalog ready for live user ingestion."""
    pass

# Mount route modules
app.include_router(ingest_router)
app.include_router(products_router)
app.include_router(fields_router)
app.include_router(review_router)
app.include_router(dashboard_router)
app.include_router(export_router)
app.include_router(ocr_router)
app.include_router(conflicts_router)
app.include_router(graph_router)
app.include_router(copilot_router)


