"""Ingestion API routes — single-source and bulk CSV upload endpoints."""

import asyncio
import csv
import io
import json
from uuid import UUID, uuid4
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse

from ..models.api import IngestRequest, IngestResponse
from ..models.product_record import SourceType, TrustTier
from ..models.unihack_schema import UNIHACK_DELIVERY_COLUMNS, map_product_fields_to_unihack_row
from ..services.csv_processor import CSVProcessor
from ..orchestration.pipeline import run_pipeline
from ..db.store import store
from ..utils.logging import get_logger

logger = get_logger("routes_ingest")

router = APIRouter(prefix="/api", tags=["ingestion"])

# Cap concurrent pipeline runs to prevent OOM when processing bulk CSV.
# Each pipeline now runs 3 multi-phase LLM sub-calls (Phases 2/3/4) plus
# enrichment — running all 24 rows in parallel would exhaust memory.
_PIPELINE_SEM = asyncio.Semaphore(3)


import base64
import pandas as pd

def extract_dataset_rows(content: str, filename: str = "") -> list[dict]:
    """Parse content as multi-row Excel (.xlsx/.xls) or CSV data.
    
    Returns a list of dicts (one dict per row) if multi-row dataset, else [].
    """
    filename_lower = (filename or "").lower()
    content_strip = (content or "").strip()
    
    # 1. Try Base64 Excel / Binary parsing
    if filename_lower.endswith((".xlsx", ".xls")) or content_strip.startswith("UEsDB") or "base64" in content_strip[:60]:
        try:
            b64_str = content_strip.split(",")[-1] if "," in content_strip else content_strip
            raw_bytes = base64.b64decode(b64_str)
            df = pd.read_excel(io.BytesIO(raw_bytes))
            df = df.where(pd.notnull(df), None)
            records = df.to_dict(orient="records")
            if len(records) > 0:
                logger.info("Excel dataset parser: extracted %d rows from file '%s'", len(records), filename)
                return records
        except Exception as err:
            logger.warning("Base64 Excel parse attempt: %s", err)
            
    # 2. Try CSV text parsing
    if ("," in content_strip or "\t" in content_strip) and ("\n" in content_strip or ";" in content_strip or "part" in content_strip.lower()):
        try:
            reader = list(csv.DictReader(io.StringIO(content_strip)))
            if len(reader) > 0:
                logger.info("CSV text dataset parser: extracted %d rows from text content", len(reader))
                return reader
        except Exception as err:
            logger.warning("CSV text parse attempt: %s", err)

    return []


async def _process_remaining_dataset_rows(
    rows: list[dict],
    category: str | None,
    filename: str | None,
    trust_tier: TrustTier,
    user_id: str = "default_user",
) -> None:
    """Process remaining dataset rows (1..N) asynchronously in background."""
    logger.info("Background dataset processing started for %d remaining rows (user=%s)", len(rows), user_id)
    for i, row_dict in enumerate(rows):
        if not row_dict or not any(row_dict.values()):
            continue
        row_json = json.dumps(row_dict, ensure_ascii=False)
        try:
            async with _PIPELINE_SEM:
                await run_pipeline(
                    source_type=SourceType.CSV,
                    content=row_json,
                    category=category,
                    filename=filename,
                    trust_tier=trust_tier,
                    user_id=user_id,
                )
            logger.info("Background dataset row %d/%d completed", i + 1, len(rows))
        except Exception as row_err:
            logger.warning("Background dataset row %d/%d error: %s", i + 1, len(rows), row_err)
        await asyncio.sleep(0.5)


