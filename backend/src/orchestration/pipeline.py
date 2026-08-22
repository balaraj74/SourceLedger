"""Pipeline orchestration — wires agents into the full extraction flow.

Connects: Ingestion → Extraction → Enrichment → Validation → Explainability.

Uses a simple sequential pipeline for the MVP. The architecture doc
specifies LangGraph for branching/human-in-the-loop routing, but
the sequential flow covers the must-build demo path. LangGraph
state machine can be layered on top without changing agent interfaces.
"""

import os
from uuid import uuid4

from ..agents.enrichment_agent import EnrichmentAgent
from ..agents.explainability_layer import ExplainabilityLayer
from ..agents.extraction_agent import ExtractionAgent
from ..agents.ingestion_agent import IngestionAgent
from ..agents.validation_agent import ValidationAgent
from ..db.store import store
from ..models.product_record import ProductRecord, SourceType, TrustTier
from ..services.dedup import check_duplicate
from ..utils.logging import get_logger, log_agent_step

logger = get_logger("Pipeline")

# Agent instances — reused across requests
ingestion_agent = IngestionAgent()
extraction_agent = ExtractionAgent()
enrichment_agent = EnrichmentAgent()
validation_agent = ValidationAgent()
explainability_layer = ExplainabilityLayer()


def _rotate_key() -> str | None:
    """Rotate to the next API key and set it in the environment.

    Imports the global key_rotator lazily to avoid circular imports at
    module load time. Every agent's _get_client() reads os.environ on each
    call so this change propagates immediately.

    Returns the selected key (or None if no keys are configured).
    """
    try:
        from ..agents.main import key_rotator  # noqa: PLC0415

        api_key = key_rotator.get_next_key()
        if api_key:
            os.environ["GOOGLE_API_KEY"] = api_key
            logger.info(
                "Pipeline key rotation: using key ...%s (%d/%d active)",
                api_key[-6:],
                key_rotator.active_keys_count,
                key_rotator.total_keys,
            )
        else:
            logger.warning(
                "Pipeline: all API keys exhausted — agents will run in demo mode"
            )
        return api_key
    except Exception as exc:
        logger.warning(
            "Pipeline: key rotation skipped (%s) — using current env key", exc
        )
        return None


