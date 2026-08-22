"""Unit tests for Phase 12 Stretch Features (JSON-LD export, bulk correction, Catalog Q&A)."""

import pytest
from uuid import uuid4
from src.db.store import store
from src.models.product_record import FieldStatus, ProductField, ProductRecord, SourceExcerpt
from src.services.jsonld_exporter import export_product_to_jsonld
from src.services.catalog_qa_service import answer_catalog_question


@pytest.mark.asyncio
async def test_jsonld_export_structure():
    """Verify export_product_to_jsonld generates valid schema.org/Product JSON-LD."""
    p = ProductRecord(
        id=uuid4(),
        name="DeWalt Rotary Hammer Drill",
        category="power_tool",
        confidence_overall=92,
        mfg_part_num="DCH273B",
        fields=[
            ProductField(name="manufacturer", display_name="Manufacturer", value="DeWalt", confidence=95, reasoning="OEM", source_excerpt=SourceExcerpt(source_id=uuid4(), text="DeWalt")),
            ProductField(name="short_desc", display_name="Description", value="Heavy-duty 20V MAX SDS Plus drill", confidence=90, reasoning="OEM spec", source_excerpt=SourceExcerpt(source_id=uuid4(), text="20V MAX")),
            ProductField(name="list_price", display_name="List Price", value="$219.00", confidence=88, reasoning="Distributor catalog", source_excerpt=SourceExcerpt(source_id=uuid4(), text="$219.00")),
        ]
    )
    
    jsonld = export_product_to_jsonld(p)
    assert jsonld["@context"] == "https://schema.org/"
    assert jsonld["@type"] == "Product"
    assert jsonld["name"] == "DeWalt Rotary Hammer Drill"
    assert jsonld["sku"] == "DCH273B"
    assert jsonld["brand"]["name"] == "DeWalt"
    assert jsonld["offers"]["price"] == "219.00"


@pytest.mark.asyncio
async def test_catalog_qa_grounded_response():
    """Verify answer_catalog_question returns structured grounded Q&A results."""
    import tempfile
    from src.db.store import ProductStore
    test_store = ProductStore(tempfile.mktemp(suffix=".db"))

    p = ProductRecord(
        id=uuid4(),
        name="Goulds e-SV Vertical Multistage Pump",
        category="industrial_pump",
        confidence_overall=95,
        mfg_part_num="10SV02F007M",
        fields=[
            ProductField(name="flow_rate", display_name="Flow Rate", value="45 m³/h", confidence=90, reasoning="Spec", source_excerpt=SourceExcerpt(source_id=uuid4(), text="45 m³/h")),
        ]
    )
    await test_store.save_product(p)
    
    res = await answer_catalog_question("Which pumps have flow rate over 40 m³/h?", store_instance=test_store)
    assert "question" in res
    assert "answer" in res
    assert isinstance(res["cited_skus"], list)
