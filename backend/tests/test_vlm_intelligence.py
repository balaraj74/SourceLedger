"""Unit tests for Phase 9: Vision-Language Document Intelligence."""

import pytest
from uuid import uuid4
from src.agents.extraction_agent import ExtractionAgent
from src.models.product_record import FieldStatus


@pytest.mark.asyncio
async def test_vlm_extraction_method_tracking():
    """Verify VLM extractions track extraction_method and bounding_box in SourceExcerpt."""
    agent = ExtractionAgent()
    src_id = uuid4()
    
    result = await agent.extract_vlm_image_attributes(
        image_bytes=b"fake_image_bytes",
        source_id=src_id,
        category="generic",
        mime_type="image/png",
        is_blurry=False,
    )
    
    assert result.status == "completed"
    assert len(result.fields) >= 1
    
    field = result.fields[0]
    assert field.source_excerpt is not None
    assert field.source_excerpt.extraction_method in ("vlm_image", "vlm_pdf_table")
    assert field.source_excerpt.bounding_box is not None


@pytest.mark.asyncio
async def test_blurry_scan_graceful_degradation():
    """Verify low-legibility/blurry visual scans degrade confidence and route to NEEDS_REVIEW."""
    agent = ExtractionAgent()
    src_id = uuid4()
    
    result = await agent.extract_vlm_image_attributes(
        image_bytes=b"blurry_scan_bytes",
        source_id=src_id,
        category="generic",
        mime_type="image/jpeg",
        is_blurry=True,  # Low legibility flag
    )
    
    assert len(result.fields) >= 1
    for f in result.fields:
        assert f.confidence <= 45
        assert f.status == FieldStatus.NEEDS_REVIEW
        assert "degraded" in f.reasoning.lower() or "blurry" in f.reasoning.lower() or "needs_review" in f.reasoning.lower()
