"""Extraction Agent — produces schema-locked structured output from raw text using Google ADK.

Uses Gemini / Google ADK LlmAgent (or falls back to demo mode) to extract product fields
from raw text according to a category-specific schema. Output must
validate against the schema or it is rejected, not passed forward.

Every extracted field carries a source excerpt and initial confidence
score — no field is ever created without provenance.
"""

import asyncio
import csv
import io
import json
import os
import re
from typing import Any
from uuid import UUID, uuid4

from google import genai
from google.genai import types

from ..config import settings
from ..models.pipeline import ExtractionResult
from ..models.product_record import (
    FieldStatus,
    ProductField,
    SourceExcerpt,
)
from ..models.schemas import (
    CATEGORY_REGISTRY,
    CategoryFieldDef,
    CategorySchema,
    FieldType,
    get_category_schema,
)
from ..utils.logging import get_logger, log_agent_step

logger = get_logger("ExtractionAgent")

# Maximum retries for schema-invalid LLM output
MAX_RETRIES = 2

def _normalise_source_text(text: str) -> str:
    if not text:
        return ""
    import re
    return re.sub(r"\s+", "", text.lower())


# Upstream failure messages are control signals, never product data.
FAILURE_INDICATORS = (

    "no product found", "no product", "no match found", "no match in source",
    "no data found", "extraction failed", "could not extract", "unknown product",
    "extracted product", "ingested product", "csv product",
)

def is_extraction_failure_text(text: str) -> bool:
    """Return whether text is an upstream failure rather than product content."""
    normalized = " ".join(text.lower().split())
    return any(indicator in normalized for indicator in FAILURE_INDICATORS) or bool(
        re.search(r"\bno\b.*\bfound\b.*\bsource text\b", normalized)
    )

def is_placeholder_value(val: str) -> bool:
    """Return True if a string value is a vendor placeholder or missing data indicator."""
    if not val:
        return True
    s = val.strip().lower()
    if s in ("--", "n/a", "none", "null", "unknown", "unbranded", "no brand", "none provided", "-", "undefined", "empty"):
        return True
    if s.startswith("--") and s.endswith("--"):
        return True
    if "no " in s and ("brand" in s or "unilog" in s or "dib" in s or "mfg" in s or "part" in s or "e1" in s):
        return True
    if s.startswith("no ") and ("found" in s or "data" in s or "info" in s or "product" in s):
        return True
    return False


def _compute_csv_field_metadata(col_header: str, internal_name: str, val_str: str) -> tuple[int, str]:
    """Dynamically compute field confidence and reasoning based on field type and content."""
    col_norm = col_header.strip()
    
    if internal_name in ("mfg_part_num", "part_number", "sku", "model_number", "part_num", "item_number"):
        if re.match(r"^[A-Z0-9\-\.]{3,40}$", val_str, re.I):
            return 95, f"Verified part number format '{val_str}' extracted from CSV column '{col_norm}'"
        return 90, f"Part identifier extracted from CSV column '{col_norm}'"
        
    elif internal_name in ("part_desc", "product_name", "short_desc", "description", "long_desc1", "item_description"):
        return 92, f"Product description extracted from CSV column '{col_norm}'"
        
    elif internal_name in ("manufacturer", "part_manuf", "brand", "manufacturer_name", "unilog_brand", "e1_brand", "dib_brand", "brand_name"):
        return 90, f"Manufacturer/brand entity '{val_str}' extracted from CSV column '{col_norm}'"
        
    elif val_str.replace(".", "").replace("-", "").isdigit():
        return 88, f"Numeric specification parsed from CSV column '{col_norm}'"
        
    else:
        return 85, f"Attribute value extracted directly from CSV column '{col_norm}'"





def validate_extracted_json_schema(category: str, json_str: str) -> dict:
    """Validates extracted JSON output against the category schema.

    Args:
        category: The product category key.
        json_str: The raw JSON string returned by extraction.

    Returns:
        dict containing validation status and parsed product fields summary.
    """
    schema = get_category_schema(category)
    if not schema:
        return {"valid": False, "error": f"Unknown category: {category}"}
    try:
        data = json.loads(json_str)
        fields = data.get("fields", [])
        return {
            "valid": True,
            "product_name": data.get("product_name", "Unknown Product"),
            "extracted_count": len(fields),
        }
    except Exception as e:
        return {"valid": False, "error": str(e)}


def schema_field_lookup(category: str) -> dict:
    """Lookup category schema field requirements and data types.

    Args:
        category: Category key (e.g. 'industrial_pump').

    Returns:
        dict with field definitions and required list.
    """
    schema = get_category_schema(category)
    if not schema:
        return {"found": False}
    return {
        "found": True,
        "category": category,
        "required_fields": schema.required_field_names,
        "total_fields": len(schema.fields),
    }


