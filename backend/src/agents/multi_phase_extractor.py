"""Multi-Phase Product Extractor — iterative, split-by-split enrichment.

Instead of one big LLM prompt trying to fill all 252 output columns at once,
this module splits the work into 4 focused phases, each responsible for a
narrow subset of the output columns:

  Phase 1  IDENTITY      — part number, manufacturer, brand, product name (~0.5s)
  Phase 2  DESCRIPTIONS  — short/long/mobile/retail/marketing desc + features 1–20
                           in batches of 5 features to reduce hallucination
  Phase 3  ATTRIBUTES    — technical attribute label/value/UOM triplets in batches
                           of 10 triplets; each batch is aware of prior output
  Phase 4  LOGISTICS     — dimensions, weight, UNSPSC, URLs, certifications,
                           country of origin, compliance

Each phase:
  - Receives a narrow prompt with only its target output columns listed
  - Knows what prior phases have already filled (so it does not repeat)
  - Must cite an exact verbatim excerpt from the source text for each value
  - Returns only what is directly supported — empty field = absent from prompt
  - Gracefully returns an empty list when source has no relevant content

Results from all phases are merged by the consolidator.  Conflicts are
resolved by keeping the highest-confidence value for each field name.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from ..models.product_record import FieldStatus, ProductField, SourceExcerpt
from ..utils.logging import get_logger

logger = get_logger("MultiPhaseExtractor")

# ── Field group definitions ───────────────────────────────────────────────────

#: Identity fields — always extracted in Phase 1
_IDENTITY_FIELDS = [
    ("mfg_part_num",           "Manufacturer Part Number"),
    ("manufacturer_name",      "Manufacturer Name"),
    ("brand_name",             "Brand Name"),
    ("trade_name",             "Trade Name"),
    ("product_name",           "Product Name"),
    ("dept",                   "Department"),
    ("category_class",         "Class"),
    ("fine_category",          "Fine Category"),
    ("classpath",              "Classpath (e.g. Dept>Class>Fine)"),
]

#: Description fields — Phase 2
_DESCRIPTION_FIELDS = [
    ("short_desc",             "SHORT_DESC",            "Concise 1–2 sentence product summary for e-commerce"),
    ("invoice_desc",           "INVOICE_DESC",          "Short billing/invoice line description (≤80 chars)"),
    ("mobile_desc",            "MOBILE_DESC",           "Ultra-short description for mobile app (≤60 chars)"),
    ("long_desc1",             "LONG_DESC1",            "Full detailed product description (3–6 sentences)"),
    ("retail_desc",            "RETAIL_DESC",           "Consumer-facing retail description"),
    ("marketing_description",  "MARKETING_DESCRIPTION", "Marketing/promotional copy (1–3 sentences)"),
]

#: Item feature batch (5 at a time — reduces hallucination vs generating 20 at once)
_FEATURE_BATCH_SIZE = 5
_MAX_FEATURES = 20

#: Attribute batch (10 triplets at a time)
_ATTRIBUTE_BATCH_SIZE = 10
_MAX_ATTRIBUTES = 50

#: Logistics / compliance fields — Phase 4
_LOGISTICS_FIELDS = [
    ("length",           "Length value (numeric)"),
    ("length_uom",       "Length unit (in, mm, cm, ft …)"),
    ("height",           "Height value (numeric)"),
    ("height_uom",       "Height unit"),
    ("width",            "Width value (numeric)"),
    ("width_uom",        "Width unit"),
    ("weight",           "Weight value (numeric)"),
    ("weight_uom",       "Weight unit (lbs, kg, g, oz …)"),
    ("upc",              "UPC barcode (12-digit)"),
    ("ean",              "EAN barcode (13-digit)"),
    ("gtin",             "GTIN"),
    ("unspsc",           "UNSPSC code (8-digit)"),
    ("warranty",         "Warranty description"),
    ("list_price",       "List Price (numeric, USD)"),
    ("country_of_origin","Country of Origin"),
    ("standards_approvals","Standards/Certifications (e.g. UL, CE, RoHS, CSA)"),
    ("prop_65",          "California Prop 65 warning (Yes/No)"),
    ("application",      "Intended application / use environment"),
    ("includes",         "Package contents / included accessories"),
    ("with_feature",     "Key 'with' feature e.g. 'With LED work light'"),
]


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class PhaseResult:
    """Output from one extraction phase."""
    phase_name: str
    fields: list[ProductField] = field(default_factory=list)
    coverage: float = 0.0   # fraction of target fields that got a value


@dataclass
class MultiPhaseResult:
    """Merged output from all phases."""
    fields: list[ProductField] = field(default_factory=list)
    product_name: str = ""
    phases_run: list[str] = field(default_factory=list)
    total_fields_extracted: int = 0


# ── Helper ────────────────────────────────────────────────────────────────────

def _normalise(text: str) -> str:
    return " ".join(text.casefold().split())


def _strip_json(text: str) -> str:
    """Strip markdown code fences from an LLM JSON response."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```\w*\n?", "", cleaned)
    cleaned = re.sub(r"\n?```$", "", cleaned)
    return cleaned.strip()


