"""Unit tests for Multi-Tenant User Data Isolation."""

import tempfile
from uuid import uuid4
import pytest

from src.db.store import ProductStore
from src.models.product_record import ProductRecord, ProductField, FieldStatus, Source, SourceExcerpt, SourceType, TrustTier


@pytest.mark.asyncio
async def test_user_data_isolation():
    """Verify that User A cannot see User B's product records or sources."""
    test_db = tempfile.mktemp(suffix=".db")
    store = ProductStore(test_db)

    # 1. User A saves a source and product
    user_a = "usr-user-a-123"
    src_a = Source(
        id=uuid4(),
        source_type=SourceType.PDF,
        origin="datasheet_a.pdf",
        raw_content_ref="storage/datasheet_a.pdf",
        content_hash="hash_a",
        trust_tier=TrustTier.MANUFACTURER,
    )
    prod_a = ProductRecord(
        id=uuid4(),
        name="Pump Model A (User A Only)",
        category="industrial_pump",
        confidence_overall=95,
        fields=[
            ProductField(
                name="flow_rate",
                display_name="Flow Rate",
                value="50 m³/h",
                confidence=95,
                status=FieldStatus.AUTO_COMMITTED,
                reasoning="Datasheet A",
                source_excerpt=SourceExcerpt(source_id=src_a.id, text="50 m³/h"),
            )
        ],
    )
    await store.save_source(src_a, user_id=user_a)
    await store.save_product(prod_a, user_id=user_a)

    # 2. User B saves a source and product
    user_b = "usr-user-b-456"
    src_b = Source(
        id=uuid4(),
        source_type=SourceType.WEB,
        origin="catalog_b.html",
        raw_content_ref="storage/catalog_b.html",
        content_hash="hash_b",
        trust_tier=TrustTier.DISTRIBUTOR,
    )
    prod_b = ProductRecord(
        id=uuid4(),
        name="Valve Model B (User B Only)",
        category="valve",
        confidence_overall=88,
        fields=[
            ProductField(
                name="pressure_rating",
                display_name="Pressure Rating",
                value="16 bar",
                confidence=88,
                status=FieldStatus.AUTO_COMMITTED,
                reasoning="Catalog B",
                source_excerpt=SourceExcerpt(source_id=src_b.id, text="16 bar"),
            )
        ],
    )
    await store.save_source(src_b, user_id=user_b)
    await store.save_product(prod_b, user_id=user_b)

    # 3. Query as User A
    products_a = await store.list_products(user_id=user_a)
    sources_a = await store.list_sources(user_id=user_a)
    stats_a = await store.get_dashboard_stats(user_id=user_a)

    assert len(products_a) == 1
    assert products_a[0].name == "Pump Model A (User A Only)"
    assert len(sources_a) == 1
    assert sources_a[0].origin == "datasheet_a.pdf"
    assert stats_a["total_records"] == 1

    # 4. Query as User B
    products_b = await store.list_products(user_id=user_b)
    sources_b = await store.list_sources(user_id=user_b)
    stats_b = await store.get_dashboard_stats(user_id=user_b)

    assert len(products_b) == 1
    assert products_b[0].name == "Valve Model B (User B Only)"
    assert len(sources_b) == 1
    assert sources_b[0].origin == "catalog_b.html"
    assert stats_b["total_records"] == 1

    # 5. Query as brand new User C -> zero records returned
    user_c = "usr-user-c-789"
    products_c = await store.list_products(user_id=user_c)
    sources_c = await store.list_sources(user_id=user_c)
    stats_c = await store.get_dashboard_stats(user_id=user_c)

    assert len(products_c) == 0
    assert len(sources_c) == 0
    assert stats_c["total_records"] == 0
