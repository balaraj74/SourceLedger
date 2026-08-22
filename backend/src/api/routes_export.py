"""Export routes for SourceLedger catalog data.

Generates downloadable CSV files matching Unihack_ Expected Output - Delivery Format.csv.

Export logic is fully generic:
- Works for any product domain and any CSV column layout
- Deduplicates by canonical part number (mfg_part_num field), keeping the
  highest-confidence record when duplicates exist
- Filters stale/failed records by detecting products that have no valid
  part-number key AND whose name looks like an internal ID (UUID fragment,
  purely numeric, etc.) — without hardcoding any specific product names
- Unknown fields default to N/A, not fabricated placeholder text
"""

import csv
import io
import re
from uuid import UUID
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..models.unihack_schema import UNIHACK_DELIVERY_COLUMNS, map_product_fields_to_unihack_row
from ..db.store import store
from ..utils.logging import get_logger

logger = get_logger("routes_export")

router = APIRouter(prefix="/api", tags=["export"])

# ── Part-number column priority (generic, case-insensitive) ─────────────────
# Used to recover the canonical part-number key from a product's fields.
_PART_NUM_FIELD_PRIORITY: tuple[str, ...] = (
    "mfg_part_num", "part_number", "manufacturer_part_number",
    "model_number", "sku", "item_number", "item_id",
    "catalog_number", "vendor_part_number", "supplier_part_number",
)

# Regex: detects strings that look like internal UUIDs or UUID fragments
# (e.g. "239148c8", "4fb21548-99e7-4938"). These are stale pipeline artifacts,
# not real product names. Generic — not tied to any specific product domain.
_UUID_LIKE_RE = re.compile(
    r"^[0-9a-f]{8}(-[0-9a-f]{4}){0,4}$", re.IGNORECASE
)

# Failure-indicator phrases in product names — generic extraction failures.
# These are pipeline error strings, not domain-specific product language.
_FAILURE_INDICATORS: tuple[str, ...] = (
    "not found in source text",
    "no product found",
    "no match found",
    "no data found",
    "extraction failed",
    "could not extract",
)


def _is_stale_or_failed_product(prod) -> bool:
    """Return True if this product record should be excluded from export.

    A record is stale/failed when:
    1. Its name contains a known pipeline failure phrase (e.g. "No Product
       Found in Source Text" — these are exact pipeline error strings, not
       domain language so filtering on them is safe), OR
    2. Its name looks like a bare UUID fragment AND it has no valid
       part-number field — which means the pipeline used an internal ID
       as the product name (a known artifact from old failed runs).

    This check is generic — it does not depend on any specific product names,
    part numbers, or categories from the user's data.
    """
    name = (prod.name or "").strip()
    name_lower = name.lower()

    # Empty name = always stale
    if not name_lower:
        return True

    # Pipeline error phrases in the name
    if any(ind in name_lower for ind in _FAILURE_INDICATORS):
        return True

    # UUID-looking name with no recognisable part-number field
    if _UUID_LIKE_RE.match(name):
        has_part_num = any(
            f.name in _PART_NUM_FIELD_PRIORITY and f.value and str(f.value).strip()
            for f in prod.fields
        )
        if not has_part_num:
            return True

    return False


def _get_part_num(prod) -> str:
    """Extract the canonical part-number from a ProductRecord generically.

    Checks prod.mfg_part_num first (set by the pipeline), then falls back
    to scanning fields in priority order. Works for any field layout.
    """
    if prod.mfg_part_num and prod.mfg_part_num.strip():
        return prod.mfg_part_num.strip()
    for key in _PART_NUM_FIELD_PRIORITY:
        field = next(
            (f for f in prod.fields if f.name == key and f.value and str(f.value).strip()),
            None,
        )
        if field:
            return str(field.value).strip()
    return ""


def _dedup_products(products: list) -> list:
    """Deduplicate a list of ProductRecords by canonical part number.

    When multiple records share the same part number (same row uploaded
    multiple times, or the same Mfg_Part_Num appears in several input rows),
    keep only the record with the highest confidence_overall score.

    Records with no identifiable part number are passed through unchanged
    (no deduplication key available).

    Generic — works for any product domain and any column layout.
    """
    seen: dict[str, object] = {}   # part_num -> best ProductRecord
    no_key: list = []

    for prod in products:
        key = _get_part_num(prod)
        if not key:
            no_key.append(prod)
            continue
        existing = seen.get(key)
        if existing is None or prod.confidence_overall > existing.confidence_overall:
            seen[key] = prod

    return list(seen.values()) + no_key


@router.get("/export/csv")
async def export_all_products_csv():
    """Export all valid ledgered products in the 252-column Unihack Delivery CSV format.

    Deduplicates by canonical part number (keeps highest-confidence record).
    Filters stale/failed records generically without hardcoding product names.
    Unknown fields are N/A, not fabricated placeholder text.
    """
    all_products = await store.list_products()

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=UNIHACK_DELIVERY_COLUMNS)
    writer.writeheader()

    if not all_products:
        output.seek(0)
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode("utf-8-sig")),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=Unihack_Delivery_Format.csv"},
        )

    # 1. Filter stale / failed records
    valid_products = []
    skipped_count = 0
    for prod in all_products:
        if _is_stale_or_failed_product(prod):
            logger.warning(
                "Export: SKIPPING stale/failed product '%s' (id=%s)",
                (prod.name or "")[:60], str(prod.id)[:8],
            )
            skipped_count += 1
        else:
            valid_products.append(prod)

    # 2. Deduplicate by part number
    deduped = _dedup_products(valid_products)
    dedup_removed = len(valid_products) - len(deduped)
    if dedup_removed:
        logger.info("Export: deduplicated %d duplicate part-number records", dedup_removed)

    # 3. Emit rows
    for prod in deduped:
        sku = _get_part_num(prod)
        row = map_product_fields_to_unihack_row(prod.fields, title=prod.name, sku=sku)
        writer.writerow(row)

    output.seek(0)
    exported_count = len(deduped)
    logger.info(
        "Export: %d products exported, %d skipped (stale/failed), %d deduped",
        exported_count, skipped_count, dedup_removed,
    )

    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=Unihack_Delivery_Format_{exported_count}_items.csv"
        },
    )


@router.get("/products/{product_id}/export-csv")
async def export_single_product_csv(product_id: UUID):
    """Export a single product record in Unihack Delivery CSV format."""
    product = await store.get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=UNIHACK_DELIVERY_COLUMNS)
    writer.writeheader()

    sku = _get_part_num(product)
    row = map_product_fields_to_unihack_row(product.fields, title=product.name, sku=sku)
    writer.writerow(row)

    output.seek(0)
    safe_name = "".join(c if c.isalnum() else "_" for c in (product.name or "product")[:30])

    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=Unihack_Delivery_{safe_name}.csv"},
    )


@router.get("/export/jsonld")
async def export_catalog_jsonld():
    """Export all validated products in Schema.org/Product JSON-LD format (Phase 12c)."""
    from ..services.jsonld_exporter import export_catalog_to_jsonld
    products = await store.list_products()
    valid_prods = [p for p in products if p.confidence_overall >= 50]
    jsonld_data = export_catalog_to_jsonld(valid_prods)
    return jsonld_data


@router.get("/products/{product_id}/export/jsonld")
async def export_single_product_jsonld(product_id: UUID):
    """Export a single product in Schema.org/Product JSON-LD format (Phase 12c)."""
    from ..services.jsonld_exporter import export_product_to_jsonld
    product = await store.get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return export_product_to_jsonld(product)
