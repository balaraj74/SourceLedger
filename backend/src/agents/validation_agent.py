"""Validation Agent — conflict resolution, confidence scoring, review routing using Google ADK.

Detects conflicts between sources, resolves using trust-tier ranking,
assigns calibrated confidence scores, and routes uncertain fields to
human review. Nothing below the confidence threshold is auto-committed.

Architectural rule: the system is designed to know what it doesn't know.
Low-confidence or conflicting data is never guessed past — it is surfaced.
"""

from typing import Any, Optional
from uuid import UUID

from google import genai

from ..config import settings
from ..db.store import store
from ..models.pipeline import ValidationResult
from ..models.product_record import FieldStatus, ProductField
from ..models.schemas import (
    CategorySchema,
    FieldCandidate,
    FieldConflict,
    FieldType,
    get_category_schema,
)
from ..utils.logging import get_logger, log_agent_step

logger = get_logger("ValidationAgent")


def validate_field_type_and_source(
    field_name: str, value: Any, expected_type: str, excerpt: str
) -> dict:
    """Helper tool function for validating field value types and source excerpt strength.

    Args:
        field_name: Machine key of the field.
        value: Extracted value.
        expected_type: Expected schema field type.
        excerpt: Extracted source excerpt text.

    Returns:
        dict with validation flags and confidence penalty deductions.
    """
    has_excerpt = bool(excerpt and excerpt.strip() and not excerpt.startswith("("))
    penalty = 0
    reasons = []

    if not has_excerpt:
        penalty += 15
        reasons.append("Weak or missing source excerpt")

    return {
        "field_name": field_name,
        "valid_source": has_excerpt,
        "confidence_penalty": penalty,
        "issues": reasons,
    }


def assess_record_completeness(category: str, field_names: list[str]) -> dict:
    """Helper tool function for assessing category schema completeness.

    Args:
        category: Product category key.
        field_names: Names of fields present in the record.

    Returns:
        dict with missing required fields list and completeness score.
    """
    schema = get_category_schema(category)
    if not schema:
        return {"valid": False, "missing_required": []}

    present = set(field_names)
    required = set(schema.required_field_names)
    missing = list(required - present)

    return {
        "valid": len(missing) == 0,
        "missing_required": missing,
        "completion_ratio": len(present) / max(1, len(schema.fields)),
    }


