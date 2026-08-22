"""Persistent product catalog store (SQLite Database + In-Memory Cache).

Provides a clean repository interface for product records, sources, and review actions.
Data is persisted to an SQLite database file (sourceledger.db) so all ingested catalog items,
extracted fields, and review actions survive server restarts.

Also syncs records to Supabase Postgres if configured in environment.
"""

import json
import os
import sqlite3
from typing import Optional
from uuid import UUID

from ..models.product_record import (
    FieldStatus,
    ProductField,
    ProductRecord,
    ReviewAction,
    Source,
)
from ..models.schemas import (
    CATEGORY_REGISTRY,
    CorrectionPattern,
    FieldConflict,
    ProductRelationship,
)
from ..utils.logging import get_logger
from .supabase_client import sync_product_to_supabase

logger = get_logger("store")

# SQLite database file path — located inside the backend directory
DB_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "sourceledger.db")
)


class ProductStore:
    """Thread-safe, SQLite-backed persistent product store with in-memory cache.

    All mutations write to SQLite and in-memory cache. Data persists permanently
    across server restarts in sourceledger.db.
    """

    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path
        self._products: dict[UUID, ProductRecord] = {}
        self._sources: dict[UUID, Source] = {}
        self._review_actions: list[ReviewAction] = []
        self._init_sqlite()
        self._load_from_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_sqlite(self) -> None:
        """Create tables if they do not exist and ensure user_id column exists."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sources (
                        id TEXT PRIMARY KEY,
                        content_hash TEXT,
                        data TEXT NOT NULL,
                        user_id TEXT DEFAULT 'default_user',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS products (
                        id TEXT PRIMARY KEY,
                        category TEXT,
                        name TEXT,
                        confidence INTEGER,
                        data TEXT NOT NULL,
                        user_id TEXT DEFAULT 'default_user',
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS review_actions (
                        id TEXT PRIMARY KEY,
                        product_id TEXT,
                        data TEXT NOT NULL,
                        user_id TEXT DEFAULT 'default_user',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS field_conflicts (
                        id TEXT PRIMARY KEY,
                        product_id TEXT NOT NULL,
                        field_name TEXT NOT NULL,
                        data TEXT NOT NULL,
                        user_id TEXT DEFAULT 'default_user',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS product_relationships (
                        id TEXT PRIMARY KEY,
                        source_sku TEXT NOT NULL,
                        target_sku TEXT NOT NULL,
                        relationship_type TEXT NOT NULL,
                        confidence INTEGER NOT NULL,
                        data TEXT NOT NULL,
                        user_id TEXT DEFAULT 'default_user',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS correction_patterns (
                        id TEXT PRIMARY KEY,
                        category TEXT NOT NULL,
                        field_name TEXT NOT NULL,
                        manufacturer TEXT,
                        data TEXT NOT NULL,
                        user_id TEXT DEFAULT 'default_user',
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """
                )
                
                # Migration: add user_id column to existing tables if missing
                for tbl in ["sources", "products", "review_actions", "field_conflicts", "product_relationships", "correction_patterns"]:
                    try:
                        cursor.execute(f"ALTER TABLE {tbl} ADD COLUMN user_id TEXT DEFAULT 'default_user'")
                    except Exception:
                        pass
                conn.commit()
            logger.info("✓ SQLite database initialized at %s", self.db_path)
        except Exception as e:
            logger.error("Failed to initialize SQLite database: %s", e)

    def clear(self) -> None:
        """Clear all stored products, sources, and review actions from DB and memory."""
        self._products.clear()
        self._sources.clear()
        self._review_actions.clear()
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM products")
                cursor.execute("DELETE FROM sources")
                cursor.execute("DELETE FROM review_actions")
                conn.commit()
            logger.info("✓ Cleared all records from SQLite database")
        except Exception as e:
            logger.error("Failed to clear SQLite database: %s", e)


    def _load_from_db(self) -> None:
        """Load stored records from SQLite DB into in-memory cache on startup."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Load sources
                cursor.execute("SELECT data FROM sources")
                for row in cursor.fetchall():
                    try:
                        src = Source.model_validate_json(row["data"])
                        self._sources[src.id] = src
                    except Exception as err:
                        logger.warning("Error parsing source row: %s", err)

                # Load products
                cursor.execute("SELECT data FROM products")
                for row in cursor.fetchall():
                    try:
                        prod = ProductRecord.model_validate_json(row["data"])
                        self._products[prod.id] = prod
                    except Exception as err:
                        logger.warning("Error parsing product row: %s", err)

                # Load review actions
                cursor.execute("SELECT data FROM review_actions")
                for row in cursor.fetchall():
                    try:
                        act = ReviewAction.model_validate_json(row["data"])
                        self._review_actions.append(act)
                    except Exception as err:
                        logger.warning("Error parsing review action row: %s", err)

            logger.info(
                "✓ Loaded %d products, %d sources, and %d review actions from SQLite database.",
                len(self._products),
                len(self._sources),
                len(self._review_actions),
            )
        except Exception as e:
            logger.error("Error loading data from SQLite database: %s", e)

    # ── Sources ──────────────────────────────────────────────────────

    async def save_source(self, source: Source, user_id: str = "default_user") -> Source:
        self._sources[source.id] = source
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO sources (id, content_hash, data, user_id) VALUES (?, ?, ?, ?)",
                    (str(source.id), source.content_hash, source.model_dump_json(), user_id),
                )
                conn.commit()
            logger.info("Saved source %s (user=%s) to SQLite DB", source.id, user_id)
        except Exception as e:
            logger.error("Failed to save source to SQLite DB: %s", e)
        return source

    async def get_source(self, source_id: UUID) -> Optional[Source]:
        return self._sources.get(source_id)

    async def find_source_by_hash(self, content_hash: str) -> Optional[Source]:
        """Look up a source by its content hash — used for idempotency."""
        for source in self._sources.values():
            if source.content_hash == content_hash:
                return source
        return None

    async def list_sources(self, user_id: Optional[str] = None) -> list[Source]:
        if not user_id:
            return list(self._sources.values())
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT data FROM sources WHERE user_id = ?", (user_id,))
                res = []
                for row in cursor.fetchall():
                    res.append(Source.model_validate_json(row["data"]))
                return res
        except Exception:
            return list(self._sources.values())

    # ── Products ─────────────────────────────────────────────────────

    async def save_product(self, product: ProductRecord, user_id: str = "default_user") -> ProductRecord:
        self._products[product.id] = product
        try:
            json_data = product.model_dump_json()
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO products (id, category, name, confidence, data, user_id) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        str(product.id),
                        product.category,
                        product.name,
                        product.confidence_overall,
                        json_data,
                        user_id,
                    ),
                )
                conn.commit()
            logger.info(
                "Saved product %s '%s' (user=%s) to SQLite DB (category=%s, confidence=%d, fields=%d)",
                product.id,
                product.name,
                user_id,
                product.category,
                product.confidence_overall,
                len(product.fields),
            )
            # Sync to Supabase if configured
            await sync_product_to_supabase(
                {
                    "id": str(product.id),
                    "name": product.name,
                    "category": product.category,
                    "confidence_overall": product.confidence_overall,
                    "field_count": len(product.fields),
                    "data": json_data,
                }
            )
        except Exception as e:
            logger.error("Failed to save product to SQLite DB: %s", e)
        return product

    async def get_product(self, product_id: UUID) -> Optional[ProductRecord]:
        return self._products.get(product_id)

    async def list_products(self, user_id: Optional[str] = None) -> list[ProductRecord]:
        if not user_id:
            return list(self._products.values())
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT data FROM products WHERE user_id = ?", (user_id,))
                res = []
                for row in cursor.fetchall():
                    res.append(ProductRecord.model_validate_json(row["data"]))
                return res
        except Exception:
            return list(self._products.values())

    async def update_product(self, product: ProductRecord) -> ProductRecord:
        """Replace a product record entirely (used after review actions)."""
        return await self.save_product(product)

    async def update_field(
        self,
        product_id: UUID,
        field_id: UUID,
        new_value: object = None,
        new_status: Optional[FieldStatus] = None,
    ) -> Optional[ProductField]:
        """Update a single field within a product record and persist."""
        product = self._products.get(product_id)
        if not product:
            return None

        updated_field = None
        for i, field in enumerate(product.fields):
            if field.id == field_id:
                if new_value is not None:
                    field.value = new_value
                if new_status is not None:
                    field.status = new_status
                product.fields[i] = field
                product.confidence_overall = product.compute_overall_confidence()
                updated_field = field
                break

        if updated_field:
            await self.save_product(product)
        return updated_field

    # ── Review Queue ─────────────────────────────────────────────────

    async def get_review_queue(self, user_id: Optional[str] = None) -> list[dict]:
        """Return all fields with status needs_review across all products for user."""
        products = await self.list_products(user_id=user_id)
        items = []
        for product in products:
            schema = CATEGORY_REGISTRY.get(product.category)
            display_name = schema.display_name if schema else product.category
            for field in product.fields:
                if field.status == FieldStatus.NEEDS_REVIEW:
                    items.append(
                        {
                            "field": field,
                            "product_id": product.id,
                            "product_name": product.name,
                            "category": product.category,
                            "category_display_name": display_name,
                        }
                    )
        return items

    async def save_review_action(self, action: ReviewAction, user_id: str = "default_user") -> ReviewAction:
        self._review_actions.append(action)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO review_actions (id, product_id, data, user_id) VALUES (?, ?, ?, ?)",
                    (str(action.id), str(action.product_id), action.model_dump_json(), user_id),
                )
                conn.commit()
            logger.info(
                "Saved review action: %s on field %s (user=%s) to SQLite DB",
                action.action.value,
                action.field_id,
                user_id,
            )
        except Exception as e:
            logger.error("Failed to save review action to SQLite DB: %s", e)
        return action

    async def get_review_actions(self, user_id: Optional[str] = None) -> list[ReviewAction]:
        if not user_id:
            return list(self._review_actions)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT data FROM review_actions WHERE user_id = ?", (user_id,))
                res = []
                for row in cursor.fetchall():
                    res.append(ReviewAction.model_validate_json(row["data"]))
                return res
        except Exception:
            return list(self._review_actions)

    # ── Dashboard Stats ──────────────────────────────────────────────

    async def get_dashboard_stats(self, user_id: Optional[str] = None) -> dict:
        """Compute catalog-wide quality statistics for user."""
        products = await self.list_products(user_id=user_id)
        all_fields: list[ProductField] = []
        for p in products:
            all_fields.extend(p.fields)

        total_fields = len(all_fields)
        auto_committed = sum(
            1 for f in all_fields if f.status == FieldStatus.AUTO_COMMITTED
        )
        needs_review = sum(
            1 for f in all_fields if f.status == FieldStatus.NEEDS_REVIEW
        )
        human_corrected = sum(
            1 for f in all_fields if f.status == FieldStatus.HUMAN_CORRECTED
        )

        avg_confidence = (
            sum(f.confidence for f in all_fields) / total_fields
            if total_fields > 0
            else 0.0
        )

        # Per-category breakdowns
        confidence_by_cat: dict[str, list[int]] = {}
        records_by_cat: dict[str, int] = {}
        for p in products:
            records_by_cat[p.category] = records_by_cat.get(p.category, 0) + 1
            if p.category not in confidence_by_cat:
                confidence_by_cat[p.category] = []
            confidence_by_cat[p.category].append(p.confidence_overall)

        avg_conf_by_cat = {
            cat: sum(vals) / len(vals) if vals else 0.0
            for cat, vals in confidence_by_cat.items()
        }

        return {
            "total_records": len(products),
            "total_fields": total_fields,
            "auto_committed_count": auto_committed,
            "needs_review_count": needs_review,
            "human_corrected_count": human_corrected,
            "auto_committed_pct": (
                auto_committed / total_fields * 100 if total_fields > 0 else 0.0
            ),
            "needs_review_pct": (
                needs_review / total_fields * 100 if total_fields > 0 else 0.0
            ),
            "average_confidence": round(avg_confidence, 1),
            "confidence_by_category": {
                k: round(v, 1) for k, v in avg_conf_by_cat.items()
            },
            "records_by_category": records_by_cat,
        }

    # ── Phase 7: Field Conflicts Methods ─────────────────────────────────

    def save_field_conflict(self, conflict: FieldConflict, user_id: str = "default_user") -> None:
        """Persist a FieldConflict entity to SQLite."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO field_conflicts (id, product_id, field_name, data, user_id)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (
                        str(conflict.id),
                        str(conflict.product_id),
                        conflict.field_name,
                        conflict.model_dump_json(),
                        user_id,
                    ),
                )
                conn.commit()
            logger.info(
                "✓ Saved FieldConflict for product %s, field %s (user=%s)",
                str(conflict.product_id)[:8],
                conflict.field_name,
                user_id,
            )
        except Exception as e:
            logger.error("Failed to save FieldConflict: %s", e)

    def list_field_conflicts(self, product_id: Optional[UUID] = None, user_id: Optional[str] = None) -> list[FieldConflict]:
        """Fetch all field conflicts, optionally filtered by product_id and user_id."""
        conflicts: list[FieldConflict] = []
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if product_id and user_id:
                    cursor.execute(
                        "SELECT data FROM field_conflicts WHERE product_id = ? AND user_id = ?",
                        (str(product_id), user_id),
                    )
                elif product_id:
                    cursor.execute(
                        "SELECT data FROM field_conflicts WHERE product_id = ?",
                        (str(product_id),),
                    )
                elif user_id:
                    cursor.execute(
                        "SELECT data FROM field_conflicts WHERE user_id = ?",
                        (user_id,),
                    )
                else:
                    cursor.execute("SELECT data FROM field_conflicts")
                for row in cursor.fetchall():
                    conflicts.append(FieldConflict.model_validate_json(row["data"]))
        except Exception as e:
            logger.error("Failed to list field conflicts: %s", e)
        return conflicts

    # ── Phase 8: Product Relationships Methods ────────────────────────────

    def save_product_relationship(self, rel: ProductRelationship, user_id: str = "default_user") -> None:
        """Persist a ProductRelationship graph edge to SQLite."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO product_relationships
                    (id, source_sku, target_sku, relationship_type, confidence, data, user_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        str(rel.id),
                        rel.source_sku,
                        rel.target_sku,
                        rel.relationship_type,
                        rel.confidence,
                        rel.model_dump_json(),
                        user_id,
                    ),
                )
                conn.commit()
            logger.info("✓ Saved ProductRelationship %s -> %s (user=%s)", rel.source_sku, rel.target_sku, user_id)
        except Exception as e:
            logger.error("Failed to save ProductRelationship: %s", e)

    def list_product_relationships(self, sku: Optional[str] = None, user_id: Optional[str] = None) -> list[ProductRelationship]:
        """Fetch graph relationships, optionally filtered by SKU and user_id."""
        rels: list[ProductRelationship] = []
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if sku and user_id:
                    cursor.execute(
                        "SELECT data FROM product_relationships WHERE (source_sku = ? OR target_sku = ?) AND user_id = ?",
                        (sku, sku, user_id),
                    )
                elif sku:
                    cursor.execute(
                        "SELECT data FROM product_relationships WHERE source_sku = ? OR target_sku = ?",
                        (sku, sku),
                    )
                elif user_id:
                    cursor.execute("SELECT data FROM product_relationships WHERE user_id = ?", (user_id,))
                else:
                    cursor.execute("SELECT data FROM product_relationships")
                for row in cursor.fetchall():
                    rels.append(ProductRelationship.model_validate_json(row["data"]))
        except Exception as e:
            logger.error("Failed to list product relationships: %s", e)
        return rels

    # ── Phase 10: Correction Pattern Active Learning Methods ──────────────

    def save_correction_pattern(self, pattern: CorrectionPattern) -> None:
        """Persist or update a CorrectionPattern."""
        pat_id = f"{pattern.category}:{pattern.field_name}:{pattern.manufacturer or 'all'}"
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO correction_patterns
                    (id, category, field_name, manufacturer, data)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (
                        pat_id,
                        pattern.category,
                        pattern.field_name,
                        pattern.manufacturer or "all",
                        pattern.model_dump_json(),
                    ),
                )
                conn.commit()
        except Exception as e:
            logger.error("Failed to save CorrectionPattern: %s", e)

    def get_correction_patterns(self) -> list[CorrectionPattern]:
        """List all active learning correction patterns."""
        patterns: list[CorrectionPattern] = []
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT data FROM correction_patterns")
                for row in cursor.fetchall():
                    patterns.append(CorrectionPattern.model_validate_json(row["data"]))
        except Exception as e:
            logger.error("Failed to get correction patterns: %s", e)
        return patterns


# ── Singleton ────────────────────────────────────────────────────────
# Single store instance shared across the application lifetime.

store = ProductStore()

