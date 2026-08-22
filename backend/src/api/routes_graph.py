"""API routes for Phase 8 Product Knowledge Graph.

Exposes endpoints for querying product relationship edges and triggering graph analysis.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException

from ..agents.graph_agent import GraphAgent
from ..db.store import store
from ..models.schemas import ProductRelationship
from ..utils.logging import get_logger

logger = get_logger("routes_graph")
router = APIRouter(prefix="/api", tags=["graph"])


@router.get("/graph/relationships", response_model=List[ProductRelationship])
async def list_relationships(sku: Optional[str] = None):
    """List product knowledge graph relationships, optionally filtered by SKU."""
    return store.list_product_relationships(sku=sku)


@router.get("/products/{sku}/relationships", response_model=List[ProductRelationship])
async def get_product_relationships(sku: str):
    """Retrieve product knowledge graph relationships for a specific SKU."""
    return store.list_product_relationships(sku=sku)


@router.post("/graph/analyze", response_model=List[ProductRelationship])
async def trigger_graph_analysis():
    """Trigger GraphAgent analysis across all validated catalog records."""
    agent = GraphAgent()
    return await agent.analyze_catalog()
