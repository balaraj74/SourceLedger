"""Main Agents Execution Pipeline — SourceLedger.

Orchestrates the full multi-agent pipeline:
1. Ingestion Agent (Normalizes raw text / PDF / Web content)
2. Extraction Agent (Schema-locked structured field extraction)
3. Enrichment Agent (Fills gaps & taxonomy defaults via ADK tools)
4. Validation Agent (Scores confidence & routes uncertain fields)
5. Explainability Layer (Attaches citation & reasoning provenance)

Includes a Round-Robin Gemini API Key Rotator to switch across multiple API keys
(GOOGLE_API_KEY1..8) and handle expired/exhausted keys gracefully.
"""

import asyncio
import os
from typing import Any, Optional
from uuid import UUID, uuid4

from google import genai

from ..config import settings
from ..models.product_record import ProductRecord, SourceType, TrustTier
from ..utils.logging import get_logger, log_agent_step

from .enrichment_agent import EnrichmentAgent
from .explainability_layer import ExplainabilityLayer
from .extraction_agent import ExtractionAgent
from .ingestion_agent import IngestionAgent
from .validation_agent import ValidationAgent

logger = get_logger("AgentsMainPipeline")


from .key_rotator import APIKeyRotator, key_rotator


class AgentPipeline:
    """Full execution pipeline combining all Google ADK backend agents."""

    def __init__(self) -> None:
        self.ingestion_agent = IngestionAgent()
        self.extraction_agent = ExtractionAgent()
        self.enrichment_agent = EnrichmentAgent()
        self.validation_agent = ValidationAgent()
        self.explainability_layer = ExplainabilityLayer()
        self.key_rotator = key_rotator

    def get_rotated_api_key(self) -> Optional[str]:
        """Fetch the next rotated API key and configure runtime environment."""
        api_key = self.key_rotator.get_next_key()
        if api_key:
            os.environ["GOOGLE_API_KEY"] = api_key
        return api_key

    async def run(
        self,
        source_type: SourceType,
        content: str,
        category: str = "industrial_pump",
        filename: str | None = None,
        trust_tier: TrustTier = TrustTier.MARKETPLACE,
    ) -> ProductRecord:
        """Run the complete 5-stage agent pipeline with round-robin key switching.

        Execution stages:
        1. Ingestion Agent
        2. Extraction Agent
        3. Enrichment Agent
        4. Validation Agent
        5. Explainability Layer
        """
        with log_agent_step(logger, "AgentPipeline", "executing full pipeline") as ctx:
            # Step 1: Ingestion
            current_key = self.get_rotated_api_key()
            logger.info("Stage 1: IngestionAgent starting (Key: %s...)", current_key[:8] if current_key else "demo")
            ingestion_res = await self.ingestion_agent.ingest(
                source_type=source_type,
                content=content,
                filename=filename,
                trust_tier=trust_tier,
            )

            # Step 2: Extraction
            current_key = self.get_rotated_api_key()
            logger.info("Stage 2: ExtractionAgent starting (Key: %s...)", current_key[:8] if current_key else "demo")
            extraction_res = await self.extraction_agent.extract(
                raw_text=ingestion_res.raw_text,
                category=category,
                source_id=ingestion_res.source.id,
            )

            if extraction_res.status == "extraction_failed":
                raise ValueError(extraction_res.reason or "Extraction failed: source contains no identifiable product information")

            # Step 3: Enrichment
            current_key = self.get_rotated_api_key()
            logger.info("Stage 3: EnrichmentAgent starting (Key: %s...)", current_key[:8] if current_key else "demo")
            enrichment_res = await self.enrichment_agent.enrich(
                fields=extraction_res.fields,
                category=category,
                source_id=ingestion_res.source.id,
            )

            # Step 4: Validation
            current_key = self.get_rotated_api_key()
            logger.info("Stage 4: ValidationAgent starting (Key: %s...)", current_key[:8] if current_key else "demo")
            validation_res = await self.validation_agent.validate(
                fields=enrichment_res.fields,
                category=category,
            )

            # Step 5: Explainability
            current_key = self.get_rotated_api_key()
            logger.info("Stage 5: ExplainabilityLayer starting (Key: %s...)", current_key[:8] if current_key else "demo")
            annotated_fields = await self.explainability_layer.annotate(
                validation_res.fields
            )

            product = ProductRecord(
                id=uuid4(),
                name=extraction_res.product_name,
                category=category,
                fields=annotated_fields,
                source_ids=[
                    ingestion_res.source.id,
                    *(source.id for source in enrichment_res.enrichment_sources),
                ],
                confidence_overall=validation_res.confidence_overall,
            )

            ctx["output_summary"] = (
                f"'{product.name}' — {len(product.fields)} fields, "
                f"confidence={product.confidence_overall}"
            )
            return product


# Module-level default pipeline instance
main_pipeline = AgentPipeline()


async def main() -> None:
    """Sample CLI entrypoint to test main pipeline execution."""
    sample_text = (
        "Grundfos CR 15-3 Centrifugal Pump\n"
        "Flow Rate: 15.0 m3/h\n"
        "Head Pressure: 45.0 m\n"
        "Power Rating: 5.5 kW\n"
        "Material: Stainless Steel 316\n"
    )

    print("--- Starting SourceLedger Agents Main Pipeline ---")
    pipeline = AgentPipeline()
    product = await pipeline.run(
        source_type=SourceType.WEB,
        content=sample_text,
        category="industrial_pump",
    )

    print("\n--- Pipeline Execution Result ---")
    print(f"Product ID: {product.id}")
    print(f"Product Name: {product.name}")
    print(f"Category: {product.category}")
    print(f"Overall Confidence: {product.confidence_overall}%")
    print(f"Total Fields Extracted: {len(product.fields)}")
    for f in product.fields:
        print(f"  - {f.display_name} ({f.name}): {f.value} {f.unit or ''} [Conf: {f.confidence}%]")


if __name__ == "__main__":
    asyncio.run(main())
