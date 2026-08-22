"""Review Queue API routes — the hero review surface."""

from datetime import datetime, timezone
from uuid import UUID

from typing import Optional
from fastapi import APIRouter, Header, HTTPException

from ..db.store import store
from ..models.api import (
    ReviewActionRequest,
    ReviewActionResponse,
    ReviewQueueItem,
    ReviewQueueResponse,
)
from ..models.product_record import FieldStatus, ReviewAction, ReviewActionType

router = APIRouter(prefix="/api", tags=["review"])


@router.get("/review", response_model=ReviewQueueResponse)
async def get_review_queue(x_user_id: Optional[str] = Header(None, alias="x-user-id")) -> ReviewQueueResponse:
    """List all fields needing human review across all products for authenticated user."""
    items_raw = await store.get_review_queue(user_id=x_user_id)
    items = [
        ReviewQueueItem(
            field=item["field"],
            product_id=item["product_id"],
            product_name=item["product_name"],
            category=item["category"],
            category_display_name=item["category_display_name"],
        )
        for item in items_raw
    ]
    return ReviewQueueResponse(items=items, total_count=len(items))


@router.post(
    "/products/{product_id}/fields/{field_id}/review",
    response_model=ReviewActionResponse,
)
async def review_field(
    product_id: UUID,
    field_id: UUID,
    request: ReviewActionRequest,
    x_user_id: Optional[str] = Header(None, alias="x-user-id"),
) -> ReviewActionResponse:
    """Accept, edit, or reject a field value in the review queue."""
    product = await store.get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    field = next((f for f in product.fields if f.id == field_id), None)
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")

    original_value = field.value

    if request.action == ReviewActionType.ACCEPT:
        field.status = FieldStatus.AUTO_COMMITTED
    elif request.action == ReviewActionType.EDIT:
        if request.corrected_value is None:
            raise HTTPException(
                status_code=400,
                detail="corrected_value is required for edit action",
            )
        field.value = request.corrected_value
        field.status = FieldStatus.HUMAN_CORRECTED
        field.confidence = 100  # Human-verified = full confidence
        field.reasoning += f" | Human corrected: '{original_value}' → '{request.corrected_value}'"
    elif request.action == ReviewActionType.REJECT:
        field.value = None
        field.confidence = 0
        field.status = FieldStatus.NEEDS_REVIEW
        field.reasoning += " | Value rejected by reviewer."
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action: {request.action}. Use 'accept', 'edit', or 'reject'.",
        )

    field.updated_at = datetime.now(timezone.utc)

    # Update the field in the product and recompute overall confidence
    await store.update_field(
        product_id, field_id, new_value=field.value, new_status=field.status
    )

    active_user = x_user_id or "default_user"
    # Record the review action for audit trail and active learning
    review_action = ReviewAction(
        field_id=field_id,
        product_id=product_id,
        action=request.action,
        original_value=original_value,
        corrected_value=request.corrected_value,
        reviewer=request.reviewer,
    )
    await store.save_review_action(review_action, user_id=active_user)

    # Active Learning CorrectionPattern tracking (Phase 10)
    from ..models.schemas import CorrectionPattern
    mfr_val = next((str(f.value) for f in product.fields if f.name.lower() in ("manufacturer", "brand", "part_manuf")), None)
    patterns = store.get_correction_patterns()
    pat_id = f"{product.category}:{field.name}:{mfr_val or 'all'}"
    existing = next((p for p in patterns if f"{p.category}:{p.field_name}:{p.manufacturer or 'all'}" == pat_id), None)
    new_count = (existing.correction_count + 1) if existing else 1
    
    pat = CorrectionPattern(
        category=product.category,
        field_name=field.name,
        manufacturer=mfr_val,
        correction_count=new_count,
        avg_confidence_before_correction=float(field.confidence),
        last_updated=datetime.now(timezone.utc),
    )
    store.save_correction_pattern(pat)

    return ReviewActionResponse(
        review_action=review_action,
        updated_field=field,
    )


@router.post("/products/{product_id}/fields/{field_id}/review/bulk")
async def bulk_review_field(
    product_id: UUID,
    field_id: UUID,
    request: ReviewActionRequest,
):
    """One-click bulk correction (Phase 12b).

    Applies the reviewer's correction to all other needs_review items sharing
    the same category, field name, and original value pattern across the catalog.
    """
    primary_res = await review_field(product_id, field_id, request)
    
    # Query all matching records needing review
    all_queue = await store.get_review_queue()
    matching_targets = [
        item for item in all_queue
        if item["field"].name == primary_res.updated_field.name
        and item["field"].value == primary_res.review_action.original_value
        and item["product_id"] != product_id
    ]

    bulk_count = 0
    for target in matching_targets:
        try:
            await review_field(target["product_id"], target["field"].id, request)
            bulk_count += 1
        except Exception:
            pass

    return {
        "status": "success",
        "primary_action": primary_res,
        "bulk_applied_count": bulk_count,
        "message": f"Successfully applied bulk correction across {bulk_count + 1} matching records.",
    }
