"""Unit tests for Phase 8: Product Knowledge Graph (GraphAgent)."""

import pytest
from uuid import uuid4
from src.agents.graph_agent import GraphAgent
from src.db.store import store
from src.models.product_record import FieldStatus, ProductField, ProductRecord, SourceExcerpt


@pytest.mark.asyncio
async def test_variant_family_graph_relationship_detection():
    """Verify GraphAgent detects variant family relationships for prefix/suffix matching SKUs."""
    import tempfile
    from src.db.store import ProductStore
    test_store = ProductStore(tempfile.mktemp(suffix=".db"))
    agent = GraphAgent(store_instance=test_store)
    
    p1 = ProductRecord(
        id=uuid4(),
        name="DCB520ASTS08G",
        category="power_tool",
        confidence_overall=90,
        mfg_part_num="DCB520ASTS08G",
        fields=[
            ProductField(name="manufacturer", display_name="Manufacturer", value="DeWalt", confidence=95, reasoning="OEM", source_excerpt=SourceExcerpt(source_id=uuid4(), text="DeWalt")),
        ]
    )
    
    p2 = ProductRecord(
        id=uuid4(),
        name="DCB520ASTS08G-P120",
        category="power_tool",
        confidence_overall=88,
        mfg_part_num="DCB520ASTS08G-P120",
        fields=[
            ProductField(name="manufacturer", display_name="Manufacturer", value="DeWalt", confidence=95, reasoning="OEM", source_excerpt=SourceExcerpt(source_id=uuid4(), text="DeWalt")),
        ]
    )

    await test_store.save_product(p1)
    await test_store.save_product(p2)
    
    relationships = await agent.analyze_catalog([p1, p2])
    
    assert len(relationships) >= 1
    rel = relationships[0]
    assert rel.relationship_type == "variant_of"
    assert rel.confidence == 95
    assert rel.reasoning is not None and len(rel.reasoning) > 0
    assert "DCB520ASTS08G" in rel.source_sku
    
    # Verify persisted in SQLite
    stored_rels = test_store.list_product_relationships("DCB520ASTS08G")
    assert len(stored_rels) >= 1


@pytest.mark.asyncio
async def test_unvalidated_records_excluded_from_graph():
    """Verify records below confidence threshold (<60) produce no graph edges."""
    agent = GraphAgent()
    
    p_low = ProductRecord(
        id=uuid4(),
        name="UNVAL-001",
        category="generic",
        confidence_overall=30,  # Below threshold!
        mfg_part_num="UNVAL-001",
        fields=[]
    )
    
    p_valid = ProductRecord(
        id=uuid4(),
        name="UNVAL-001-P2",
        category="generic",
        confidence_overall=90,
        mfg_part_num="UNVAL-001-P2",
        fields=[]
    )
    
    relationships = await agent.analyze_catalog([p_low, p_valid])
    assert len(relationships) == 0
