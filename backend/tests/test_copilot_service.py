"""Unit tests for Catalog Copilot & Multi-Agent Data Chat Engine."""

import pytest
import tempfile
from uuid import uuid4

from src.db.store import ProductStore
from src.models.product_record import ProductRecord, ProductField, FieldStatus, SourceExcerpt
from src.services.copilot_service import CopilotEngine


@pytest.mark.asyncio
async def test_copilot_chat_grounding_and_tool_execution():
    """Verify CopilotEngine executes multi-agent tools and grounds catalog responses."""
    test_store = ProductStore(tempfile.mktemp(suffix=".db"))
    engine = CopilotEngine(store_instance=test_store)

    p1 = ProductRecord(
        id=uuid4(),
        name="Goulds e-SV Vertical Pump",
        category="industrial_pump",
        confidence_overall=92,
        mfg_part_num="10SV02F007M",
        fields=[
            ProductField(
                name="flow_rate",
                display_name="Flow Rate",
                value="45 m³/h",
                confidence=90,
                status=FieldStatus.AUTO_COMMITTED,
                reasoning="OEM spec sheet",
                source_excerpt=SourceExcerpt(source_id=uuid4(), text="45 m³/h"),
            )
        ],
    )
    await test_store.save_product(p1)

    # Execute Copilot natural language chat query
    res = await engine.chat("Show products with flow rate specifications")

    assert res["question"] == "Show products with flow rate specifications"
    assert "answer" in res
    assert isinstance(res["executed_tools"], list)
    assert isinstance(res["cited_skus"], list)
    assert isinstance(res["data_preview"], list)
    assert len(res["data_preview"]) >= 1
    assert res["data_preview"][0]["sku"] == "10SV02F007M"


@pytest.mark.asyncio
async def test_copilot_suggestions():
    """Verify get_suggestions returns quick-start prompt chips."""
    test_store = ProductStore(tempfile.mktemp(suffix=".db"))
    engine = CopilotEngine(store_instance=test_store)

    suggestions = await engine.get_suggestions()
    assert len(suggestions) >= 3
    assert "prompt" in suggestions[0]
    assert "label" in suggestions[0]