@router.post("/ingest", response_model=IngestResponse)
async def ingest_source(
    request: IngestRequest,
    background_tasks: BackgroundTasks,
    x_user_id: Optional[str] = Header(None, alias="x-user-id"),
) -> IngestResponse:
    """Ingest a single source or multi-row dataset (CSV/Excel) into product records.

    Accepts URLs, base64 PDF/Excel files, or raw CSV text.
    For multi-row datasets, processes Row 0 immediately (< 2s) and queues remaining
    items to process in background without blocking the UI.
    """
    run_id = uuid4()

    trust_tier = TrustTier.MARKETPLACE
    if request.trust_tier is not None:
        try:
            trust_tier = TrustTier(request.trust_tier)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid trust_tier: {request.trust_tier}. Use 1 (manufacturer), 2 (distributor), or 3 (marketplace).",
            )

    active_user = x_user_id or "default_user"

    try:
        # Check if content is a multi-row Excel (.xlsx) or CSV dataset (e.g. 1000 items)
        dataset_rows = extract_dataset_rows(request.content, request.filename or "")
        if len(dataset_rows) > 0:
            logger.info("Dataset detected (%s): processing Row 0 immediately, %d total rows", request.filename, len(dataset_rows))
            # Process Row 0 immediately for instant UI response
            row0_dict = dataset_rows[0]
            row0_json = json.dumps(row0_dict, ensure_ascii=False)
            first_prod = await run_pipeline(
                source_type=SourceType.CSV,
                content=row0_json,
                category=request.category,
                filename=request.filename,
                trust_tier=trust_tier,
                user_id=active_user,
            )

            # Queue remaining rows in background
            if len(dataset_rows) > 1:
                background_tasks.add_task(
                    _process_remaining_dataset_rows,
                    dataset_rows[1:],
                    request.category,
                    request.filename,
                    trust_tier,
                    active_user,
                )

            remaining_count = len(dataset_rows) - 1
            msg = (
                f"Successfully processed '{first_prod.name}' — "
                f"{len(first_prod.fields)} fields extracted ({first_prod.confidence_overall}% confidence)."
            )
            if remaining_count > 0:
                msg += f" Queued {remaining_count} remaining items to ingest in background."

            return IngestResponse(
                run_id=run_id,
                status="completed",
                product_id=first_prod.id,
                message=msg,
            )



        product = await run_pipeline(
            source_type=request.source_type,
            content=request.content,
            category=request.category,
            filename=request.filename,
            trust_tier=trust_tier,
            user_id=active_user,
        )

        return IngestResponse(
            run_id=run_id,
            status="completed",
            product_id=product.id,
            message=(
                f"Successfully processed '{product.name}' — "
                f"{len(product.fields)} fields extracted, "
                f"overall confidence {product.confidence_overall}%"
            ),
        )


    except ValueError as e:
        return IngestResponse(run_id=run_id, status="failed", message=str(e))
    except Exception as e:
        return IngestResponse(run_id=run_id, status="failed", message=f"Pipeline error: {str(e)}")


# ─── Bulk CSV upload ──────────────────────────────────────────────────────────

# In-memory job tracker { job_id: { total, done, failed, product_ids[], failed_rows[] } }
_bulk_jobs: dict[str, dict] = {}

# Priority-ordered column name patterns for generic part-number detection.
# Case-insensitive. Works for any CSV column layout.
_PART_NUM_COL_PATTERNS: tuple[str, ...] = (
    "mfg_part_num", "part_number", "manufacturer_part_number",
    "model_number", "sku", "item_number", "item_id",
    "catalog_number", "vendor_part_number", "supplier_part_number",
)


def _extract_part_num_from_row(row_dict: dict) -> str:
    """Dynamically extract the canonical part-number from any CSV row dict.

    Checks column names case-insensitively in priority order.
    Falls back to the first non-empty cell in the row.
    Works for any CSV format — no column names are hardcoded.
    """
    lower_map = {k.lower().strip(): v for k, v in row_dict.items()}
    for pattern in _PART_NUM_COL_PATTERNS:
        val = lower_map.get(pattern)
        if val and str(val).strip():
            return str(val).strip()
    # Fallback: first non-empty value in insertion order
    for v in row_dict.values():
        if v and str(v).strip():
            return str(v).strip()
    return ""