def _make_field(
    name: str,
    display_name: str,
    value: Any,
    confidence: int,
    excerpt: str,
    reasoning: str,
    source_id: UUID,
    unit: str | None = None,
) -> ProductField:
    return ProductField(
        id=uuid4(),
        name=name,
        display_name=display_name,
        value=value,
        unit=unit,
        confidence=min(100, max(0, confidence)),
        source_excerpt=SourceExcerpt(source_id=source_id, text=excerpt[:300]),
        reasoning=reasoning,
        status=FieldStatus.NEEDS_REVIEW,
    )


# ── Main class ────────────────────────────────────────────────────────────────

class MultiPhaseExtractor:
    """Runs 4 focused extraction phases, merging results for final output.

    Each phase makes one LLM call with a narrow prompt covering only its
    column group.  This significantly reduces hallucination vs a single
    prompt that tries to fill all 252 columns at once.

    Usage::

        extractor = MultiPhaseExtractor(client, source_text, source_id)
        result = await extractor.run()
        # result.fields contains the merged ProductField list
    """

    def __init__(
        self,
        client: Any,
        source_text: str,
        source_id: UUID,
        *,
        model: str = "gemini-3.6-flash",
        temperature: float = 0.05,

    ) -> None:
        self._client = client
        self._source_text = source_text[:16_000]  # hard cap to stay in context
        self._source_id = source_id
        self._model = model
        self._temperature = temperature
        self._normalised_source = _normalise(self._source_text)

    # ── Internal LLM caller ───────────────────────────────────────────────────

    async def _call_llm(self, prompt: str) -> str:
        """Make a single async LLM call with 429 quota auto-retry and key rotation."""
        from google import genai
        from google.genai import types
        from .main import key_rotator

        for attempt in range(3):
            try:
                response = await asyncio.to_thread(
                    self._client.models.generate_content,
                    model=self._model,
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=self._temperature),
                )
                return response.text or ""
            except Exception as exc:
                exc_str = str(exc)
                if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str or "quota" in exc_str.lower():
                    logger.info("MultiPhaseExtractor 429 rate limit hit (attempt %d/3). Rotating key...", attempt + 1)
                    new_key = key_rotator.get_next_key()
                    if new_key:
                        try:
                            self._client = genai.Client(api_key=new_key)
                        except Exception:
                            pass
                    await asyncio.sleep(2.0 * (attempt + 1))
                else:
                    logger.warning("MultiPhaseExtractor LLM call exception: %s", exc)
                    return ""
        return ""


    def _excerpt_is_grounded(self, excerpt: str) -> bool:
        """Return True if the excerpt appears verbatim in the source text."""
        if not excerpt or len(excerpt) < 4:
            return False
        if "inferred" in excerpt.lower() or "general knowledge" in excerpt.lower():
            return False
        return _normalise(excerpt) in self._normalised_source

    def _parse_field_list(self, response_text: str, source_id: UUID) -> list[ProductField]:
        """Parse a standard JSON fields array from an LLM response."""
        cleaned = _strip_json(response_text)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            # Try to extract first JSON object/array from the text
            m = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if not m:
                return []
            try:
                data = json.loads(m.group(0))
            except json.JSONDecodeError:
                return []

        raw_fields = data.get("fields", []) if isinstance(data, dict) else []
        if not isinstance(raw_fields, list):
            return []

        fields: list[ProductField] = []
        for rf in raw_fields:
            if not isinstance(rf, dict):
                continue
            name = str(rf.get("name") or "").strip()
            value = rf.get("value")
            excerpt = str(rf.get("excerpt") or "").strip()
            reasoning = str(rf.get("reasoning") or "").strip()
            confidence = int(rf.get("confidence", 0))
            unit = rf.get("unit") or None
            display = str(rf.get("display_name") or name.replace("_", " ").title()).strip()

            if not name or value in (None, "", [], {}):
                continue
            if not self._excerpt_is_grounded(excerpt):
                continue  # reject ungrounded claims

            fields.append(_make_field(
                name=name,
                display_name=display,
                value=value,
                confidence=confidence,
                excerpt=excerpt,
                reasoning=reasoning or f"Extracted from source in Phase",
                source_id=source_id,
                unit=unit,
            ))

        # Dedup: description fields must not all share the same value.
        # If Phase 2 fills short_desc/long_desc1/mobile_desc/retail_desc/
        # marketing_description/invoice_desc all with the same string (product name
        # copy), drop all except the first and highest-confidence occurrence.
        _DESC_NAMES = {"short_desc", "long_desc1", "invoice_desc",
                       "mobile_desc", "retail_desc", "marketing_description"}
        _seen_desc_values: set[str] = set()
        deduped: list[ProductField] = []
        for _f in fields:
            if _f.name in _DESC_NAMES:
                _norm_val = " ".join(str(_f.value).casefold().split())
                if _norm_val in _seen_desc_values:
                    logger.debug("Phase2 dedup: dropping '%s' (same value as prior description)", _f.name)
                    continue
                _seen_desc_values.add(_norm_val)
            deduped.append(_f)
        return deduped

    # ── Phase 1: IDENTITY ─────────────────────────────────────────────────────

    async def phase1_identity(self) -> PhaseResult:
        """Extract part number, manufacturer, brand, product name, taxonomy."""
        target_block = "\n".join(
            f'  "{name}" — {desc}' for name, desc in _IDENTITY_FIELDS
        )
        prompt = f"""You are an expert product data extractor.
Extract ONLY the identity/taxonomy fields listed below from the SOURCE TEXT.
Return ONLY values that appear verbatim in the source. Do NOT infer, guess, or use general knowledge.
Leave out any field not directly supported by the source text.

TARGET FIELDS:
{target_block}

SOURCE TEXT:
---
{self._source_text}
---

Return ONLY a JSON object in this exact format:
{{
  "fields": [
    {{"name": "<field_key>", "display_name": "<label>", "value": "<verbatim value>", "confidence": <0-100>, "excerpt": "<exact verbatim quote from source>", "reasoning": "<one sentence>"}}
  ]
}}
No markdown, no commentary outside the JSON."""

        logger.info("MultiPhaseExtractor: Phase 1 — IDENTITY")
        response = await self._call_llm(prompt)
        fields = self._parse_field_list(response, self._source_id)
        logger.info("Phase 1 complete: %d identity fields", len(fields))
        return PhaseResult(phase_name="identity", fields=fields, coverage=len(fields) / max(1, len(_IDENTITY_FIELDS)))

    # ── Phase 2: DESCRIPTIONS ─────────────────────────────────────────────────

    async def phase2_descriptions(self, identity_context: str) -> PhaseResult:
        """Extract all description fields + item features in batches of 5."""
        all_fields: list[ProductField] = []

        # Part A: description text fields
        desc_targets = "\n".join(
            f'  "{name}" ({col}) — {desc}'
            for name, col, desc in _DESCRIPTION_FIELDS
        )
        prompt_desc = f"""You are an expert product data extractor.
The product has already been identified as:
{identity_context}

Extract ONLY the description fields below from the SOURCE TEXT.

STRICT RULES — READ CAREFULLY:
1. Return ONLY values directly supported by the source text. Do NOT write from scratch.
2. EACH description field must contain DISTINCT content — do NOT copy the same sentence or phrase into multiple fields.
3. SHORT_DESC: 1–2 sentences max. LONG_DESC1 must be longer and richer than SHORT_DESC.
4. If the source only contains a product name (e.g. "DeWalt 20V Battery"), fill SHORT_DESC only — leave LONG_DESC1, MOBILE_DESC, RETAIL_DESC, MARKETING_DESCRIPTION all EMPTY.
5. INVOICE_DESC must be ≤ 80 characters. MOBILE_DESC must be ≤ 60 characters.
6. Each field must include an exact verbatim excerpt proving the value comes from the source.
7. Do NOT repeat the product name verbatim as the full value of a description field.

TARGET DESCRIPTION FIELDS:
{desc_targets}

SOURCE TEXT:
---
{self._source_text}
---

Return ONLY JSON:
{{"fields": [{{"name": "<key>", "display_name": "<label>", "value": "<text>", "confidence": <0-100>, "excerpt": "<exact verbatim quote>", "reasoning": "<one sentence>"}}]}}"""

        logger.info("MultiPhaseExtractor: Phase 2a — DESCRIPTIONS")
        resp = await self._call_llm(prompt_desc)
        all_fields.extend(self._parse_field_list(resp, self._source_id))

        # Part B: item features in batches of 5
        already_filled = {f.name for f in all_fields}
        filled_features: list[str] = []  # collect all feature values for tracking

        for batch_start in range(1, _MAX_FEATURES + 1, _FEATURE_BATCH_SIZE):
            batch_end = min(batch_start + _FEATURE_BATCH_SIZE - 1, _MAX_FEATURES)
            # Build target feature names for this batch
            feature_names = [f"item_features_{i}" for i in range(batch_start, batch_end + 1)]

            prompt_features = f"""You are an expert product data extractor.
Product identity: {identity_context}

Extract exactly {batch_end - batch_start + 1} product feature bullet points (ITEM_FEATURES_{batch_start} to ITEM_FEATURES_{batch_end}) from the SOURCE TEXT.
Each feature must be:
  - A distinct, concrete product attribute or benefit directly stated in the source
  - A short phrase or sentence (not repeated from another bullet already filled)
  - Directly supported by the source text — do NOT invent features

Already filled features (do not repeat these): {filled_features[-10:] if filled_features else "(none yet)"}

SOURCE TEXT:
---
{self._source_text}
---

Return ONLY JSON with fields named "item_features_{batch_start}" through "item_features_{batch_end}":
{{"fields": [{{"name": "item_features_N", "display_name": "Item Feature N", "value": "<feature text>", "confidence": <0-100>, "excerpt": "<verbatim source quote>", "reasoning": "<one sentence>"}}]}}
Only include features with strong source support. Return fewer fields if the source does not support more."""

            logger.info("MultiPhaseExtractor: Phase 2b — features %d–%d", batch_start, batch_end)
            resp_f = await self._call_llm(prompt_features)
            batch_fields = self._parse_field_list(resp_f, self._source_id)

            # Renumber features sequentially so they don't collide
            # The LLM returns named fields like "item_features_1", but each batch
            # should map to a unique slot in the output
            renumbered: list[ProductField] = []
            for bf in batch_fields:
                # Extract the batch-local index (e.g. "item_features_3" → 3)
                m = re.search(r"item_features_(\d+)$", bf.name)
                if m:
                    local_idx = int(m.group(1))
                    global_idx = batch_start + local_idx - 1  # offset to global slot
                    if 1 <= global_idx <= _MAX_FEATURES:
                        global_name = f"item_features_{global_idx}"
                        if global_name not in already_filled:
                            already_filled.add(global_name)
                            filled_features.append(str(bf.value))
                            bf = _make_field(
                                name=global_name,
                                display_name=f"Item Feature {global_idx}",
                                value=bf.value,
                                confidence=bf.confidence,
                                excerpt=bf.source_excerpt.text if bf.source_excerpt else "",
                                reasoning=bf.reasoning,
                                source_id=self._source_id,
                            )
                            renumbered.append(bf)
            all_fields.extend(renumbered)

            # Stop early if the batch returned nothing useful (source exhausted)
            if not renumbered:
                logger.info("Phase 2b: source exhausted at feature batch starting at %d", batch_start)
                break

        logger.info("Phase 2 complete: %d fields (desc + features)", len(all_fields))
        return PhaseResult(phase_name="descriptions", fields=all_fields)

    # ── Phase 3: ATTRIBUTES ───────────────────────────────────────────────────

    async def phase3_attributes(self, identity_context: str, already_in_phases_1_2: set[str]) -> PhaseResult:
        """Extract technical attribute triplets (label/value/UOM) in batches of 10."""
        all_attrs: list[dict] = []  # collect as dicts first, then convert
        attr_slot = 1               # global attribute slot counter

        for batch_num in range(1, (_MAX_ATTRIBUTES // _ATTRIBUTE_BATCH_SIZE) + 2):
            if attr_slot > _MAX_ATTRIBUTES:
                break

            already_labels = [a["label"] for a in all_attrs[-15:]] if all_attrs else []

            prompt_attrs = f"""You are an expert product data extractor.
Product identity: {identity_context}

Extract up to {_ATTRIBUTE_BATCH_SIZE} technical attribute triplets (label, value, unit) from the SOURCE TEXT.
Each attribute must represent a distinct technical specification — e.g. "Voltage Rating / 250 / V" or "Flow Rate / 15 / m³/h".

Rules:
- Each attribute must be directly stated in the source text (verbatim evidence required).
- Do NOT repeat these already-extracted attributes: {already_labels}
- Do NOT include attributes already covered in descriptions (SHORT_DESC, LONG_DESC, features).
- Omit unit if the value has no meaningful unit.
- Return fewer than {_ATTRIBUTE_BATCH_SIZE} if the source does not have more distinct specs.

SOURCE TEXT:
---
{self._source_text}
---

Return ONLY JSON:
{{"attributes": [{{"label": "<spec name>", "value": "<value>", "uom": "<unit or empty>", "excerpt": "<exact verbatim source quote>", "confidence": <0-100>}}]}}
Return an empty attributes array if no more distinct specs are found."""

            logger.info("MultiPhaseExtractor: Phase 3 — attribute batch %d (slot %d+)", batch_num, attr_slot)
            response = await self._call_llm(prompt_attrs)

            cleaned = _strip_json(response)
            try:
                data = json.loads(cleaned)
                candidates = data.get("attributes", []) if isinstance(data, dict) else []
            except json.JSONDecodeError:
                candidates = []

            if not candidates:
                logger.info("Phase 3: no more attributes from source at batch %d", batch_num)
                break

            new_attrs_this_batch = 0
            for cand in candidates:
                if not isinstance(cand, dict):
                    continue
                label = str(cand.get("label") or "").strip()
                value = cand.get("value")
                uom = str(cand.get("uom") or "").strip()
                excerpt = str(cand.get("excerpt") or "").strip()
                confidence = int(cand.get("confidence", 70))

                if not label or value in (None, "", []):
                    continue
                if not self._excerpt_is_grounded(excerpt):
                    continue  # no ungrounded attributes
                # Skip duplicate labels
                if any(a["label"].lower() == label.lower() for a in all_attrs):
                    continue

                all_attrs.append({
                    "label": label, "value": value, "uom": uom,
                    "excerpt": excerpt, "confidence": confidence,
                    "slot": attr_slot,
                })
                attr_slot += 1
                new_attrs_this_batch += 1
                if attr_slot > _MAX_ATTRIBUTES:
                    break

            if new_attrs_this_batch == 0:
                break  # source has no more distinct specs

        # Convert to ProductFields with names like "attribute_label_1", "attribute_value_1"
        fields: list[ProductField] = []
        for a in all_attrs:
            s = a["slot"]
            label_field = _make_field(
                name=f"attribute_label_{s}",
                display_name=f"Attribute Label {s}",
                value=a["label"],
                confidence=a["confidence"],
                excerpt=a["excerpt"],
                reasoning=f"Technical spec extracted in attribute batch",
                source_id=self._source_id,
            )
            value_field = _make_field(
                name=f"attribute_value_{s}",
                display_name=f"Attribute Value {s}",
                value=str(a["value"]),
                confidence=a["confidence"],
                excerpt=a["excerpt"],
                reasoning=f"Technical spec extracted in attribute batch",
                source_id=self._source_id,
                unit=a["uom"] or None,
            )
            uom_field = _make_field(
                name=f"attribute_uom_{s}",
                display_name=f"Attribute UOM {s}",
                value=a["uom"],
                confidence=a["confidence"],
                excerpt=a["excerpt"],
                reasoning="Unit of measurement for attribute",
                source_id=self._source_id,
            ) if a["uom"] else None

            fields.append(label_field)
            fields.append(value_field)
            if uom_field:
                fields.append(uom_field)

        logger.info("Phase 3 complete: %d attribute triplets → %d fields", len(all_attrs), len(fields))
        return PhaseResult(phase_name="attributes", fields=fields, coverage=len(all_attrs) / _MAX_ATTRIBUTES)

    # ── Phase 4: LOGISTICS ────────────────────────────────────────────────────

    async def phase4_logistics(self, identity_context: str) -> PhaseResult:
        """Extract dimensions, weight, UNSPSC, compliance, URLs, country of origin."""
        target_block = "\n".join(
            f'  "{name}" — {desc}' for name, desc in _LOGISTICS_FIELDS
        )
        prompt = f"""You are an expert product data extractor.
Product identity: {identity_context}

Extract ONLY the logistics/compliance fields below from the SOURCE TEXT.
Rules:
- Return ONLY values directly supported by the source text.
- Numeric fields (length, height, width, weight, list_price): return only the number, not the unit.
- For UOM fields: return only the unit string.
- Do NOT infer dimensions or weights from product category knowledge.
- Do NOT invent certifications not mentioned in the source.

TARGET LOGISTICS FIELDS:
{target_block}

SOURCE TEXT:
---
{self._source_text}
---

Return ONLY JSON:
{{"fields": [{{"name": "<key>", "display_name": "<label>", "value": "<value>", "unit": "<uom or null>", "confidence": <0-100>, "excerpt": "<exact verbatim quote>", "reasoning": "<one sentence>"}}]}}"""

        logger.info("MultiPhaseExtractor: Phase 4 — LOGISTICS")
        response = await self._call_llm(prompt)
        fields = self._parse_field_list(response, self._source_id)
        logger.info("Phase 4 complete: %d logistics fields", len(fields))
        return PhaseResult(phase_name="logistics", fields=fields)

    # ── Consolidator ──────────────────────────────────────────────────────────

    @staticmethod
    def _merge_phases(phases: list[PhaseResult]) -> list[ProductField]:
        """Merge all phase results, keeping the highest-confidence value per field name."""
        best: dict[str, ProductField] = {}
        for phase in phases:
            for f in phase.fields:
                existing = best.get(f.name)
                if existing is None or f.confidence > existing.confidence:
                    best[f.name] = f
        return list(best.values())

    # ── Public entry point ────────────────────────────────────────────────────

    async def run(self) -> MultiPhaseResult:
        """Run all 4 phases sequentially and return the merged result.

        Each phase builds on the identity context from Phase 1.
        Phases 2–4 are run with the identity context so they can reference
        the product correctly without re-reading the full source text.
        """
        phases_run: list[str] = []

        # Phase 1 always runs
        p1 = await phase1_safe(self)
        phases_run.append("identity")

        # Build a compact identity context string for Phases 2–4
        identity_parts: list[str] = []
        for f in p1.fields:
            if f.name in ("mfg_part_num", "manufacturer_name", "brand_name", "product_name"):
                identity_parts.append(f"{f.display_name}: {f.value}")
        identity_context = "; ".join(identity_parts) if identity_parts else "(see source text)"

        # Extract product name for the result
        product_name = next(
            (str(f.value) for f in p1.fields if f.name in ("product_name", "mfg_part_num") and f.value),
            "",
        )

        # Phases 2–4 only run if Phase 1 produced at least a part number or name
        if not product_name:
            logger.warning("MultiPhaseExtractor: Phase 1 produced no identity — skipping 2–4")
            return MultiPhaseResult(
                fields=p1.fields,
                product_name="",
                phases_run=phases_run,
                total_fields_extracted=len(p1.fields),
            )

        already_named = {f.name for f in p1.fields}

        p2 = await phase2_safe(self, identity_context)
        phases_run.append("descriptions")

        already_named.update(f.name for f in p2.fields)

        p3 = await phase3_safe(self, identity_context, already_named)
        phases_run.append("attributes")

        p4 = await phase4_safe(self, identity_context)
        phases_run.append("logistics")

        merged = self._merge_phases([p1, p2, p3, p4])

        logger.info(
            "MultiPhaseExtractor done: %d total fields across %d phases",
            len(merged), len(phases_run),
        )
        return MultiPhaseResult(
            fields=merged,
            product_name=product_name,
            phases_run=phases_run,
            total_fields_extracted=len(merged),
        )


# ── Safe wrappers (catch per-phase errors without stopping the run) ───────────

async def phase1_safe(extractor: MultiPhaseExtractor) -> PhaseResult:
    try:
        return await extractor.phase1_identity()
    except Exception as exc:
        logger.error("Phase 1 (identity) failed: %s", exc)
        return PhaseResult(phase_name="identity")


async def phase2_safe(extractor: MultiPhaseExtractor, identity: str) -> PhaseResult:
    try:
        return await extractor.phase2_descriptions(identity)
    except Exception as exc:
        logger.error("Phase 2 (descriptions) failed: %s", exc)
        return PhaseResult(phase_name="descriptions")


async def phase3_safe(extractor: MultiPhaseExtractor, identity: str, already: set[str]) -> PhaseResult:
    try:
        return await extractor.phase3_attributes(identity, already)
    except Exception as exc:
        logger.error("Phase 3 (attributes) failed: %s", exc)
        return PhaseResult(phase_name="attributes")


async def phase4_safe(extractor: MultiPhaseExtractor, identity: str) -> PhaseResult:
    try:
        return await extractor.phase4_logistics(identity)
    except Exception as exc:
        logger.error("Phase 4 (logistics) failed: %s", exc)
        return PhaseResult(phase_name="logistics")