class ValidationAgent:
    """Validates extracted fields, scores confidence, and routes to review using Google ADK.

    This agent is the gatekeeper between raw extraction and committed
    catalog data. Its core job is ensuring the system never silently
    guesses past ambiguity.
    """

    def __init__(self) -> None:
        self._adk_agent = None

    @property
    def adk_agent(self) -> Any:
        """Expose the underlying Agent instance."""
        return self._adk_agent or self

    async def validate(
        self,
        fields: list[ProductField],
        category: str,
    ) -> ValidationResult:
        """Validate fields, adjust confidence, and set commit/review status."""
        from ..models.schemas import CATEGORY_REGISTRY
        schema = get_category_schema(category)
        if not schema or (category and category not in ("generic", "unknown") and category not in CATEGORY_REGISTRY):
            # Without a registered schema, mark everything for review
            for f in fields:
                f.status = FieldStatus.NEEDS_REVIEW
            return ValidationResult(
                fields=fields,
                confidence_overall=0,
                needs_review_count=len(fields),
            )

        with log_agent_step(logger, "ValidationAgent", f"validating {category}") as ctx:
            validated_fields: list[ProductField] = []
            conflicts: list[dict] = []
            threshold = settings.confidence_threshold

            for field in fields:
                validated = self._validate_field(field, schema, threshold)
                validated_fields.append(validated)

            # Check schema completeness — penalize missing required fields
            validated_fields = self._check_completeness(
                validated_fields, schema
            )

            # Compute aggregate stats
            needs_review = sum(
                1 for f in validated_fields
                if f.status == FieldStatus.NEEDS_REVIEW
            )
            auto_committed = sum(
                1 for f in validated_fields
                if f.status == FieldStatus.AUTO_COMMITTED
            )

            # Overall confidence is the average across extracted fields
            non_zero_confidences = [f.confidence for f in validated_fields if f.value is not None]
            confidence_overall = (
                round(sum(non_zero_confidences) / len(non_zero_confidences))
                if non_zero_confidences
                else (round(sum(f.confidence for f in validated_fields) / len(validated_fields)) if validated_fields else 0)
            )

            ctx["output_summary"] = (
                f"{auto_committed} auto-committed, "
                f"{needs_review} needs review, "
                f"overall confidence={confidence_overall}"
            )

            return ValidationResult(
                fields=validated_fields,
                confidence_overall=confidence_overall,
                conflicts=conflicts,
                needs_review_count=needs_review,
                auto_committed_count=auto_committed,
            )

    def detect_and_resolve_conflicts(
        self,
        product_id: UUID,
        multi_source_candidates: dict[str, list[FieldCandidate]],
        validated_fields: list[ProductField],
        store_instance: Optional[Any] = None,
    ) -> tuple[list[ProductField], list[FieldConflict]]:
        """Detect disagreements across sources and persist conflict records (Phase 7)."""
        target_store = store_instance or store
        conflicts: list[FieldConflict] = []
        field_dict = {f.name: f for f in validated_fields}

        for field_name, candidates in multi_source_candidates.items():
            if len(candidates) < 2:
                # Regression rule: zero FieldConflict rows for single-source fields
                continue

            def _norm(val: Any) -> str:
                return " ".join(str(val).strip().lower().split())

            unique_vals = {_norm(c.value) for c in candidates if c.value is not None and str(c.value).strip()}
            if len(unique_vals) <= 1:
                # Sources agree — no conflict record needed
                continue

            # Cross-source conflict detected!
            sorted_candidates = sorted(candidates, key=lambda c: c.trust_tier)
            top_tier = sorted_candidates[0].trust_tier
            top_candidates = [c for c in sorted_candidates if c.trust_tier == top_tier]
            top_unique_vals = {_norm(c.value) for c in top_candidates}

            target_field = field_dict.get(field_name)

            if len(top_unique_vals) == 1:
                # Clear winner from higher trust tier!
                winner = top_candidates[0]
                resolution = str(winner.value)
                reasoning = f"Tier {winner.trust_tier} source outranks lower-tier candidates."
                resolved_confidence = min(95, max(60, 100 - (winner.trust_tier * 10)))
                if target_field:
                    target_field.value = winner.value
                    target_field.confidence = resolved_confidence
                    target_field.reasoning += f" | Conflict resolved: {reasoning}"
            else:
                # Tie at highest trust tier — force NEEDS_REVIEW
                winner = top_candidates[0]
                resolution = str(winner.value)
                reasoning = f"Cross-source disagreement between Tier {top_tier} sources — routed to human review."
                resolved_confidence = 50
                if target_field:
                    target_field.status = FieldStatus.NEEDS_REVIEW
                    target_field.confidence = min(target_field.confidence, resolved_confidence)
                    target_field.reasoning += f" | Conflict unresolved: {reasoning}"

            conflict = FieldConflict(
                product_id=product_id,
                field_name=field_name,
                candidates=candidates,
                resolution=resolution,
                resolution_reasoning=reasoning,
                resolved_confidence=resolved_confidence,
            )
            conflicts.append(conflict)
            target_store.save_field_conflict(conflict)

        return validated_fields, conflicts

    #: Known field alias mapping to schema standard field definitions
    _FIELD_ALIASES = {
        "mfg_part_num": "model_number",
        "part_number": "model_number",
        "part_num": "model_number",
        "item_number": "model_number",
        "sku": "model_number",
        "part_manuf": "manufacturer",
        "manufacturer_name": "manufacturer",
        "brand_name": "manufacturer",
        "brand": "manufacturer",
        "e1_brand": "manufacturer",
        "unilog_brand": "manufacturer",
        "dib_brand": "manufacturer",
        "part_desc": "short_desc",
        "product_name": "short_desc",
        "description": "short_desc",
        "name": "short_desc",
        "title": "short_desc",
        "item_name": "short_desc",
        "item_description": "short_desc",
        "unspsc_code": "unspsc",
        "certifications": "standards_approvals",
    }

    def _validate_field(
        self,
        field: ProductField,
        schema: CategorySchema,
        threshold: int,
        store_instance: Optional[Any] = None,
    ) -> ProductField:
        """Validate a single field: type-check, adjust confidence, set status."""
        target_name = self._FIELD_ALIASES.get(field.name.lower(), field.name)
        schema_field = next(
            (f for f in schema.fields if f.name in (field.name.lower(), target_name)), None
        )

        if schema_field:
            # Type validation for schema-matched or alias-matched field
            type_valid = self._check_type(field.value, schema_field.field_type)
            if not type_valid:
                field.confidence = max(0, field.confidence - 20)
                field.reasoning += (
                    f" | Type mismatch: expected {schema_field.field_type.value}, "
                    f"got {type(field.value).__name__}."
                )
        else:
            # Field is not explicitly listed in static category schema.
            # Check if this is a dynamic product attribute (e.g. attribute_*, item_features_*, UNSPSC, barcodes, custom CSV columns)
            # If it has a non-empty value and valid source excerpt/provenance, preserve its extracted confidence!
            is_dynamic_attribute = (
                field.name.startswith("attribute_")
                or field.name.startswith("item_features_")
                or field.name.startswith("feature_")
                or field.name in ("mfr_url", "specification_sheet", "owners_manual", "product_image", "upc", "ean", "gtin", "unspsc", "list_price")
                or (field.source_excerpt and field.source_excerpt.text and "CSV column" in field.source_excerpt.text)
            )

            has_valid_source = bool(
                field.source_excerpt
                and field.source_excerpt.text
                and not field.source_excerpt.text.startswith("(")
            )

            if is_dynamic_attribute or has_valid_source:
                # Valid product attribute with grounded source provenance — preserve confidence!
                pass
            else:
                # Truly ungrounded or unknown field without source backing
                field.confidence = min(field.confidence, 30)
                field.reasoning += " | Uncertified field without strong source backing."


        # Null/empty value check
        if field.value is None or field.value == "" or field.value == []:
            field.confidence = 0
            field.status = FieldStatus.NEEDS_REVIEW
            if schema_field and schema_field.required:
                field.reasoning += " | Required field with no value — needs manual entry."
            return field

        # Source quality check: empty excerpt lowers confidence
        if not field.source_excerpt.text or field.source_excerpt.text.startswith("("):
            field.confidence = max(0, field.confidence - 15)
            field.reasoning += " | Weak or missing source excerpt."

        # Active Learning Adjustment (Phase 10)
        try:
            target_store = store_instance or store
            patterns = target_store.get_correction_patterns()
            match_pat = next(
                (p for p in patterns if p.category == schema.category_key and p.field_name == field.name and p.correction_count >= 2),
                None
            )
            if match_pat:
                penalty = min(35, match_pat.correction_count * 5)
                field.confidence = max(0, field.confidence - penalty)
                field.reasoning += f" | Active learning adjustment: lowered confidence by -{penalty} due to {match_pat.correction_count} historical reviewer corrections."
        except Exception as e:
            logger.debug("Active learning pattern check skipped: %s", e)

        # Apply confidence threshold to determine status
        if field.confidence >= threshold:
            field.status = FieldStatus.AUTO_COMMITTED
        else:
            field.status = FieldStatus.NEEDS_REVIEW

        return field


    def _check_type(self, value: object, expected: FieldType) -> bool:
        """Check if a value matches the expected field type."""
        if expected == FieldType.NUMBER:
            return isinstance(value, (int, float))
        elif expected == FieldType.STRING:
            return isinstance(value, str)
        elif expected == FieldType.BOOLEAN:
            return isinstance(value, bool)
        elif expected == FieldType.LIST:
            return isinstance(value, list)
        return True

    def _check_completeness(
        self,
        fields: list[ProductField],
        schema: CategorySchema,
    ) -> list[ProductField]:
        """Verify all required fields are present; penalize missing ones."""
        field_names = [f.name for f in fields]
        assess_record_completeness(schema.category_key, field_names)

        existing_names = set(field_names)
        required_names = set(schema.required_field_names)
        missing = required_names - existing_names

        if missing:
            logger.warning(
                "Missing required fields after enrichment: %s",
                ", ".join(sorted(missing)),
            )

        return fields
