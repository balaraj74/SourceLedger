"""Schema.org / Product JSON-LD Exporter (Phase 12c).

Converts validated ProductRecord objects into standard schema.org/Product
JSON-LD structures suitable for e-commerce search engines, PIM, and market syndication.
"""

from typing import Any, Dict, List
from ..models.product_record import ProductRecord


def export_product_to_jsonld(product: ProductRecord) -> Dict[str, Any]:
    """Convert a single ProductRecord to schema.org/Product JSON-LD."""
    fields_dict = {f.name.lower(): str(f.value) for f in product.fields if f.value is not None}

    mfr = fields_dict.get("manufacturer") or fields_dict.get("brand") or fields_dict.get("part_manuf") or "Unknown Brand"
    sku = product.mfg_part_num or product.name
    desc = fields_dict.get("short_desc") or fields_dict.get("long_desc1") or product.name

    jsonld: Dict[str, Any] = {
        "@context": "https://schema.org/",
        "@type": "Product",
        "name": product.name,
        "sku": sku,
        "mpn": sku,
        "description": desc,
        "category": product.category,
        "brand": {
            "@type": "Brand",
            "name": mfr,
        },
    }

    # Add pricing if available
    price = fields_dict.get("list_price") or fields_dict.get("price")
    if price:
        jsonld["offers"] = {
            "@type": "Offer",
            "price": price.replace("$", "").strip(),
            "priceCurrency": "USD",
            "availability": "https://schema.org/InStock",
        }

    # Add image if available
    img = fields_dict.get("product_image") or fields_dict.get("image_url")
    if img and img.startswith("http"):
        jsonld["image"] = img

    # Add structured additional specs
    additional_props: List[Dict[str, str]] = []
    for f in product.fields:
        if f.value is not None and f.name.lower() not in ("manufacturer", "brand", "part_manuf", "short_desc", "long_desc1", "list_price", "price"):
            additional_props.append({
                "@type": "PropertyValue",
                "name": f.display_name or f.name.replace("_", " ").title(),
                "value": str(f.value),
            })

    if additional_props:
        jsonld["additionalProperty"] = additional_props

    return jsonld


def export_catalog_to_jsonld(products: List[ProductRecord]) -> List[Dict[str, Any]]:
    """Convert a list of ProductRecords to a list of schema.org/Product JSON-LD objects."""
    return [export_product_to_jsonld(p) for p in products]