@router.post("/ingest/bulk-csv")
async def bulk_ingest_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    """Upload a CSV file and process each row through the full pipeline.

    The CSV must contain at least one of:
      - A column named 'Part_Desc', 'PART_NUMBER', or 'Mfg_Part_Num'
      - Any human-readable product description column

    Processing runs in the background. Poll /api/ingest/bulk-csv/{job_id}
    for progress, then GET /api/export/csv to download the enriched output.
    """
    raw_bytes = await file.read()
    try:
        text = raw_bytes.decode("utf-8-sig")  # strip BOM if present
    except UnicodeDecodeError:
        text = raw_bytes.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise HTTPException(status_code=400, detail="CSV file is empty or has no data rows.")

    job_id = str(uuid4())
    _bulk_jobs[job_id] = {
        "total": len(rows),
        "done": 0,
        "failed": 0,
        "product_ids": [],
        "input_part_numbers": {_extract_part_num_from_row(row) for row in rows if _extract_part_num_from_row(row)},
        "row_statuses": [],
        # failed_rows: list of {"part_num": str, "reason": str}
        # These become blank passthrough rows in the export CSV.
        "failed_rows": [],
        "status": "running",
    }

    background_tasks.add_task(_process_bulk_rows, job_id, rows)

    logger.info("bulk_ingest: started job %s — %d rows", job_id, len(rows))
    return {
        "job_id": job_id,
        "total_rows": len(rows),
        "status": "running",
        "message": f"Processing {len(rows)} rows in the background.",
        "poll_url": f"/api/ingest/bulk-csv/{job_id}",
        "download_url": "/api/export/csv",
    }


@router.get("/ingest/bulk-csv/{job_id}")
async def bulk_ingest_status(job_id: str):
    """Poll the status of a bulk CSV ingestion job."""
    job = _bulk_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    pct = round(job["done"] / job["total"] * 100) if job["total"] else 0
    return {
        "job_id": job_id,
        "status": job["status"],
        "total": job["total"],
        "done": job["done"],
        "failed": job["failed"],
        "progress_pct": pct,
        "product_ids": job["product_ids"][-10:],  # last 10 for preview
        "row_statuses": job.get("row_statuses", []),
        "sanity_issues": job.get("sanity_issues", []),
    }


@router.post("/ingest/bulk-csv/{job_id}/download")
async def bulk_ingest_download(job_id: str):
    """Download the enriched CSV for a completed bulk job.

    Successfully processed rows are emitted with all enriched fields.
    Failed rows (binary content, blank description, extraction failure)
    are emitted as blank passthrough rows: the original part number is
    preserved in Mfg_Part_Num / PART_NUMBER; all enriched columns are
    empty or N/A so no fabricated data appears.
    """
    job = _bulk_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    if job["status"] != "completed":
        raise HTTPException(status_code=202, detail=f"Job still running — {job['done']}/{job['total']} done.")

    # ── Successful products ──────────────────────────────────────────
    product_ids: list[UUID] = [UUID(pid) for pid in job["product_ids"]]
    products = [await store.get_product(pid) for pid in product_ids]
    products = [p for p in products if p]

    # Preserve job order and duplicate input rows: one delivery row per input row.
    # Deduplication across uploads belongs in review tooling, never in a job export.
    delivery_products = products

    out = io.StringIO()
    writer = csv.DictWriter(
        out, fieldnames=UNIHACK_DELIVERY_COLUMNS,
        extrasaction="ignore", lineterminator="\r\n"
    )
    writer.writeheader()
    emitted_part_numbers: set[str] = set()
    delivery_rows: list[dict[str, str]] = []

    for product in delivery_products:
        row = map_product_fields_to_unihack_row(product.fields, title=product.name, sku="")
        if row.get("Mfg_Part_Num"):
            emitted_part_numbers.add(row["Mfg_Part_Num"].strip())
        delivery_rows.append(row)
        writer.writerow(row)

    # ── Failed/blank passthrough rows ───────────────────────────────
    # Rows that couldn't be processed (binary content, blank desc, etc.)
    # appear with their original part number preserved and all enriched
    # columns blank — never fabricated placeholder text.
    for failed in job.get("failed_rows", []):
        blank_row = {col: "" for col in UNIHACK_DELIVERY_COLUMNS}
        pn = str(failed.get("part_num", "")).strip()
        if pn:
            blank_row["Mfg_Part_Num"] = pn
            blank_row["MANUFACTURER_PART_NUMBER"] = pn
            emitted_part_numbers.add(pn)
        delivery_rows.append(blank_row)
        writer.writerow(blank_row)

    sanity_issues = CSVProcessor._delivery_sanity_issues(
        job.get("input_part_numbers", set()), delivery_rows, job.get("row_statuses", [])
    )
    job["sanity_issues"] = sanity_issues
    blocking_issues = [issue for issue in sanity_issues if issue.startswith("out-of-scope") or issue.startswith("coverage mismatch")]
    if blocking_issues:
        raise HTTPException(status_code=500, detail="Delivery validation failed: " + "; ".join(blocking_issues))

    csv_bytes = "\ufeff".encode("utf-8") + out.getvalue().encode("utf-8")
    total_rows = len(delivery_products) + len(job.get("failed_rows", []))
    filename = f"Unihack_Delivery_Format_{total_rows}_items.csv"
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ─── Background worker ────────────────────────────────────────────────────────

