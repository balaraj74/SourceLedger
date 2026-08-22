"""Unit tests for Phase 7: Cross-Source Conflict Resolution (ValidationAgent)."""

import pytest
from uuid import uuid4
from src.agents.validation_agent import ValidationAgent
from src.db.store import store
from src.models.product_record import FieldStatus, ProductField, SourceExcerpt
from src.models.schemas import FieldCandidate, FieldConflict


@pytest.mark.asyncio
async def test_cross_source_conflict_detection():
    """Verify >= 2 conflicting sources produce a FieldConflict record."""
    agent = ValidationAgent()
    prod_id = uuid4()
    
    validated_fields = [
        ProductField(
            name="flow_rate",
            display_name="Flow Rate",
            value="150 GPM",
            confidence=85,
            source_excerpt=SourceExcerpt(source_id=uuid4(), text="Flow rate: 150 GPM", page=1),
            reasoning="Extracted from spec sheet",
            status=FieldStatus.AUTO_COMMITTED,
        )
    ]
    
    candidates = {
        "flow_rate": [
            FieldCandidate(value="150 GPM", source_id="src_1", trust_tier=1, raw_excerpt="OEM Spec Sheet: 150 GPM"),
            FieldCandidate(value="200 GPM", source_id="src_2", trust_tier=3, raw_excerpt="Distributor Catalog: 200 GPM"),
        ]
    }
    
    import tempfile
    from src.db.store import ProductStore
    test_store = ProductStore(tempfile.mktemp(suffix=".db"))

    fields_res, conflicts = agent.detect_and_resolve_conflicts(prod_id, candidates, validated_fields, store_instance=test_store)
    
    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict.product_id == prod_id
    assert conflict.field_name == "flow_rate"
    assert len(conflict.candidates) == 2
    assert "Tier 1" in conflict.resolution_reasoning
    
    # Verify persisted to SQLite
    stored_conflicts = test_store.list_field_conflicts(prod_id)
    assert len(stored_conflicts) == 1
    assert stored_conflicts[0].field_name == "flow_rate"


@pytest.mark.asyncio
async def test_single_source_zero_conflict_regression():
    """Verify zero FieldConflict rows exist for fields with only one source."""
    agent = ValidationAgent()
    prod_id = uuid4()
    
    validated_fields = [
        ProductField(
            name="material",
            display_name="Material",
            value="316 Stainless Steel",
            confidence=90,
            source_excerpt=SourceExcerpt(source_id=uuid4(), text="Material: 316SS", page=1),
            reasoning="Extracted from spec sheet",
            status=FieldStatus.AUTO_COMMITTED,
        )
    ]
    
    candidates = {
        "material": [
            FieldCandidate(value="316 Stainless Steel", source_id="src_1", trust_tier=1, raw_excerpt="OEM Spec Sheet: 316SS")
        ]
    }
    
    fields_res, conflicts = agent.detect_and_resolve_conflicts(prod_id, candidates, validated_fields)
    assert len(conflicts) == 0


@pytest.mark.asyncio
async def test_tied_trust_tier_forces_needs_review():
    """Verify equal trust tier conflict forces NEEDS_REVIEW status."""
    agent = ValidationAgent()
    prod_id = uuid4()
    
    target_field = ProductField(
        name="max_pressure",
        display_name="Max Pressure",
        value="100 PSI",
        confidence=85,
        source_excerpt=SourceExcerpt(source_id=uuid4(), text="Max pressure: 100 PSI", page=1),
        reasoning="Extracted from OEM sheet A",
        status=FieldStatus.AUTO_COMMITTED,
    )
    
    candidates = {
        "max_pressure": [
            FieldCandidate(value="100 PSI", source_id="src_oem_a", trust_tier=1, raw_excerpt="OEM Spec Sheet A: 100 PSI"),
            FieldCandidate(value="150 PSI", source_id="src_oem_b", trust_tier=1, raw_excerpt="OEM Spec Sheet B: 150 PSI"),
        ]
    }
    
    fields_res, conflicts = agent.detect_and_resolve_conflicts(prod_id, candidates, [target_field])
    
    assert len(conflicts) == 1
    assert target_field.status == FieldStatus.NEEDS_REVIEW
    assert "disagreement" in target_field.reasoning.lower()
