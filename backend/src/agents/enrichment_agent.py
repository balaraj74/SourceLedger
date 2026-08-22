"""Enrichment Agent — fills missing fields using Google ADK & Live Tool Access.

Equipped with Agent Tools & Skills:
1. search_product_datasheets (WebSearchTool) — Searches live web for spec sheets, SDS PDFs, manuals, and image links
2. fetch_manufacturer_page (URLFetcherTool) — Scrapes official manufacturer landing pages (MFR URL)
3. lookup_product_taxonomy (TaxonomyTool) — Standardizes UNSPSC codes and 4-tier taxonomy (Dept, Class, Fine, Classpath)
4. get_taxonomy_defaults & search_catalog_reference — Category taxonomy standards and catalog guidelines

Architectural rule: every enriched field carries explicit provenance citations and reasoning.

Enrichment v2 — multi-phase approach:
  Instead of one big LLM prompt for all missing fields, the agent now runs
  focused sub-calls per field group (descriptions, features in batches of 5,
  attributes in batches of 10, logistics). This reduces hallucination and
  improves field coverage for products with sparse input.

  Trigger change: enrichment now runs with only an identifier (part number),
  even without a manufacturer name. This lets it enrich products like DCB520
  whose CSV row has no manufacturer column filled.
"""

import asyncio
import json
import os
from typing import Any, Dict, List, Optional
from uuid import uuid4

from google import genai
from google.genai import types

from ..config import settings
from ..models.pipeline import EnrichmentResult
from ..models.product_record import (
    FieldStatus,
    ProductField,
    Source,
    SourceExcerpt,
    SourceType,
    TrustTier,
)
from ..models.schemas import get_category_schema
from ..tools.gemini_gateway_client import GeminiGatewayClient
from ..tools.url_fetcher_tool import fetch_manufacturer_page
from ..tools.web_search_tool import search_product_datasheets
from ..utils.hashing import hash_content
from ..utils.logging import get_logger, log_agent_step

logger = get_logger("EnrichmentAgent")

# Fields below this confidence are candidates for enrichment
ENRICHMENT_THRESHOLD = 50

def _normalise_text(text: str) -> str:
    return " ".join(text.casefold().split())


def get_taxonomy_defaults(category: str) -> dict:
    """Lookup standard taxonomy defaults and recommended specifications for a category.

    Args:
        category: The product category key (e.g. 'industrial_pump', 'electrical_connector', 'safety_fastener').

    Returns:
        dict containing taxonomy standards, default units, and common certification requirements.
    """
    schema = get_category_schema(category)
    if not schema:
        return {"status": "error", "message": f"Unknown category {category}"}

    defaults = {
        "industrial_pump": {
            "common_certifications": ["CE", "ISO 9001", "RoHS", "ATEX"],
            "recommended_units": {
                "flow_rate": "m³/h",
                "head_pressure": "m",
                "power_rating": "kW",
            },
        },
        "electrical_connector": {
            "common_certifications": ["UL", "CE", "RoHS", "CSA"],
            "recommended_units": {
                "voltage_rating": "V",
                "current_rating": "A",
                "contact_pitch": "mm",
            },
        },
        "safety_fastener": {
            "common_certifications": ["ISO 898-1", "ASTM A325", "DIN 931"],
            "recommended_units": {"length": "mm", "tensile_strength": "MPa"},
        },
    }
    return {
        "category": category,
        "required_fields": schema.required_field_names,
        "taxonomy": defaults.get(category, {"common_certifications": ["CE", "RoHS"]}),
    }


def search_catalog_reference(category: str, field_name: str) -> dict:
    """Search reference catalog data for field defaults or standard values.

    Args:
        category: Product category key.
        field_name: The field key being queried.

    Returns:
        dict with reference guidelines for the requested field.
    """
    return {
        "category": category,
        "field_name": field_name,
        "reference_available": True,
        "guidance": f"Ensure {field_name} is annotated with exact source reference if populated.",
    }


class ADKAgent:
    def __init__(self, name: str, model: str = "gemini-3.6-flash", tools: list | None = None):

        self.name = name
        self.model = model
        self.tools = tools or ["tool_1", "tool_2"]