async def _process_bulk_rows(job_id: str, rows: list[dict]) -> None:
    """Process each CSV row through the full pipeline (runs in background).

    Each row dict is JSON-serialized and passed as the content string.
    The ExtractionAgent detects JSON dicts and uses deterministic mapping
    instead of LLM parsing, preserving exact CSV values.

    On failure (binary content, empty/garbled description, extraction error):
    - The row is NOT silently dropped.
    - Its canonical part number (found generically from whichever column
      holds it) is recorded in failed_rows.
    - The download endpoint emits a blank passthrough row so the output
      has one row per input row, with failed rows showing only the part
      number and all enriched columns empty.
    """
    job = _bulk_jobs[job_id]

    for i, row_dict in enumerate(rows):
        # Pass the raw CSV row as a JSON-encoded dict so the ExtractionAgent
        # can deterministically map columns -> ProductFields without LLM.
        row_json = json.dumps(row_dict, ensure_ascii=False)

        try:
            async with _PIPELINE_SEM:
                product = await run_pipeline(
                    source_type=SourceType.CSV,
                    content=row_json,
                    category=None,
                )
            job["done"] += 1
            job["product_ids"].append(str(product.id))
            job["row_statuses"].append({"row_number": i + 1, "status": "enriched", "product_id": str(product.id)})
            logger.info(
                "bulk_ingest[%s]: row %d/%d — '%s' (%d fields)",
                job_id, i + 1, job["total"], product.name, len(product.fields),
            )
        except Exception as e:
            job["failed"] += 1
            job["done"] += 1
            # Record a blank passthrough: extract the part number from the
            # original row generically (no hardcoded column names).
            part_num = _extract_part_num_from_row(row_dict)
            job["failed_rows"].append({"part_num": part_num, "reason": str(e)})
            job["row_statuses"].append({"row_number": i + 1, "status": "skipped_unprocessable", "reason": str(e)})
            logger.warning(
                "bulk_ingest[%s]: row %d/%d SKIPPED — part='%s' reason=%s",
                job_id, i + 1, job["total"], part_num, e,
            )

        # Delay between rows: each now makes 3+ LLM sub-calls (multi-phase
        # extraction), so 2 s respects API rate limits and reduces memory pressure.
        if i < len(rows) - 1:
            await asyncio.sleep(2.0)

    job["status"] = "completed"
    logger.info(
        "bulk_ingest[%s]: completed — %d/%d succeeded, %d failed",
        job_id, job["total"] - job["failed"], job["total"], job["failed"],
    )