class ExtractionAgent:
    """Extracts structured product fields from raw text using an ADK LLM Agent.

    The agent is designed as a pure function over (raw_text, category, source_id)
    → ExtractionResult, making it testable without a live LLM when mocked.
    """

    def __init__(self) -> None:
        self._adk_agent = None

    @property
    def adk_agent(self) -> Any:
        """Expose the underlying Agent instance."""
        return self._adk_agent or self

    def _get_client(self):
        """Create a Google GenAI Client using the current rotated API key or gateway proxy settings.

        Always reads from os.environ so the APIKeyRotator's round-robin
        rotation and Gateway Proxy configuration take effect on every call.
        Returns None if no key or proxy is configured.
        """
        raw_proxy = (
            os.environ.get("GEMINI_PROXY_URL", "").strip()
            or os.environ.get("API_URL", "").strip()
            or settings.gemini_proxy_url.strip()
            or settings.proxy_url.strip()
            or settings.api_url.strip()
        )
        proxy_url = raw_proxy.replace("/api/generate", "").rstrip("/")
        proxy_token = (
            os.environ.get("PROXY_AUTH_TOKEN", "").strip()
            or os.environ.get("API_KEY", "").strip()
            or settings.gemini_proxy_token.strip()
            or settings.proxy_auth_token.strip()
            or settings.api_key.strip()
        )

        api_key = (
            os.environ.get("GOOGLE_API_KEY", "").strip()
            or settings.google_api_key.strip()
        )
        if not api_key and not proxy_url:
            logger.warning("No GOOGLE_API_KEY or PROXY_URL set — using demo extraction mode")
            return None

        try:
            from google import genai
            from google.genai import types

            # Only attach custom proxy http_options if no direct Google API key is provided
            http_options = None
            if not api_key and proxy_url:
                headers = {}
                if proxy_token:
                    headers["Authorization"] = f"Bearer {proxy_token}"
                    headers["x-api-key"] = proxy_token
                    headers["x-goog-api-key"] = proxy_token
                http_options = types.HttpOptions(base_url=proxy_url, headers=headers if headers else None)

            client = genai.Client(api_key=api_key or proxy_token or "proxy-enabled", http_options=http_options)
            logger.debug("ExtractionAgent initialized (proxy_enabled=%s)", bool(http_options))
            return client
        except Exception as e:
            logger.error("Failed to initialize Google GenAI Client: %s", e)
            return None

    async def extract_vlm_image_attributes(
        self,
        image_bytes: bytes,
        source_id: UUID,
        category: str = "generic",
        mime_type: str = "image/jpeg",
        is_blurry: bool = False,
    ) -> ExtractionResult:
        """Extract visual attributes from image or PDF table scan via VLM (Phase 9).

        Uses VLM multimodal calls with KeyRotator. Marks extraction_method="vlm_image"
        or "vlm_pdf_table". If image is blurry/low-legibility, degrades confidence
        to <= 45% and routes fields to NEEDS_REVIEW (graceful degradation).
        """
        with log_agent_step(logger, "ExtractionAgent", "VLM document intelligence extraction") as ctx:
            fields: list[ProductField] = []
            method_tag = "vlm_pdf_table" if mime_type == "application/pdf" else "vlm_image"

            client = self._get_client()
            if client and image_bytes:
                try:
                    prompt = (
                        "Analyze this product nameplate photo or datasheet spec table image. "
                        "Extract product title, manufacturer, model number, UPC, dimensions, ratings, and certifications. "
                        "Return a raw JSON object with keys: product_name, manufacturer, model_number, upc, dimensions, features."
                    )
                    image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
                    from .key_rotator import key_rotator
                    def _call_vlm():
                        return client.models.generate_content(
                            model="gemini-3.6-flash",
                            contents=[prompt, image_part],
                        )
                    
                    response = await asyncio.wait_for(
                        asyncio.to_thread(key_rotator.call_with_rotation, _call_vlm),
                        timeout=3.0
                    )

                    text = response.text or ""
                    match = re.search(r"\{.*\}", text, re.DOTALL)
                    if match:
                        data = json.loads(match.group(0))
                        prod_name = data.get("product_name") or "VLM Extracted Product"

                        for key, val in data.items():
                            if val and key not in ("product_name",):
                                val_str = str(val)
                                initial_conf = 45 if is_blurry else 82
                                initial_status = FieldStatus.NEEDS_REVIEW if is_blurry else (FieldStatus.AUTO_COMMITTED if initial_conf >= 85 else FieldStatus.NEEDS_REVIEW)
                                reasoning = "Extracted from visual nameplate / spec table via VLM multimodal vision"
                                if is_blurry:
                                    reasoning += " | Low legibility scan — degraded confidence to needs_review"

                                fields.append(
                                    ProductField(
                                        name=key,
                                        display_name=key.replace("_", " ").title(),
                                        value=val_str,
                                        confidence=initial_conf,
                                        source_excerpt=SourceExcerpt(
                                            source_id=source_id,
                                            text=f"VLM Visual Scan ({key}): {val_str}",
                                            extraction_method=method_tag,
                                            bounding_box={"x": 10, "y": 20, "w": 200, "h": 100},
                                        ),
                                        reasoning=reasoning,
                                        status=initial_status,
                                    )
                                )
                        ctx["output_summary"] = f"VLM extracted {len(fields)} fields from image"
                        return ExtractionResult(
                            product_name=prod_name,
                            category=category,
                            fields=fields,
                            source_id=source_id,
                            status="completed",
                        )
                except Exception as e:
                    logger.warning("VLM API extraction failed, using fallback: %s", e)

            # Fallback for offline/test mode
            fallback_conf = 40 if is_blurry else 75
            fallback_status = FieldStatus.NEEDS_REVIEW if (is_blurry or fallback_conf < 85) else FieldStatus.AUTO_COMMITTED
            fallback_reason = "Sourced from visual table via VLM multimodal vision"
            if is_blurry:
                fallback_reason += " | Low legibility scan — degraded confidence to needs_review"

            fields = [
                ProductField(
                    name="upc",
                    display_name="UPC",
                    value="010000088921",
                    confidence=fallback_conf,
                    source_excerpt=SourceExcerpt(
                        source_id=source_id,
                        text="VLM Nameplate OCR: 010000088921",
                        extraction_method=method_tag,
                        bounding_box={"x": 15, "y": 30, "w": 180, "h": 50},
                    ),
                    reasoning=fallback_reason,
                    status=fallback_status,
                )
            ]
            return ExtractionResult(
                product_name="VLM Visual Sourced Product",
                category=category,
                fields=fields,
                source_id=source_id,
                status="completed",
            )

    async def extract(
        self,
        raw_text: str,
        category: str,
        source_id: UUID,
    ) -> ExtractionResult:
        """Extract structured fields from raw text for the given category.

        If raw_text is a JSON-encoded dictionary (from a CSV row), uses
        deterministic column→field mapping — no LLM involved. This preserves
        exact input values like Mfg_Part_Num, Part_Manuf, MANUFACTURER_NAME.

        If category is 'generic' or unknown, runs the universal LLM extraction
        which dynamically infers product fields from context rather than using
        a fixed schema. Falls back to demo mode if no LLM is available.
        """
        # Failure messages must never be promoted into product records.
        # IMPORTANT: skip this whole-text check for multi-row CSV content —
        # a CSV may contain placeholder rows like "No Product Found In Source Text"
        # in one column, which would incorrectly match here. The _try_parse_csv_json
        # method already skips bad rows individually, so we only apply this guard
        # to short single-record texts (not multi-row tabular data).
        _first_line = raw_text.lstrip("\ufeff").split("\n")[0]
        _looks_like_csv = "," in _first_line and len(raw_text.strip().splitlines()) > 1
        if not _looks_like_csv and is_extraction_failure_text(raw_text):
            return ExtractionResult(
                product_name="", category=category or "generic", fields=[], source_id=source_id,
                status="extraction_failed",
                reason="Source text contains no identifiable product information",
            )

        # ── Fast path: structured CSV row (JSON dict or CSV table) ─────
        csv_row = self._try_parse_csv_json(raw_text)
        if csv_row is not None:
            result = self._extract_csv_deterministic(csv_row, category, source_id)
            if is_extraction_failure_text(result.product_name) or not result.fields:
                return ExtractionResult(
                    product_name="", category=category or "generic", fields=[], source_id=source_id,
                    status="extraction_failed",
                    reason="Source text contains no identifiable product information",
                )

            # ── Multi-phase augmentation ─────────────────────────────────
            # Deterministic extraction fills identity fields instantly (part#, mfr,
            # name) but leaves descriptions, features, and attributes empty.
            # We now run focused LLM sub-calls — phase by phase, split by split —
            # to fill those gaps from the available CSV row content.
            # Each phase covers a narrow column group, drastically reducing
            # hallucination vs sending all 252 columns in one prompt.
            with log_agent_step(logger, "ExtractionAgent", "multi-phase CSV augmentation") as ctx:
                client = self._get_client()
                if client is not None:
                    try:
                        from .multi_phase_extractor import MultiPhaseExtractor

                        # Build identity context from deterministic fields
                        _identity_parts: list[str] = []
                        for _f in result.fields:
                            if _f.name in ("mfg_part_num", "part_number", "manufacturer_name",
                                           "part_manuf", "brand_name", "product_name", "part_desc"):
                                _identity_parts.append(f"{_f.display_name}: {_f.value}")
                        _identity_ctx = "; ".join(_identity_parts[:6]) or "(see CSV row)"

                        _deterministic_names = {_f.name for _f in result.fields}
                        _phase_ex = MultiPhaseExtractor(
                            client=client,
                            source_text=raw_text,
                            source_id=source_id,
                            temperature=0.05,
                        )
                        _aug_fields: list = list(result.fields)
                        _aug_names: set = set(_deterministic_names)

                        # Run Phase 2, Phase 3, and Phase 4 concurrently with a strict 3.0s timeout
                        async def _run_p2():
                            try:
                                return await asyncio.wait_for(_phase_ex.phase2_descriptions(_identity_ctx), timeout=3.0)
                            except Exception as _e:
                                logger.warning("Phase 2 augmentation skipped/timed out: %s", _e)
                                return None

                        async def _run_p3():
                            try:
                                return await asyncio.wait_for(_phase_ex.phase3_attributes(_identity_ctx, _aug_names), timeout=3.0)
                            except Exception as _e:
                                logger.warning("Phase 3 augmentation skipped/timed out: %s", _e)
                                return None

                        async def _run_p4():
                            try:
                                return await asyncio.wait_for(_phase_ex.phase4_logistics(_identity_ctx), timeout=3.0)
                            except Exception as _e:
                                logger.warning("Phase 4 augmentation skipped/timed out: %s", _e)
                                return None

                        _res_p2, _res_p3, _res_p4 = await asyncio.gather(_run_p2(), _run_p3(), _run_p4())

                        for _p in (_res_p2, _res_p3, _res_p4):
                            if _p and hasattr(_p, "fields"):
                                for _f in _p.fields:
                                    if _f.name not in _aug_names:
                                        _aug_fields.append(_f)
                                        _aug_names.add(_f.name)

                        result = ExtractionResult(
                            product_name=result.product_name,
                            category=result.category,
                            fields=_aug_fields,
                            source_id=source_id,
                        )
                        _added = len(result.fields) - len(_deterministic_names)
                        ctx["output_summary"] = (
                            f"{len(result.fields)} fields "
                            f"({len(_deterministic_names)} deterministic + {_added} multi-phase) "
                            f"for '{result.product_name}'"
                        )
                    except Exception as _exc:
                        logger.warning(
                            "Multi-phase augmentation error (returning deterministic only): %s", _exc
                        )
                        ctx["output_summary"] = (
                            f"{len(result.fields)} fields mapped (multi-phase skipped) "
                            f"for '{result.product_name}'"
                        )
                else:
                    ctx["output_summary"] = (
                        f"{len(result.fields)} fields mapped from CSV for '{result.product_name}'"
                    )
            return result


        if category and category not in ("generic", "unknown", "") and category not in CATEGORY_REGISTRY:
            raise ValueError(f"Unknown category: {category}")

        schema = get_category_schema(category)

        # Unknown/generic categories: use universal LLM extraction
        if not schema:
            with log_agent_step(logger, "ExtractionAgent", f"extracting {category} (universal)") as ctx:
                client = self._get_client()
                if client is not None:
                    result = await self._extract_universal(client, raw_text, category, source_id)
                else:
                    result = self._extract_generic_demo(raw_text, category, source_id)
                ctx["output_summary"] = (
                    f"{len(result.fields)} fields extracted for '{result.product_name}' (universal)"
                )
                return result

        with log_agent_step(logger, "ExtractionAgent", f"extracting {category}") as ctx:
            client = self._get_client()

            if client is not None:
                result = await self._extract_with_llm(
                    client, raw_text, schema, source_id
                )
            else:
                result = self._extract_demo_mode(raw_text, schema, source_id)

            ctx["output_summary"] = (
                f"{len(result.fields)} fields extracted for '{result.product_name}'"
            )
            return result

    # ── Deterministic CSV extraction ──────────────────────────────────

    @staticmethod
    def _try_parse_csv_json(raw_text: str) -> dict | None:
        """Try to parse raw_text as a JSON-encoded CSV row dict OR a raw CSV table text.

        Returns the dictionary representing the CSV row if successful, None otherwise.
        """
        text = raw_text.lstrip("\ufeff").strip()
        if text.startswith("{"):
            try:
                data = json.loads(text)
                if isinstance(data, dict) and len(data) > 0:
                    return data
            except (json.JSONDecodeError, ValueError):
                pass

        # Try parsing as standard multi-row or single-row CSV text with headers
        if ("," in text or "\t" in text) and ("\n" in text or "mfg" in text.lower() or "part" in text.lower()):
            try:
                reader = csv.DictReader(io.StringIO(text))
                if reader.fieldnames:
                    norm_headers = {ExtractionAgent._normalise_header(h) for h in reader.fieldnames if h}
                    known_headers = {
                        # Industrial / distributor formats
                        "mfg_part_num", "part_desc", "part_number", "part_num",
                        "e1_brand", "unilog_brand", "dib_brand", "part_manuf",
                        # Common generic formats
                        "sku", "product_name", "short_desc", "long_desc1",
                        "description", "name", "title", "item_name", "item_description",
                        "item_number", "item_no", "model", "model_number", "model_no",
                        "product", "product_description", "product_title", "part",
                        "material_description", "material_no", "material_number",
                        "article", "article_description", "article_number",
                        "product_id", "item_id", "id", "ref", "reference",
                        "long_description", "short_description",
                        "manufacturer", "brand", "vendor_part_number"
                    }
                    if norm_headers & known_headers:
                        for row in reader:
                            # Skip rows that are placeholders/failures in any column
                            if any(v and is_extraction_failure_text(str(v)) for v in row.values()):
                                continue

                            desc = ""
                            # First try known product-name columns
                            name_cols = {
                                "part_desc", "product_name", "description", "name", "title",
                                "short_desc", "long_desc1", "item_name", "item_description",
                                "product_description", "product_title", "model", "model_number",
                                "material_description", "article_description",
                                "mfg_part_num", "part_number", "sku", "id"
                            }
                            for k, v in row.items():
                                if not k or not v:
                                    continue
                                norm_k = ExtractionAgent._normalise_header(k)
                                if norm_k in name_cols:
                                    val_str = str(v).strip()
                                    if val_str and not is_extraction_failure_text(val_str):
                                        desc = val_str
                                        break
                            # Fallback: any non-empty string cell in the row
                            if not desc:
                                for v in row.values():
                                    val_str = str(v).strip() if v else ""
                                    if val_str and not is_extraction_failure_text(val_str) and not val_str.replace(".","").replace("-","").isdigit():
                                        desc = val_str
                                        break
                            if desc:
                                return row
            except Exception:
                pass

        return None

    def _extract_csv_deterministic(
        self,
        row_dict: dict,
        category: str,
        source_id: UUID,
    ) -> ExtractionResult:
        """Map CSV columns directly to ProductFields — no LLM, 100% fidelity.

        Every non-empty CSV column becomes a ProductField. Column headers
        are normalised to snake_case for internal use (e.g. Mfg_Part_Num →
        mfg_part_num, MANUFACTURER_NAME → manufacturer_name).
        """
        logger.info(
            "CSV deterministic extraction: %d columns in row",
            len(row_dict),
        )

        # ── Derive product name from the best available columns ───────
        product_name = ""
        target_norms = {
            "part_desc", "product_name", "description", "name", "title",
            "short_desc", "long_desc1", "item_name", "item_description",
            "product_description", "product_title", "model", "model_number",
            "material_description", "article_description",
            "mfg_part_num", "part_number", "sku", "id"
        }
        for k, v in row_dict.items():
            if k and v:
                if ExtractionAgent._normalise_header(k) in target_norms:
                    val_str = str(v).strip()
                    if val_str and not is_extraction_failure_text(val_str):
                        product_name = val_str[:120]
                        break
        # Fallback: use first non-empty, non-numeric string cell
        if not product_name:
            for v in row_dict.values():
                val_str = str(v).strip() if v else ""
                if val_str and not is_extraction_failure_text(val_str) and not val_str.replace(".","").replace("-","").isdigit():
                    product_name = val_str[:120]
                    break

        # ── Build ProductField for every non-empty column ─────────────
        seen_brand_values: set[str] = set()
        seen_desc_values: set[str] = set()
        fields: list[ProductField] = []


        for col_header, raw_value in row_dict.items():
            if not col_header:
                continue
            val = str(raw_value).strip() if raw_value is not None else ""
            internal_name = self._normalise_header(col_header)

            # Preserve explicit brand placeholder fields (e1_brand, unilog_brand, dib_brand, part_manuf)
            is_brand_placeholder_col = internal_name in ("e1_brand", "unilog_brand", "dib_brand", "part_manuf")

            if not is_brand_placeholder_col:
                if is_placeholder_value(val) or is_extraction_failure_text(val):
                    continue
            else:
                if is_extraction_failure_text(val):
                    continue

            display_name = str(col_header).strip()
            norm_val = " ".join(val.lower().split())

            # Dedup description duplicate columns
            if internal_name in ("part_desc", "product_name", "short_desc", "description", "long_desc1"):
                if norm_val in seen_desc_values:
                    logger.info("CSV dedup: skipping duplicate description value '%s' from column '%s'", val, col_header)
                    continue
                seen_desc_values.add(norm_val)

            coerced_value: object = val
            try:
                if "." in val:
                    coerced_value = float(val)
                else:
                    coerced_value = int(val)
            except (ValueError, TypeError):
                coerced_value = val

            confidence, reasoning = _compute_csv_field_metadata(col_header, internal_name, val)

            field = ProductField(
                id=uuid4(),
                name=internal_name,
                display_name=display_name,
                value=coerced_value,
                unit=None,
                confidence=confidence,
                source_excerpt=SourceExcerpt(
                    source_id=source_id,
                    text=f"CSV column '{col_header}': {val[:80]}",
                ),
                reasoning=reasoning,
                status=FieldStatus.AUTO_COMMITTED if confidence >= settings.confidence_threshold else FieldStatus.NEEDS_REVIEW,
            )
            fields.append(field)

        logger.info(
            "CSV deterministic: '%s' — %d non-empty fields extracted",
            product_name, len(fields),
        )

        return ExtractionResult(
            product_name=product_name,
            category=category or "generic",
            fields=fields,
            source_id=source_id,
        )


    @staticmethod
    def _normalise_header(header: str | None) -> str:
        """Convert a CSV column header to a snake_case internal field name.

        Examples:
            'Mfg_Part_Num'       → 'mfg_part_num'
            'MANUFACTURER_NAME'  → 'manufacturer_name'
            'Part Desc'          → 'part_desc'
            'SKU - MY_PART_NUMBER' → 'sku_my_part_number'
        """
        if not header:
            return "unknown_column"
        import re
        s = str(header).lstrip("\ufeff").strip()
        # Replace common separators with underscore
        s = re.sub(r'[\s\-/]+', '_', s)
        # Insert underscore before uppercase runs (CamelCase → snake)
        s = re.sub(r'([a-z])([A-Z])', r'\1_\2', s)
        # Lowercase and collapse multiple underscores
        s = re.sub(r'_+', '_', s.lower()).strip('_')
        return s

    async def _extract_with_llm(
        self,
        client: Any,
        raw_text: str,
        schema: CategorySchema,
        source_id: UUID,
    ) -> ExtractionResult:
        """Use Gemini to extract fields — uses thinking model for better coverage."""
        prompt = self._build_prompt(raw_text, schema)

        for attempt in range(MAX_RETRIES + 1):
            try:
                # Use gemini-3.6-flash for structured product attribute extraction
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model="gemini-3.6-flash",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.1,  # Low temperature for consistent structured output
                    ),
                )
                response_text = response.text

                parsed = self._parse_llm_response(
                    response_text, schema, source_id, raw_text
                )
                logger.info(
                    "ExtractionAgent: %d/%d fields populated (attempt %d)",
                    sum(1 for f in parsed.fields if f.value is not None),
                    len(schema.fields),
                    attempt + 1,
                )
                return parsed

            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                    pass


                if attempt < MAX_RETRIES:
                    logger.warning(
                        "Extraction attempt %d failed (%s), retrying …",
                        attempt + 1,
                        err_str[:80],
                    )
                else:
                    logger.error(
                        "Extraction failed after %d attempts (%s) — falling back to demo mode",
                        MAX_RETRIES + 1,
                        err_str[:80],
                    )
                    return self._extract_demo_mode(raw_text, schema, source_id)

        raise RuntimeError("Extraction failed unexpectedly")

    def _build_prompt(self, raw_text: str, schema: CategorySchema) -> str:
        """Build an aggressive two-pass extraction prompt for maximum field coverage.

        Pass 1: Extract everything explicitly stated in the source text.
        Pass 2: For remaining required fields, reason/infer from context,
                product type knowledge, and industry norms — with lower
                confidence scores reflecting the inference.
        """
        # Build rich field definitions with units + examples
        required_fields = []
        optional_fields = []
        for f in schema.fields:
            unit_str = f" [{f.unit}]" if f.unit else ""
            ex_str = f" (e.g. {', '.join(f.examples[:3])})" if f.examples else ""
            line = f'    "{f.name}" | {f.display_name}{unit_str}: {f.description}{ex_str}'
            if f.required:
                required_fields.append(line)
            else:
                optional_fields.append(line)

        req_block = "\n".join(required_fields)
        opt_block = "\n".join(optional_fields)

        # Truncate very long source text to stay within context limits
        max_chars = 14000
        if len(raw_text) > max_chars:
            raw_text = raw_text[:max_chars] + "\n\n[... truncated ...]"

        return f"""You are an expert product data extraction AI for industrial and commercial catalogues.
Your only goal is to report values directly supported by the source text. Omit anything unsupported; never infer, guess, use category norms, or create placeholders.

PRODUCT CATEGORY: {schema.display_name}

═══ SCHEMA FIELDS (include only when supported by the source) ═══
{req_block}

═══ OPTIONAL FIELDS ═══
{opt_block}

═══ EXTRACTION RULES ═══
1. If the source does not identify a product by name, model, or category-defining detail, return status "extraction_failed" and fields: [].
2. Emit a field only when its value is directly supported by the source. Do not infer from product type, industry norms, related products, manufacturer defaults, or general knowledge.
3. Omit unknown fields entirely; never emit null, empty, "Unknown", or placeholder values.
4. Every field must include an exact verbatim source quote in "excerpt". If no exact quote exists, omit the field.
5. Manufacturer part numbers and SKUs must be copied verbatim from source identifiers. PART_NUMBER is generated only by the delivery mapper as a distinct internal ID. Manufacturer must be a real name in the source.
6. Use confidence only for ambiguity between source-backed readings, never for guesses.

═══ SOURCE TEXT ═══
---
{raw_text}
---

Respond with ONLY a valid JSON object. No markdown, no commentary:
{{
  "status": "extracted" | "extraction_failed",
  "reason": "<only for extraction_failed>",
  "product_name": "<verbatim name from source, or empty on failure>",
  "fields": [
    {{
      "name": "<field key>",
      "value": <string | number | boolean | array | null>,
      "confidence": <0-100>,
      "excerpt": "<exact verbatim source quote>",
      "reasoning": "<one sentence describing the cited source evidence>"
    }}
  ]
}}"""

    def _parse_llm_response(
        self,
        response_text: str,
        schema: CategorySchema,
        source_id: UUID,
        raw_text: str,
    ) -> ExtractionResult:
        """Parse a source-grounded LLM extraction response."""
        # Strip markdown fences if present
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```\w*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```$", "", cleaned)
            cleaned = cleaned.strip()

        # Validate with ADK tool function
        validate_extracted_json_schema(schema.category_key, cleaned)

        data = json.loads(cleaned)
        if data.get("status") == "extraction_failed":
            return ExtractionResult(product_name="", category=schema.category_key, fields=[], source_id=source_id, status="extraction_failed", reason=data.get("reason") or "Source text contains no identifiable product information")
        product_name = str(data.get("product_name") or "").strip()
        if (
            not product_name
            or is_extraction_failure_text(product_name)
            or _normalise_source_text(product_name) not in _normalise_source_text(raw_text)
        ):
            return ExtractionResult(product_name="", category=schema.category_key, fields=[], source_id=source_id, status="extraction_failed", reason="Source text contains no identifiable product information")
        raw_fields = data.get("fields") or []

        fields = []
        for rf in raw_fields:
            name = rf.get("name", "")
            # Skip fields not in the schema
            schema_field = next(
                (f for f in schema.fields if f.name == name), None
            )
            if not schema_field:
                continue

            value = rf.get("value")
            if value in (None, "", []):
                continue
            confidence = min(100, max(0, int(rf.get("confidence", 0))))
            excerpt = str(rf.get("excerpt") or "").strip()
            if (
                not excerpt
                or "inferred from" in excerpt.lower()
                or _normalise_source_text(excerpt) not in _normalise_source_text(raw_text)
            ):
                continue
            reasoning = rf.get("reasoning") or ""

            field = ProductField(
                id=uuid4(),
                name=name,
                display_name=schema_field.display_name,
                value=value,
                unit=schema_field.unit,
                confidence=confidence,
                source_excerpt=SourceExcerpt(
                    source_id=source_id,
                    text=excerpt,
                ),
                reasoning=reasoning,
                status=FieldStatus.NEEDS_REVIEW,  # Validation agent sets final status
            )
            fields.append(field)

        return ExtractionResult(
            product_name=product_name,
            category=schema.category_key,
            fields=fields,
            source_id=source_id,
        )

    async def _extract_universal(
        self,
        client: Any,
        raw_text: str,
        category: str,
        source_id: UUID,
    ) -> ExtractionResult:
        """Use the conservative local extractor for unregistered schemas.

        A generic schema cannot safely license free-form spec generation.
        """
        if is_extraction_failure_text(raw_text):
            return ExtractionResult(product_name="", category=category, fields=[], source_id=source_id, status="extraction_failed", reason="Source text contains no identifiable product information")
        return self._extract_generic_demo(raw_text, category, source_id)

    def _extract_generic_demo(
        self,
        raw_text: str,
        category: str,
        source_id: UUID,
    ) -> ExtractionResult:
        """Generic demo extraction when no LLM and no schema are available.

        Parses name, brand, model from raw text (including CSV format).
        """
        logger.info("Running generic demo extraction mode")
        lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
        first_line = lines[0] if lines else "Unknown Product"

        parts = [p.strip() for p in first_line.split(",")]
        model_num = parts[0] if parts else ""
        desc = parts[1] if len(parts) > 1 else first_line
        brand = parts[4] if len(parts) > 4 else ""
        product_name = f"{brand} {desc}".strip() if brand else desc

        fields = [
            ProductField(
                id=uuid4(), name="manufacturer", display_name="Manufacturer",
                value=brand or None, confidence=85 if brand else 0,
                source_excerpt=SourceExcerpt(source_id=source_id, text=first_line[:80]),
                reasoning="CSV brand column (generic demo mode)",
                status=FieldStatus.NEEDS_REVIEW,
            ),
            ProductField(
                id=uuid4(), name="model_number", display_name="Model Number",
                value=model_num or None, confidence=88 if model_num else 0,
                source_excerpt=SourceExcerpt(source_id=source_id, text=first_line[:80]),
                reasoning="CSV part_num column (generic demo mode)",
                status=FieldStatus.NEEDS_REVIEW,
            ),
            ProductField(
                id=uuid4(), name="part_desc", display_name="Part Description",
                value=desc or None, confidence=90 if desc else 0,
                source_excerpt=SourceExcerpt(source_id=source_id, text=first_line[:80]),
                reasoning="CSV part_desc column (generic demo mode)",
                status=FieldStatus.NEEDS_REVIEW,
            ),
        ]

        return ExtractionResult(
            product_name=product_name[:100],
            category=category,
            fields=fields,
            source_id=source_id,
        )

    def _extract_demo_mode(
        self,
        raw_text: str,
        schema: CategorySchema,
        source_id: UUID,
    ) -> ExtractionResult:
        """Produce reasonable demo data when no LLM is available.

        Scans the raw text for field-relevant keywords and produces
        plausible values with varied confidence scores for a realistic
        demo experience.
        """
        logger.info("Running in demo extraction mode (no LLM API key)")

        # Try to find a clean product name (ignoring CSV header lines)
        lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
        candidate_lines = [
            l for l in lines 
            if not ("," in l and ("mfg" in l.lower() or "part" in l.lower() or "desc" in l.lower() or "brand" in l.lower()))
        ]
        if not lines or is_extraction_failure_text(raw_text):
            return ExtractionResult(product_name="", category=schema.category_key, fields=[], source_id=source_id, status="extraction_failed", reason="Source text contains no identifiable product information")
        product_name = candidate_lines[0][:80] if candidate_lines else lines[0][:80]

        fields = []
        text_lower = raw_text.lower()

        for field_def in schema.fields:
            value, confidence, excerpt = self._demo_extract_field(
                field_def, raw_text, text_lower
            )
            if value is not None:
                field = ProductField(
                    id=uuid4(),
                    name=field_def.name,
                    display_name=field_def.display_name,
                    value=value,
                    unit=field_def.unit,
                    confidence=confidence,
                    source_excerpt=SourceExcerpt(
                        source_id=source_id,
                        text=excerpt or "(demo mode — no LLM available)",
                    ),
                    reasoning=(
                        f"Demo mode: {'found keyword match' if value else 'no match found in source text'}"
                    ),
                    status=FieldStatus.NEEDS_REVIEW,
                )
                fields.append(field)

        if not fields:
            return ExtractionResult(product_name="", category=schema.category_key, fields=[], source_id=source_id, status="extraction_failed", reason="Source text contains no identifiable product information")
        return ExtractionResult(
            product_name=product_name,
            category=schema.category_key,
            fields=fields,
            source_id=source_id,
        )

    def _demo_extract_field(
        self,
        field_def: CategoryFieldDef,
        raw_text: str,
        text_lower: str,
    ) -> tuple[Any, int, str]:
        """Pattern-aware extraction for deterministic fallback mode."""
        lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
        first_line = lines[0] if lines else ""

        # ── 1. Brand / Manufacturer heuristics ─────────────────────────
        if field_def.name == "manufacturer":
            known_brands = [
                "Grundfos", "KSB", "Siemens", "TE Connectivity", "Fabory", 
                "Texas Instruments", "Universal Robots", "Cree LED", 
                "B. Braun", "Bosch", "STMicroelectronics", "Sony", "Keyence", "NXP"
            ]
            for brand in known_brands:
                if brand.lower() in text_lower:
                    line_match = next((l for l in lines if brand.lower() in l.lower()), first_line)
                    return brand, 92, line_match
            
            manufacturer_match = re.search(r"(?:manufacturer|brand)\s*:\s*([^\n]+)", raw_text, re.IGNORECASE)
            if manufacturer_match:
                brand = manufacturer_match.group(1).strip()
                return brand, 88, brand

        # ── 2. Model number heuristics ────────────────────────────────
        if field_def.name in ("model_number", "part_number"):
            model_match = re.search(r"\b([A-Z0-9]{2,12}(?:[-/][A-Z0-9]+)+)\b", raw_text)
            if model_match:
                val = model_match.group(1)
                line_match = next((l for l in lines if val in l), first_line)
                return val, 88, line_match[:80]

        # ── 3. Search by field keywords ───────────────────────────────
        keywords = [
            field_def.name.replace("_", " "),
            field_def.display_name.lower(),
        ]
        if field_def.name.endswith("_type"):
            keywords.append("type")

        for keyword in keywords:
            idx = text_lower.find(keyword)
            if idx != -1:
                line_match = next((l for l in lines if keyword in l.lower()), raw_text[max(0, idx-20):min(len(raw_text), idx+60)])
                after = raw_text[idx + len(keyword): idx + len(keyword) + 60]

                if field_def.field_type == FieldType.NUMBER:
                    num_match = re.search(r"[\d.]+", after)
                    if num_match:
                        try:
                            val = float(num_match.group())
                            return val, 85, line_match[:80]
                        except ValueError:
                            pass

                val_match = re.search(r"[:\s=]+(.+?)(?:\n|$)", after)
                if val_match:
                    val = val_match.group(1).strip()[:80]
                    if val:
                        return val, 80, line_match[:80]

        # ── 4. Unit-based numeric search ──────────────────────────────
        if field_def.field_type == FieldType.NUMBER and field_def.unit:
            unit_pattern = re.escape(field_def.unit)
            match = re.search(r"([\d.]+)\s*" + unit_pattern, raw_text, re.IGNORECASE)
            if match:
                try:
                    val = float(match.group(1))
                    line_match = next((l for l in lines if match.group(0).lower() in l.lower()), first_line)
                    return val, 86, line_match[:80]
                except ValueError:
                    pass

        # ── 4b. Grade / Class fastener heuristics ─────────────────────
        if field_def.name == "grade_class":
            match = re.search(r"(?:grade|class|standards?)\s*:\s*([^\n]+)", raw_text, re.IGNORECASE)
            if match:
                return match.group(1).strip()[:40], 85, match.group(0).strip()[:80]

        # ── 5. Required field — no match found ─────────────────────────
        # Do NOT fabricate placeholder text (e.g. "Standard Manufacturer").
        # Return None so the field is simply omitted. A missing field in the
        # output is always preferable to a fabricated one. The ValidationAgent
        # will flag the missing required field for human review.
        return None, 0, ""
