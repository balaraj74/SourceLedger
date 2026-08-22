"""Unit tests for Phase 10: Confidence-Based Active Learning."""

import pytest
from uuid import uuid4
from src.agents.validation_agent import ValidationAgent
from src.db.store import store
from src.models.product_record import FieldStatus, ProductField, SourceExcerpt
from src.models.schemas import CategorySchema, CategoryFieldDef, FieldType, CorrectionPattern


@pytest.mark.asyncio
async def test_active_learning_confidence_adjustment():
    """Verify reviewer corrections adjust future confidence scoring in ValidationAgent."""
    import tempfile
    from src.db.store import ProductStore
    test_store = ProductStore(tempfile.mktemp(suffix=".db"))
    agent = ValidationAgent()
    
    # 1. Seed 3 reviewer correction patterns for industrial_pump flow_rate
    pat = CorrectionPattern(
        category="industrial_pump",
        field_name="flow_rate",
        manufacturer="Goulds Pumps",
        correction_count=4,  # 4 reviewer corrections!
        avg_confidence_before_correction=85.0,
    )
    test_store.save_correction_pattern(pat)
    
    # 2. Validate new flow_rate field for industrial_pump
    schema = CategorySchema(
        category_key="industrial_pump",
        display_name="Industrial Pump",
        fields=[
            CategoryFieldDef(name="flow_rate", display_name="Flow Rate", field_type=FieldType.STRING, required=True, description="Flow rate")
        ]
    )
    
    field = ProductField(
        name="flow_rate",
        display_name="Flow Rate",
        value="120 GPM",
        confidence=90,
        source_excerpt=SourceExcerpt(source_id=uuid4(), text="Flow rate: 120 GPM"),
        reasoning="Extracted from datasheet",
        status=FieldStatus.AUTO_COMMITTED,
    )
    
    validated = agent._validate_field(field, schema, threshold=85, store_instance=test_store)
    
    # Verify active learning penalty was applied!
    assert validated.confidence < 90
    assert validated.status == FieldStatus.NEEDS_REVIEW
    assert "Active learning adjustment" in validated.reasoning
