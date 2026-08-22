"""Tests for the Validation Agent — second highest priority test suite.

Tests confidence scoring, status routing (auto_committed vs needs_review),
type checking, and completeness validation. These catch the most dangerous
runtime bugs: wrong confidence scoring and silent auto-commits of bad data.
"""

import pytest
from uuid import uuid4

from src.agents.validation_agent import ValidationAgent
from src.models.product_record import (
    FieldStatus,
    ProductField,
    SourceExcerpt,
)
from src.models.schemas import INDUSTRIAL_PUMP_SCHEMA


@pytest.fixture
def agent():
    return ValidationAgent()


def _make_field(
    name: str = "manufacturer",
    display_name: str = "Manufacturer",
    value: object = "Grundfos",
    confidence: int = 80,
    excerpt: str = "Grundfos CR 15-3",
    reasoning: str = "Found in title",
    unit: str | None = None,
) -> ProductField:
    """Helper to create a ProductField for testing."""
    return ProductField(
        id=uuid4(),
        name=name,
        display_name=display_name,
        value=value,
        unit=unit,
        confidence=confidence,
        source_excerpt=SourceExcerpt(
            source_id=uuid4(),
            text=excerpt,
        ),
        reasoning=reasoning,
        status=FieldStatus.NEEDS_REVIEW,
    )


class TestValidationAgent:
    """Tests that validation correctly scores and routes fields."""

    @pytest.mark.asyncio
    async def test_high_confidence_field_auto_committed(self, agent):
        """Fields above threshold should be auto-committed."""
        field = _make_field(confidence=85)
        result = await agent.validate([field], "industrial_pump")

        assert result.fields[0].status == FieldStatus.AUTO_COMMITTED
        assert result.auto_committed_count == 1

    @pytest.mark.asyncio
    async def test_low_confidence_field_needs_review(self, agent):
        """Fields below threshold should route to review."""
        field = _make_field(confidence=40)
        result = await agent.validate([field], "industrial_pump")

        assert result.fields[0].status == FieldStatus.NEEDS_REVIEW
        assert result.needs_review_count == 1

    @pytest.mark.asyncio
    async def test_null_value_gets_zero_confidence(self, agent):
        """A field with null value should get 0 confidence."""
        field = _make_field(value=None, confidence=80)
        result = await agent.validate([field], "industrial_pump")

        assert result.fields[0].confidence == 0
        assert result.fields[0].status == FieldStatus.NEEDS_REVIEW

    @pytest.mark.asyncio
    async def test_empty_string_value_gets_zero_confidence(self, agent):
        """A field with empty string value should get 0 confidence."""
        field = _make_field(value="", confidence=80)
        result = await agent.validate([field], "industrial_pump")

        assert result.fields[0].confidence == 0
        assert result.fields[0].status == FieldStatus.NEEDS_REVIEW

    @pytest.mark.asyncio
    async def test_overall_confidence_is_average(self, agent):
        """Overall confidence should be average of all extracted fields."""
        fields = [
            _make_field(name="manufacturer", confidence=90),
            _make_field(name="model_number", display_name="Model Number", confidence=80),
            _make_field(name="pump_type", display_name="Pump Type", confidence=30),
        ]
        result = await agent.validate(fields, "industrial_pump")

        assert result.confidence_overall == 67, (
            "Overall confidence should be the average across all fields"
        )

    @pytest.mark.asyncio
    async def test_type_mismatch_penalizes_confidence(self, agent):
        """A type mismatch should reduce confidence."""
        # flow_rate should be NUMBER but we pass a string
        field = _make_field(
            name="flow_rate",
            display_name="Flow Rate",
            value="fifteen",  # Should be a number
            confidence=80,
            unit="m³/h",
        )
        result = await agent.validate([field], "industrial_pump")

        assert result.fields[0].confidence < 80, (
            "Type mismatch should reduce confidence"
        )

    @pytest.mark.asyncio
    async def test_weak_source_excerpt_penalizes_confidence(self, agent):
        """A weak/missing source excerpt should reduce confidence."""
        field = _make_field(
            confidence=80,
            excerpt="(not found in source text)",
        )
        result = await agent.validate([field], "industrial_pump")

        assert result.fields[0].confidence < 80, (
            "Weak source excerpt should reduce confidence"
        )

    @pytest.mark.asyncio
    async def test_field_not_in_schema_gets_low_confidence(self, agent):
        """A field not in the schema should get capped confidence."""
        field = _make_field(
            name="nonexistent_field",
            display_name="Not Real",
            confidence=90,
            excerpt="",
        )

        result = await agent.validate([field], "industrial_pump")

        assert result.fields[0].confidence <= 30
        assert result.fields[0].status == FieldStatus.NEEDS_REVIEW

    @pytest.mark.asyncio
    async def test_threshold_boundary_exact(self, agent):
        """A field exactly at threshold should be auto-committed."""
        field = _make_field(confidence=70)  # Default threshold is 70
        result = await agent.validate([field], "industrial_pump")

        assert result.fields[0].status == FieldStatus.AUTO_COMMITTED

    @pytest.mark.asyncio
    async def test_threshold_boundary_just_below(self, agent):
        """A field one below threshold should need review."""
        field = _make_field(confidence=69)
        result = await agent.validate([field], "industrial_pump")

        assert result.fields[0].status == FieldStatus.NEEDS_REVIEW

    @pytest.mark.asyncio
    async def test_all_fields_validated(self, agent):
        """Every input field should appear in the output."""
        fields = [
            _make_field(name="manufacturer", confidence=90),
            _make_field(name="model_number", display_name="Model Number", confidence=85),
            _make_field(name="pump_type", display_name="Pump Type", value="centrifugal", confidence=75),
        ]
        result = await agent.validate(fields, "industrial_pump")

        assert len(result.fields) == 3

    @pytest.mark.asyncio
    async def test_unknown_category_marks_all_for_review(self, agent):
        """If the category schema is unknown, all fields should need review."""
        fields = [_make_field(confidence=90)]
        result = await agent.validate(fields, "nonexistent_category")

        assert result.fields[0].status == FieldStatus.NEEDS_REVIEW
        assert result.confidence_overall == 0

    @pytest.mark.asyncio
    async def test_mixed_confidence_correct_counts(self, agent):
        """Verify the counts of auto_committed vs needs_review are accurate."""
        fields = [
            _make_field(name="manufacturer", confidence=90),  # auto
            _make_field(name="model_number", display_name="Model Number", confidence=85),  # auto
            _make_field(name="pump_type", display_name="Pump Type", confidence=40),  # review
            _make_field(name="flow_rate", display_name="Flow Rate", value=15.0, confidence=20, unit="m³/h"),  # review
        ]
        result = await agent.validate(fields, "industrial_pump")

        assert result.auto_committed_count == 2
        assert result.needs_review_count == 2
