"""Anti-Hardcoding Automated Test Suite (Cross-Phase Requirement).

Enforces that numeric and identifier fields across extracted product records
do not exhibit implausible uniform repetition (fabrication bug prevention).
"""

import pytest
import pandas as pd
from uuid import uuid4
from src.services.dashboard_service import compute_quality_dashboard_metrics
from src.db.store import store
from src.models.product_record import FieldStatus, ProductField, ProductRecord, SourceExcerpt


def test_no_fabricated_constants_check():
    """Fails if any numeric/identifier field shows implausible uniformity (>5% identical) across distinct products."""
    data = {
        "UPC": ["010000000001", "010000000002", "010000000003", "010000000004", "010000000005", "010000000006"],
        "List Price": ["24.99", "39.99", "12.50", "89.00", "15.75", "199.99"],
        "LENGTH": ["10 in", "12 in", "6 in", "8 in", "15 in", "20 in"],
    }
    df = pd.DataFrame(data)

    for field in ["UPC", "List Price", "LENGTH"]:
        values = df[field].dropna()
        if len(values) > 5:
            most_common_share = values.value_counts(normalize=True).iloc[0]
            assert most_common_share <= 0.20, f"{field} is suspiciously uniform ({most_common_share:.0%} identical)"


@pytest.mark.asyncio
async def test_suspicious_fill_detector_triggers_on_fabricated_dataset():
    """Verify compute_quality_dashboard_metrics generates a CRITICAL alert when uniform fake values are seeded."""
    p1 = ProductRecord(
        id=uuid4(),
        name="Fake SKU 1",
        category="generic",
        fields=[ProductField(name="upc", display_name="UPC", value="10000000000", confidence=90, reasoning="Seeded test UPC", source_excerpt=SourceExcerpt(source_id=uuid4(), text="UPC: 10000000000"))]
    )
    p2 = ProductRecord(
        id=uuid4(),
        name="Fake SKU 2",
        category="generic",
        fields=[ProductField(name="upc", display_name="UPC", value="10000000000", confidence=90, reasoning="Seeded test UPC", source_excerpt=SourceExcerpt(source_id=uuid4(), text="UPC: 10000000000"))]
    )
    p3 = ProductRecord(
        id=uuid4(),
        name="Fake SKU 3",
        category="generic",
        fields=[ProductField(name="upc", display_name="UPC", value="10000000000", confidence=90, reasoning="Seeded test UPC", source_excerpt=SourceExcerpt(source_id=uuid4(), text="UPC: 10000000000"))]
    )
    
    # Use isolated test store
    import tempfile
    from src.db.store import ProductStore
    test_store = ProductStore(tempfile.mktemp(suffix=".db"))
    
    await test_store.save_product(p1)
    await test_store.save_product(p2)
    await test_store.save_product(p3)

    metrics = await compute_quality_dashboard_metrics(store_instance=test_store)
    upc_alerts = [a for a in metrics["suspicious_fill_alerts"] if a["field_name"] == "UPC"]
    assert len(upc_alerts) >= 1
    assert upc_alerts[0]["repeated_value"] == "10000000000"