async def run_pipeline(
    source_type: SourceType,
    content: str,
    category: str | None = None,
    filename: str | None = None,
    trust_tier: TrustTier = TrustTier.MARKETPLACE,
    user_id: str = "default_user",
) -> ProductRecord:
    """Run the full extraction pipeline on a single source.

    Steps:
    1. Ingest: normalize input → raw text + Source entity
    2. Check idempotency: skip if same content already processed
    3. Extract: raw text → structured fields via Gemini LLM
    4. Enrich: fill missing fields from secondary sources/defaults
    5. Validate: score confidence, route to auto-commit or review
    6. Annotate: ensure all fields have complete provenance
    7. Persist: save product record and source to store

    Each stage rotates to the next Google API key before calling Gemini,
    distributing load across the full key pool to avoid quota exhaustion.

    Returns the completed ProductRecord.
    """
    with log_agent_step(logger, "Pipeline", "full extraction run") as ctx:

        # ── Stage 1: Ingestion ────────────────────────────────────────
        _rotate_key()
        logger.info("=== Stage 1/5 — IngestionAgent: normalising source content ===")
        ingestion_result = await ingestion_agent.ingest(
            source_type=source_type,
            content=content,
            filename=filename,
            trust_tier=trust_tier,
        )
        logger.info(
            "Stage 1 complete: %d chars extracted from '%s'",
            len(ingestion_result.raw_text),
            ingestion_result.source.origin,
        )

        # ── Stage 2: Idempotency check ───────────────────────────────
        existing = await store.find_source_by_hash(
            ingestion_result.source.content_hash
        )
        if existing:
            logger.info(
                "Duplicate source detected (hash=%s) — checking for existing product",
                existing.content_hash[:12],
            )
            products = await store.list_products()
            for p in products:
                if existing.id in p.source_ids:
                    ctx["output_summary"] = (
                        f"duplicate source — returning existing product '{p.name}'"
                    )
                    return p

        # Save source record
        await store.save_source(ingestion_result.source, user_id=user_id)

        # ── Auto-detect category if not provided ──────────────────────
        if not category:
            if (filename and filename.endswith(".csv")) or (
                "\n" in ingestion_result.raw_text
                and "," in ingestion_result.raw_text.split("\n")[0]
            ):
                category = "generic"
            else:
                category = _detect_category(ingestion_result.raw_text)
        logger.info("Category: %s", category)

        # ── Stage 3: Extraction ───────────────────────────────────────
        _rotate_key()
        logger.info(
            "=== Stage 2/5 — ExtractionAgent: extracting fields for '%s' ===", category
        )
        extraction_result = await extraction_agent.extract(
            raw_text=ingestion_result.raw_text,
            category=category,
            source_id=ingestion_result.source.id,
        )
        logger.info(
            "Stage 2 complete: %d fields extracted for '%s'",
            len(extraction_result.fields),
            extraction_result.product_name,
        )

        # ── Circuit breaker: detect extraction failures ───────────────
        # If the extraction step produced a failure/not-found product name,
        # STOP the pipeline immediately. Do NOT pass to enrichment, which
        # would fabricate a full spec sheet on top of the failure string.
        _name_lower = extraction_result.product_name.lower().strip()
        _FAILURE_INDICATORS = [
            "not found",
            "no product found",
            "no match found",
            "no data found",
            "unknown product",
            "extracted product",
            "ingested product",
            "csv product",  # old fallback — kept for safety
        ]

        # If name is empty but we have real fields, derive it from the best field
        if not _name_lower and extraction_result.fields:
            _name_priority = [
                "part_desc", "product_name", "description", "name", "title",
                "item_name", "item_description", "model", "model_number",
                "mfg_part_num", "part_number", "sku",
            ]
            for _priority_key in _name_priority:
                _match = next(
                    (f for f in extraction_result.fields if f.name == _priority_key and f.value),
                    None
                )
                if _match:
                    extraction_result.product_name = str(_match.value)[:120]
                    _name_lower = extraction_result.product_name.lower().strip()
                    break
            # Ultimate fallback: first non-empty field value
            if not _name_lower:
                _first = next(
                    (f for f in extraction_result.fields if f.value and str(f.value).strip()),
                    None
                )
                if _first:
                    extraction_result.product_name = str(_first.value)[:120]
                    _name_lower = extraction_result.product_name.lower().strip()

        _is_failure = (
            not _name_lower
            or any(indicator in _name_lower for indicator in _FAILURE_INDICATORS)
            or len(extraction_result.fields) == 0
            # Catch names that are error-message strings, not real product names:
            # e.g. "No Power Tool Found In Source Text", "found in source"
            or "found in source" in _name_lower
            or "no product" in _name_lower
            or "not found" in _name_lower
        )
        if _is_failure:
            logger.error(
                "⛔ CIRCUIT BREAKER: extraction failed — product_name='%s', "
                "fields=%d. Stopping pipeline before enrichment to prevent "
                "hallucinated data.",
                extraction_result.product_name,
                len(extraction_result.fields),
            )
            raise ValueError(
                f"Extraction failed: '{extraction_result.product_name}' — "
                f"no valid product data could be extracted from the source. "
                f"Pipeline stopped to prevent fabricated output."
            )

        # ── Stage 4: Enrichment ───────────────────────────────────────
        _rotate_key()
        logger.info(
            "=== Stage 3/5 — EnrichmentAgent: enriching %d fields ===",
            len(extraction_result.fields),
        )
        enrichment_result = await enrichment_agent.enrich(
            fields=extraction_result.fields,
            category=category,
            source_id=ingestion_result.source.id,
        )
        logger.info(
            "Stage 3 complete: %d fields after enrichment",
            len(enrichment_result.fields),
        )

        for enrichment_source in enrichment_result.enrichment_sources:
            await store.save_source(enrichment_source)

        # ── Post-enrichment hallucination guard ───────────────────────────
        # If extraction produced very few fields (≤ 3 identity fields) and
        # enrichment exploded to > 25 fields, the enrichment agent probably
        # fabricated data from a mismatched web page. Demote all enrichment
        # fields to confidence = 5 + NEEDS_REVIEW so a human reviewer sees them.
        _extraction_field_count = len(extraction_result.fields)
        _enrichment_field_count = len(enrichment_result.fields)
        _enrichment_added = _enrichment_field_count - _extraction_field_count
        if _extraction_field_count <= 3 and _enrichment_added > 25:
            logger.warning(
                "⚠️ POST-ENRICHMENT SANITY: extraction had %d fields, enrichment "
                "added %d more (%d total) — possible fabrication. Demoting all "
                "enrichment-only fields to confidence=5.",
                _extraction_field_count, _enrichment_added, _enrichment_field_count,
            )
            from ..models.product_record import FieldStatus
            _extraction_names = {f.name for f in extraction_result.fields}
            for _ef in enrichment_result.fields:
                if _ef.name not in _extraction_names:
                    _ef.confidence = 5
                    _ef.status = FieldStatus.NEEDS_REVIEW
                    if _ef.reasoning:
                        _ef.reasoning = (
                            "[SANITY DEMOTED — low extraction coverage: "
                            f"{_extraction_field_count} fields before enrichment] "
                            + _ef.reasoning
                        )


        # ── Stage 5: Validation ───────────────────────────────────────
        _rotate_key()
        logger.info("=== Stage 4/5 — ValidationAgent: scoring confidence ===")
        validation_result = await validation_agent.validate(
            fields=enrichment_result.fields,
            category=category,
        )
        logger.info(
            "Stage 4 complete: overall confidence=%d%%, needs_review=%d",
            validation_result.confidence_overall,
            validation_result.needs_review_count,
        )

        # ── Stage 6: Explainability ───────────────────────────────────
        _rotate_key()
        logger.info("=== Stage 5/5 — ExplainabilityLayer: attaching provenance ===")
        annotated_fields = await explainability_layer.annotate(
            validation_result.fields
        )
        logger.info(
            "Stage 5 complete: %d fields annotated with provenance",
            len(annotated_fields),
        )

        # ── Dedup check (stub — Phase 5) ──────────────────────────────
        dedup_id = await check_duplicate(
            extraction_result.product_name, category
        )

        # ── Build and persist ProductRecord ───────────────────────────
        product = ProductRecord(
            id=uuid4(),
            name=extraction_result.product_name,
            category=category,
            fields=annotated_fields,
            source_ids=[
                ingestion_result.source.id,
                *(source.id for source in enrichment_result.enrichment_sources),
            ],
            confidence_overall=validation_result.confidence_overall,
            dedup_cluster_id=dedup_id,
        )

        # Populate the canonical part-number key for export deduplication.
        # Scan extracted fields in priority order — generic, works for any
        # CSV layout or product domain. The key is used to deduplicate
        # identical part numbers across multiple uploads or duplicate rows.
        _PN_FIELD_PRIORITY = (
            "mfg_part_num", "part_number", "manufacturer_part_number",
            "model_number", "sku", "item_number", "item_id",
            "catalog_number", "vendor_part_number", "supplier_part_number",
        )
        for _pn_key in _PN_FIELD_PRIORITY:
            _pn_field = next(
                (f for f in annotated_fields if f.name == _pn_key and f.value and str(f.value).strip()),
                None,
            )
            if _pn_field:
                product.mfg_part_num = str(_pn_field.value).strip()
                break

        await store.save_product(product, user_id=user_id)

        ctx["output_summary"] = (
            f"'{product.name}' — {len(product.fields)} fields, "
            f"confidence={product.confidence_overall}, "
            f"review={validation_result.needs_review_count}"
        )

        logger.info(
            "=== Pipeline COMPLETE: '%s' | %d fields | confidence=%d%% | needs_review=%d ===",
            product.name,
            len(product.fields),
            product.confidence_overall,
            validation_result.needs_review_count,
        )

        return product