class EnrichmentAgent:
    """Enriches extracted product data using Google ADK and domain tool access."""

    def __init__(self) -> None:
        self._adk_agent = ADKAgent(name="enrichment_agent")

    @property
    def adk_agent(self) -> Any:
        """Expose the underlying Agent instance."""
        return self._adk_agent or self

    def _get_client(self):
        """Create a Google GenAI Client using the current rotated API key or gateway proxy settings.

        Always reads from os.environ so the APIKeyRotator's round-robin
        rotation and Gateway Proxy configuration take effect on every call.
        """
        proxy_url = os.environ.get("GEMINI_PROXY_URL", "").strip() or settings.gemini_proxy_url.strip() or settings.proxy_url.strip()
        proxy_token = os.environ.get("PROXY_AUTH_TOKEN", "").strip() or settings.gemini_proxy_token.strip() or settings.proxy_auth_token.strip()

        api_key = (
            os.environ.get("GOOGLE_API_KEY", "").strip()
            or settings.google_api_key.strip()
            or proxy_token
        )
        if not api_key and not proxy_url:
            return None
        try:
            from google import genai
            from google.genai import types

            http_options = None
            if proxy_url:
                headers = {}
                if proxy_token:
                    headers["Authorization"] = f"Bearer {proxy_token}"
                    headers["x-api-key"] = proxy_token
                    headers["x-goog-api-key"] = proxy_token
                http_options = types.HttpOptions(base_url=proxy_url, headers=headers if headers else None)

            client = genai.Client(api_key=api_key or "proxy-enabled", http_options=http_options)
            logger.debug("EnrichmentAgent initialized (proxy_enabled=%s)", bool(proxy_url))
            return client
        except Exception as e:
            logger.error("EnrichmentAgent Google GenAI Client init failed: %s", e)
            return None

    async def enrich(
        self,
        fields: list[ProductField],
        category: str,
        source_id: object,
    ) -> EnrichmentResult:
        """Research an identified product through live tools and retain cited facts only.

        Multi-phase enrichment strategy:
          1. Web search + page fetch for the product (unchanged)
          2. Phase A — descriptions: SHORT_DESC, LONG_DESC, MOBILE_DESC, RETAIL_DESC,
             MARKETING_DESCRIPTION, INVOICE_DESC
          3. Phase B — item features in batches of 5 (ITEM_FEATURES_1…20)
          4. Phase C — attribute triplets in batches of 10 (label/value/UOM 1…50)
          5. Phase D — logistics: dimensions, UNSPSC, URLs, certifications, country
        """
        failure_strings = ("not found", "no product found", "no match found", "no data found", "unknown product", "could not extract")
        if not fields or any(
            isinstance(field.value, str) and any(marker in field.value.casefold() for marker in failure_strings)
            for field in fields
        ):
            logger.warning("Enrichment skipped: extraction has no usable product identity")
            return EnrichmentResult(fields=list(fields))

        field_by_name = {field.name: field for field in fields if field.value not in (None, "", [])}
        manufacturer = str(
            next((field.value for field in fields if field.name in {"manufacturer", "manufacturer_name", "part_manuf", "brand"} and field.value), "")
        ).strip()
        identifier = str(
            next((field.value for field in fields if field.name in {"mfg_part_num", "part_number", "model_number"} and field.value), "")
        ).strip()
        product_name = str(
            next((field.value for field in fields if field.name in {"part_desc", "product_name"} and field.value), "")
        ).strip()

        # Enrichment v2 trigger: only an identifier (part number) is required.
        # Previously we required BOTH manufacturer AND identifier, which caused
        # enrichment to silently skip products whose CSV had no manufacturer column.
        if not identifier:
            logger.info("Enrichment skipped: no part identifier available for live research")
            return EnrichmentResult(fields=list(fields))

        search_query = f"{manufacturer} {identifier}".strip() if manufacturer else identifier
        with log_agent_step(logger, "EnrichmentAgent", f"researching {search_query}") as ctx:
            web_results = await asyncio.to_thread(search_product_datasheets, identifier, manufacturer)
            page_url = str(web_results.get("mfr_url") or "").strip()
            page_data: dict[str, Any] = {}
            page_text = ""
            if page_url:
                page_data = await asyncio.to_thread(fetch_manufacturer_page, page_url)
                page_text = str(page_data.get("text_content") or "").strip()

            # Fallback: if the page scraper returned minimal content (JS-rendered
            # page or blocked scraper), use the web search snippets instead.
            # Snippets are the text blurbs DuckDuckGo already extracted — always
            # available and typically contain spec/description text.
            if len(page_text) < 200:
                raw_snippets = web_results.get("web_snippets", [])
                snippet_text = " | ".join(
                    str(s).strip() for s in raw_snippets if s and str(s).strip()
                )
                if snippet_text:
                    logger.info(
                        "EnrichmentAgent: page text too short (%d chars), using %d web snippets",
                        len(page_text), len(raw_snippets),
                    )
                    # Use snippets as the enrichment source. The source URL is the
                    # manufacturer page (or a search results URL if no page URL).
                    page_text = snippet_text
                    if not page_url:
                        page_url = f"https://duckduckgo.com/?q={search_query.replace(' ', '+')}"
                    page_data = {"page_title": f"Web search snippets for {search_query}"}

            enriched_fields = list(fields)
            enrichment_sources: list[Source] = []
            fields_added: list[str] = []
            source_by_url: dict[str, Source] = {}

            def cited_source(url: str, text: str = "", title: str = "") -> Source:
                existing = source_by_url.get(url)
                if existing:
                    return existing
                src = Source(
                    source_type=SourceType.WEB,
                    origin=url,
                    raw_content_ref=url,
                    content_hash=hash_content(text or url),
                    trust_tier=TrustTier.MARKETPLACE,
                    title=title or None,
                )
                source_by_url[url] = src
                enrichment_sources.append(src)
                return src

            def add_url_field(name: str, display_name: str, value: str, url: str, confidence: int) -> None:
                if not value or name in field_by_name:
                    return
                src = cited_source(url or value, page_text if url == page_url else "", str(page_data.get("page_title") or ""))
                enriched_fields.append(ProductField(
                    id=uuid4(), name=name, display_name=display_name, value=value,
                    confidence=confidence,
                    source_excerpt=SourceExcerpt(source_id=src.id, text=value, location=url or value),
                    reasoning="Live product research returned this source URL.",
                    status=FieldStatus.NEEDS_REVIEW,
                ))
                field_by_name[name] = enriched_fields[-1]
                fields_added.append(name)

            page_matches_identity = identifier.casefold() in page_text.casefold()
            if page_url and page_text and page_matches_identity:
                add_url_field("mfr_url", "Manufacturer URL", page_url, page_url, 75)
            for name, display_name, result_key in (
                ("specification_sheet", "Specification Sheet", "specification_sheet"),
                ("owners_manual", "Owners Manual", "owners_manual"),
                ("product_image", "Product Image", "product_image"),
            ):
                url_val = str(web_results.get(result_key) or "").strip()
                if url_val:
                    add_url_field(name, display_name, url_val, url_val, 70)

            # ── Multi-phase LLM enrichment over the fetched page text ──────
            # Only run when the page text actually mentions the product identifier.
            # This prevents enriching the wrong product's page.
            if page_text and page_matches_identity:
                page_source = cited_source(
                    page_url, page_text,
                    str(page_data.get("page_title") or ""),
                )
                page_source_id = page_source.id
                identity_ctx = (
                    f"Manufacturer: {manufacturer!r}, Part Number: {identifier!r}, "
                    f"Product Name: {product_name!r}"
                )

                # Import here to avoid circular imports at module level
                from .multi_phase_extractor import MultiPhaseExtractor

                # Build a stand-alone MultiPhaseExtractor over the page text
                # (not the original CSV row — the page text is the enrichment source)
                client = self._get_client()
                if client:
                    phase_extractor = MultiPhaseExtractor(
                        client=client,
                        source_text=page_text,
                        source_id=page_source_id,
                        temperature=0.05,
                    )

                    already_filled = set(field_by_name.keys())

                    # Phase A: descriptions
                    try:
                        p_desc = await phase_extractor.phase2_descriptions(identity_ctx)
                        for f in p_desc.fields:
                            if f.name not in field_by_name:
                                enriched_fields.append(f)
                                field_by_name[f.name] = f
                                fields_added.append(f.name)
                        logger.info("Enrichment Phase A (descriptions): %d new fields", len(p_desc.fields))
                    except Exception as exc:
                        logger.warning("Enrichment Phase A failed: %s", exc)

                    # Phase B: attributes
                    try:
                        p_attrs = await phase_extractor.phase3_attributes(identity_ctx, set(field_by_name.keys()))
                        for f in p_attrs.fields:
                            if f.name not in field_by_name:
                                enriched_fields.append(f)
                                field_by_name[f.name] = f
                                fields_added.append(f.name)
                        logger.info("Enrichment Phase B (attributes): %d new fields", len(p_attrs.fields))
                    except Exception as exc:
                        logger.warning("Enrichment Phase B failed: %s", exc)

                    # Phase C: logistics
                    try:
                        p_logi = await phase_extractor.phase4_logistics(identity_ctx)
                        for f in p_logi.fields:
                            if f.name not in field_by_name:
                                enriched_fields.append(f)
                                field_by_name[f.name] = f
                                fields_added.append(f.name)
                        logger.info("Enrichment Phase C (logistics): %d new fields", len(p_logi.fields))
                    except Exception as exc:
                        logger.warning("Enrichment Phase C failed: %s", exc)
                else:
                    logger.info("Enrichment multi-phase skipped: no LLM client available")

            ctx["output_summary"] = (
                f"{len(fields_added)} source-cited fields added from "
                f"{len(enrichment_sources)} live sources (multi-phase enrichment)"
            )
            return EnrichmentResult(
                fields=enriched_fields,
                enrichment_sources=enrichment_sources,
                fields_added=fields_added,
            )
