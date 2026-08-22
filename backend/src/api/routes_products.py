"""Product record API routes."""

from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Header, HTTPException

from ..db.store import store
from ..models.api import ProductDetailResponse, ProductListResponse, ProductSummary
from ..models.product_record import FieldStatus
from ..models.schemas import CATEGORY_REGISTRY, get_category_schema

router = APIRouter(prefix="/api", tags=["products"])


@router.get("/products", response_model=ProductListResponse)
async def list_products(x_user_id: Optional[str] = Header(None, alias="x-user-id")) -> ProductListResponse:
    """List all product records with summary info for the authenticated user."""
    products = await store.list_products(user_id=x_user_id)
    summaries = []
    for p in products:
        schema = CATEGORY_REGISTRY.get(p.category)
        needs_review = sum(
            1 for f in p.fields if f.status == FieldStatus.NEEDS_REVIEW
        )
        auto_committed = sum(
            1 for f in p.fields if f.status == FieldStatus.AUTO_COMMITTED
        )
        summaries.append(
            ProductSummary(
                id=p.id,
                name=p.name,
                category=p.category,
                category_display_name=schema.display_name if schema else p.category,
                confidence_overall=p.confidence_overall,
                field_count=len(p.fields),
                needs_review_count=needs_review,
                auto_committed_count=auto_committed,
                created_at=p.created_at.isoformat(),
            )
        )
    return ProductListResponse(products=summaries, total_count=len(summaries))


@router.get("/products/{product_id}", response_model=ProductDetailResponse)
async def get_product(product_id: UUID) -> ProductDetailResponse:
    """Get full product record with all fields and provenance."""
    product = await store.get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Gather all sources used by this product
    sources = []
    for sid in product.source_ids:
        source = await store.get_source(sid)
        if source:
            sources.append(source)

    schema = get_category_schema(product.category)
    if not schema:
        # Fall back to first available schema for unknown/generic categories
        from ..models.schemas import CATEGORY_REGISTRY
        schema = next(iter(CATEGORY_REGISTRY.values()), None)
    if not schema:
        raise HTTPException(
            status_code=500, detail=f"No category schemas registered"
        )

    return ProductDetailResponse(
        product=product,
        sources=sources,
        category_schema=schema,
    )


@router.delete("/products")
async def clear_all_products() -> dict:
    """Clear all products, sources, and audit logs from store."""
    store.clear()
    return {"status": "success", "message": "All product catalog data cleared"}