def _detect_category(raw_text: str) -> str:
    """Simple keyword-based category detection.

    Scans the raw text for domain-specific keywords to guess the
    most likely product category. Falls back to "industrial_pump"
    if no clear match.
    """
    text_lower = raw_text.lower()

    category_keywords = {
        "industrial_pump": [
            "pump", "flow rate", "head pressure", "impeller",
            "centrifugal", "submersible", "suction", "discharge",
        ],
        "electrical_connector": [
            "connector", "contact", "pin", "socket", "plug",
            "voltage rating", "current rating", "ip67", "ip68",
        ],
        "safety_fastener": [
            "bolt", "nut", "screw", "fastener", "thread",
            "torque", "tensile", "washer", "grade 8.8", "grade 10.9",
            "din 931", "iso 898", "hex",
        ],
        "power_tool": [
            "drill", "driver", "saw", "nailer", "grinder", "sander",
            "milwaukee", "dewalt", "makita", "bosch", "ryobi", "metabo",
            "hilti", "m18", "m12", "20v max", "18v lxt", "flexvolt",
            "hedge trimmer", "hammer drill", "impact driver", "brad nailer",
            "framing nailer", "reciprocating", "circular saw",
            "bare tool", "kit", "cordless",
        ],
        "home_appliance": [
            "dishwasher", "washer", "dryer", "refrigerator", "freezer",
            "range", "oven", "microwave", "cooktop", "frigidaire",
            "whirlpool", "ge appliances", "samsung appliance", "miele",
            "capacity", "energy star", "spin cycle", "rinse",
        ],
        "electric_motor": [
            "motor", "rpm", "torque", "horsepower", " hp ",
            "nema", "iec frame", "inverter duty", "ac motor", "dc motor",
        ],
        "valve_actuator": [
            "valve", "actuator", "ball valve", "gate valve", "butterfly",
            "solenoid", "cv value", "kv value", "pn rating",
        ],
        "sensor_instrument": [
            "sensor", "transmitter", "transducer", "detector",
            "thermocouple", "rtd", "pressure sensor", "level sensor",
            "4-20ma", "0-10v",
        ],
        "power_supply": [
            "power supply", "psu", "ups", "rectifier",
            "ac/dc", "dc/dc", "output voltage", "output current",
        ],
        "cable_wire": [
            "cable", "conductor", "shielded", "armoured", "coaxial",
            "cat5", "cat6", "ethernet cable",
        ],
    }

    scores: dict[str, int] = {}
    for category, keywords in category_keywords.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        scores[category] = score

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        logger.info("No category keywords matched — using 'generic' universal extraction path")
        return "generic"

    logger.info("Auto-detected category: %s (score=%d)", best, scores[best])
    return best
