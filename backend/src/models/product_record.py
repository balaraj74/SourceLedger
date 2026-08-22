"""Core domain models for SourceLedger.

These are the load-bearing data structures of the entire system.
The key modeling decision: Field is its own entity (not a flat
key-value inside a product dict) so that confidence, citation,
reasoning, and review status can be tracked per-field. This is
what makes the Field Inspector and Review Queue possible.

No product field is ever created without a source reference and
confidence score — a missing citation is treated as a bug, not
a cosmetic gap.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────


class FieldStatus(str, Enum):
    """Lifecycle status of a product field.

    Every field starts as NEEDS_REVIEW or AUTO_COMMITTED depending on
    whether its confidence meets the threshold. HUMAN_CORRECTED is set
    only after a reviewer explicitly acts on it.
    """

    AUTO_COMMITTED = "auto_committed"
    NEEDS_REVIEW = "needs_review"
    HUMAN_CORRECTED = "human_corrected"


class SourceType(str, Enum):
    """Type of source document ingested."""

    PDF = "pdf"
    WEB = "web"
    IMAGE = "image"
    CSV = "csv"
    XLSX = "xlsx"
    MANUAL = "manual"


class TrustTier(int, Enum):
    """Source trust ranking for conflict resolution.

    Lower number = higher trust. When two sources disagree on a field,
    the source with the lower (more trusted) tier wins — unless the
    confidence delta is too small to be decisive, in which case the
    field routes to human review.

    This ranking reflects real-world data quality hierarchy in
    industrial product data:
    - Manufacturer specs are canonical
    - Authorized distributors are generally accurate but may lag
    - Marketplace/forum listings are noisy and often incomplete
    """

    MANUFACTURER = 1
    DISTRIBUTOR = 2
    MARKETPLACE = 3


class ReviewActionType(str, Enum):
    """What a human reviewer did with a flagged field."""

    ACCEPT = "accept"
    EDIT = "edit"
    REJECT = "reject"


# ── Source ───────────────────────────────────────────────────────────


class Source(BaseModel):
    """A source document from which product data was extracted.

    Every piece of product data in SourceLedger traces back to at
    least one Source. The original content is stored in object storage
    and referenced by raw_content_ref for audit and citation.
    """

    id: UUID = Field(default_factory=uuid4)
    source_type: SourceType
    origin: str  # URL, filename, or upload identifier
    raw_content_ref: str  # Path in object storage to the original document
    content_hash: str  # SHA-256 of content, for idempotency checks
    trust_tier: TrustTier = TrustTier.MARKETPLACE
    title: Optional[str] = None  # Human-readable title if available
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class SourceExcerpt(BaseModel):
    """A specific excerpt from a source, used for field-level citation.

    This is what the Field Inspector surfaces to the user: the exact
    text that led to a field value, not just a pointer to a whole
    document. The combination of source_id + text + location makes
    every field's provenance independently verifiable.
    """

    source_id: UUID
    text: str  # The exact excerpt from the source
    location: Optional[str] = None  # Page number, CSS selector, section heading, etc.
    extraction_method: str = "text"  # "text", "vlm_image", or "vlm_pdf_table" (Phase 9)
    bounding_box: Optional[dict] = None  # VLM image crop / bounding box coordinates (Phase 9)


# ── ProductField ─────────────────────────────────────────────────────


class ProductField(BaseModel):
    """A single field in a product record, with full provenance.

    This is the core modeling decision in SourceLedger. Instead of
    storing product data as a flat dict of {field_name: value}, every
    field is its own entity carrying:

    - confidence (0–100): how certain the system is about this value
    - source_excerpt: the exact text this value was extracted from
    - reasoning: the LLM's explanation of why this value was chosen
    - status: whether it was auto-committed, needs review, or has
      been corrected by a human

    This per-field granularity is what powers the Field Inspector
    (click any field → see its provenance) and the Review Queue
    (filter to only the uncertain fields).
    """

    id: UUID = Field(default_factory=uuid4)
    name: str  # Field key, e.g. "flow_rate", "material_body"
    display_name: str  # Human-readable label, e.g. "Flow Rate"
    value: Any  # The extracted/enriched value
    unit: Optional[str] = None  # Unit of measurement, if applicable
    confidence: int = Field(ge=0, le=100)
    source_excerpt: SourceExcerpt
    reasoning: str  # Why this value was chosen — shown in Field Inspector
    status: FieldStatus = FieldStatus.NEEDS_REVIEW
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ── ProductRecord ────────────────────────────────────────────────────


class ProductRecord(BaseModel):
    """A structured, validated product record with full provenance.

    Each record belongs to a category (e.g. "industrial_pump") and its
    fields are validated against that category's schema definition in
    schemas.py.

    confidence_overall is computed as the minimum confidence across all
    fields, because the record is only as trustworthy as its weakest
    field. This incentivizes the system to flag gaps rather than hide
    them behind a misleading average.
    """

    id: UUID = Field(default_factory=uuid4)
    name: str  # Product name/title
    category: str  # Category key, e.g. "industrial_pump"
    schema_version: str = "1.0"
    fields: list[ProductField] = Field(default_factory=list)
    source_ids: list[UUID] = Field(default_factory=list)
    confidence_overall: int = Field(ge=0, le=100, default=0)
    # Canonical part-number key — populated by the pipeline after extraction
    # by scanning extracted fields for mfg_part_num > part_number > sku.
    # Used for export deduplication: when the same part number appears
    # multiple times (re-upload, duplicate row), only the highest-confidence
    # record is exported. None when the source had no identifiable part number.
    mfg_part_num: Optional[str] = None
    taxonomy_code: Optional[str] = None  # UNSPSC/eCl@ss code (stretch)
    dedup_cluster_id: Optional[UUID] = None  # Dedup cluster (stretch)
    conflicts: list[Any] = Field(default_factory=list)  # FieldConflict records (Phase 7)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def compute_overall_confidence(self) -> int:
        """Recalculate overall confidence as minimum of all field confidences.

        Using min rather than mean because a record with nine 95%
        fields and one 20% field is not a 87.5%-trustworthy record —
        it's a record with a known weak spot that needs review.
        """
        if not self.fields:
            return 0
        return min(f.confidence for f in self.fields)


# ── ReviewAction ─────────────────────────────────────────────────────


class ReviewAction(BaseModel):
    """A human correction applied to a product field.

    Stored for two purposes:
    1. Audit trail — every change to product data is traceable
    2. Active learning loop (stretch goal) — corrections feed back
       into future extraction for that category, so accuracy visibly
       improves with use
    """

    id: UUID = Field(default_factory=uuid4)
    field_id: UUID
    product_id: UUID
    action: ReviewActionType
    original_value: Any
    corrected_value: Optional[Any] = None  # Required when action is EDIT
    reviewer: str = "anonymous"  # No auth in MVP
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
