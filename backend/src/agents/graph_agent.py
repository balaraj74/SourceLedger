"""Product Knowledge Graph Agent (Phase 8).

Builds linked product intelligence across validated catalog records by detecting
variant families, substitutes, compatible accessories, and product lines based on
grounded part-number prefixes/suffixes, manufacturer product lines, and category attributes.
"""

from typing import Any, List, Optional
from ..db.store import store
from ..models.product_record import ProductRecord
from ..models.schemas import ProductRelationship
from ..utils.logging import get_logger, log_agent_step

logger = get_logger("GraphAgent")


class GraphAgent:
    """Agent that analyzes validated catalog records to construct product relationship edges."""

    def __init__(self, store_instance: Optional[Any] = None) -> None:
        self.store = store_instance or store

    async def analyze_catalog(self, products: Optional[List[ProductRecord]] = None) -> List[ProductRelationship]:
        """Analyze validated catalog products and construct product relationship edges."""
        if products is None:
            products = await self.store.list_products()

        # Rule: only link validated records with confidence >= 60
        valid_products = [p for p in products if p.confidence_overall >= 60]
        if len(valid_products) < 2:
            return []

        relationships: List[ProductRelationship] = []

        with log_agent_step(logger, "GraphAgent", f"analyzing {len(valid_products)} products") as ctx:
            for i in range(len(valid_products)):
                for j in range(i + 1, len(valid_products)):
                    p1 = valid_products[i]
                    p2 = valid_products[j]
                    
                    sku1 = p1.mfg_part_num or p1.name
                    sku2 = p2.mfg_part_num or p2.name
                    
                    if not sku1 or not sku2 or sku1 == sku2:
                        continue

                    # 1. Variant / Pack Size Detection (Prefix/Suffix Match)
                    clean1 = sku1.split("-")[0].strip()
                    clean2 = sku2.split("-")[0].strip()
                    
                    if len(clean1) >= 4 and clean1 == clean2:
                        rel = ProductRelationship(
                            source_sku=sku1,
                            target_sku=sku2,
                            relationship_type="variant_of",
                            confidence=95,
                            reasoning=f"Matching base part number '{clean1}' with variant suffix difference.",
                            evidence_field="mfg_part_num",
                        )
                        relationships.append(rel)
                        self.store.save_product_relationship(rel)
                        continue

                    # 2. Same Family Detection (Shared Manufacturer + Category Class)
                    mfr1 = next((str(f.value) for f in p1.fields if f.name.lower() in ("manufacturer", "part_manuf", "brand")), "").lower()
                    mfr2 = next((str(f.value) for f in p2.fields if f.name.lower() in ("manufacturer", "part_manuf", "brand")), "").lower()

                    if mfr1 and mfr2 and mfr1 == mfr2 and p1.category == p2.category and p1.category != "generic":
                        rel = ProductRelationship(
                            source_sku=sku1,
                            target_sku=sku2,
                            relationship_type="same_family",
                            confidence=85,
                            reasoning=f"Shared manufacturer '{mfr1.title()}' and category '{p1.category}'.",
                            evidence_field="manufacturer",
                        )
                        relationships.append(rel)
                        self.store.save_product_relationship(rel)
                        continue

                    # 3. Substitute Detection (Matching Category Schema Specs)
                    if p1.category == p2.category and p1.category in ("industrial_pump", "safety_fastener", "electrical_connector"):
                        specs1 = {f.name: str(f.value) for f in p1.fields if f.value is not None}
                        specs2 = {f.name: str(f.value) for f in p2.fields if f.value is not None}
                        
                        shared_keys = set(specs1.keys()) & set(specs2.keys())
                        matching_keys = [k for k in shared_keys if specs1[k].lower() == specs2[k].lower()]
                        
                        if len(matching_keys) >= 3:
                            rel = ProductRelationship(
                                source_sku=sku1,
                                target_sku=sku2,
                                relationship_type="substitute_for",
                                confidence=80,
                                reasoning=f"Matching specifications across {len(matching_keys)} fields ({', '.join(matching_keys[:3])}).",
                                evidence_field=", ".join(matching_keys[:3]),
                            )
                            relationships.append(rel)
                            self.store.save_product_relationship(rel)

            ctx["output_summary"] = f"Detected {len(relationships)} product relationships"

        return relationships
