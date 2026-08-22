"""CSV Exporter — maps ProductRecord fields to the Unihack 252-column delivery format.

The delivery format has:
- Fixed columns (MFR URL, SHORT_DESC, LONG_DESC1, …)
- ITEM_FEATURES_1 … ITEM_FEATURES_20 (one feature per column)
- ATTRIBUTE_LABEL n / ATTRIBUTE_VALUE n / ATTRIBUTE_UOM n × 50 triplets
- Document links (Specification Sheet, Owners/User Manual, …)
- Dimensional and packaging fields (LENGTH, HEIGHT, WIDTH, WEIGHT, …)
- Product images, country of origin, discontinued flag

This module is the single source of truth for how our field names map to
the delivery column names. Any schema change should be reflected here.
"""

import csv
import io
import json
from typing import Any, Dict, List, Optional

from ..models.product_record import ProductField, ProductRecord
from ..models.unihack_schema import map_product_fields_to_unihack_row
from ..utils.logging import get_logger

logger = get_logger("csv_exporter")

# ── The exact 252-column header row ──────────────────────────────────
DELIVERY_COLUMNS = [
    "MFR URL", "Ref URL 1", "Ref URL 2", "Ref URL 3", "Ref URL 4", "Ref URL 5",
    "PART_NUMBER", "Dept", "Class", "Fine",
    "SKU - MY_PART_NUMBER", "Mfg_Part_Num", "Part_Desc",
    "E1_Brand", "Unilog_Brand", "DIB_Brand", "Part_Manuf",
    "MANUFACTURER_NAME", "BRAND_NAME", "TRADE_NAME",
    "MANUFACTURER_PART_NUMBER", "ALTERNATE_PART_NUMBER",
    "Classpath",
    "MOBILE_DESC", "INVOICE_DESC", "SHORT_DESC", "LONG_DESC1",
    "RETAIL_DESC", "MARKETING_DESCRIPTION",
    *[f"ITEM_FEATURES_{i}" for i in range(1, 21)],
    "With", "Standard/Approvals", "Prop 65", "Application", "Includes",
    "Product Name",
    *[col for i in range(1, 51) for col in (
        f"ATTRIBUTE_LABEL {i}", f"ATTRIBUTE_VALUE {i}", f"ATTRIBUTE_UOM {i}"
    )],
    "UPC", "EAN", "GTIN", "UNSPSC",
    "Warranty", "List Price", "Selling Qty", "Selling UOM",
    "Standard Packaging Information",
    "LENGTH", "LENGTH_UOM", "HEIGHT", "HEIGHT_UOM",
    "WIDTH", "WIDTH_UOM", "WEIGHT", "WEIGHT_UOM",
    "VOLUME", "VOLUME_UOM",
    "Product Image",
    "Alternate Image 1", "Alternate Image 2", "Alternate Image 3", "Alternate Image 4",
    "SDS", "SDS_1", "Warranty Information", "Catalog",
    "Specification Sheet", "Instruction/Installation Manual",
    "Service Manual", "Owners/User Manual",
    "Line Drawing", "MTR", "RoHS", "Full Engineering Drawing",
    "Energy Star Guide", "Technical Bulletin", "Submittal",
    "Compatibility Chart", "Size Chart", "Product Label/Insert",
    "Video Link", "Video Link 1",
    "Country Of Origin", "Discontinued", "Actual Image (Yes/No)",
]

# ── Internal field name → delivery column name ────────────────────────
# Fields in this map are written directly into their fixed columns.
# All other extracted fields go into ATTRIBUTE_LABEL/VALUE/UOM slots.
FIXED_FIELD_MAP: Dict[str, str] = {
    # URLs
    "mfr_url":              "MFR URL",
    "specification_sheet":  "Specification Sheet",
    "product_image":        "Product Image",
    "owners_manual":        "Owners/User Manual",
    "sds":                  "SDS",
    "video_link":           "Video Link",

    # Identity
    "part_number":          "PART_NUMBER",
    "mfg_part_num":         "Mfg_Part_Num",
    "model_number":         "PART_NUMBER",          # fallback for PART_NUMBER
    "part_desc":            "Part_Desc",
    "product_name_field":   "Product Name",

    # Taxonomy
    "dept":                 "Dept",
    "category_class":       "Class",
    "fine_category":        "Fine",
    "classpath":            "Classpath",
    "category_path":        "Classpath",            # alias

    # Manufacturer / brand
    "manufacturer":         "MANUFACTURER_NAME",
    "brand":                "BRAND_NAME",
    "trade_name":           "TRADE_NAME",
    "alternate_part_number":"ALTERNATE_PART_NUMBER",

    # Descriptions
    "short_desc":           "SHORT_DESC",
    "long_desc1":           "LONG_DESC1",
    "long_desc2":           "RETAIL_DESC",
    "marketing_description":"MARKETING_DESCRIPTION",
    "mobile_desc":          "MOBILE_DESC",
    "invoice_desc":         "INVOICE_DESC",
    "retail_desc":          "RETAIL_DESC",

    # Certifications / compliance
    "certifications":       "Standard/Approvals",
    "standard_approvals":   "Standard/Approvals",
    "rohs":                 "RoHS",

    # Identifiers
    "upc":                  "UPC",
    "ean":                  "EAN",
    "gtin":                 "GTIN",
    "unspsc_code":          "UNSPSC",
    "unspsc":               "UNSPSC",

    # Dimensions / packaging
    "length":               "LENGTH",
    "height":               "HEIGHT",
    "width":                "WIDTH",
    "weight":               "WEIGHT",
    "warranty":             "Warranty",
    "list_price":           "List Price",

    # Origin / status
    "country_of_origin":        "Country Of Origin",
    "country_of_manufacture":   "Country Of Origin",
    "discontinued":             "Discontinued",
}

# Fields to SKIP — used internally but never exported as attributes
_SKIP_FIELDS = {
    "item_features", "item_keywords", "item_key_selling_points",
    "category_path",  # handled via Classpath
    "part_manuf",     # handled via MANUFACTURER_NAME
    "long_desc2",     # handled via RETAIL_DESC
}

# Fields already placed in fixed columns — excluded from ATTRIBUTE slots
_FIXED_ONLY = set(FIXED_FIELD_MAP.keys()) | _SKIP_FIELDS


def _get(fields: Dict[str, ProductField], *keys: str) -> str:
    """Return the string value of the first matching key, or empty string."""
    for k in keys:
        f = fields.get(k)
        if f and f.value is not None:
            v = f.value
            if isinstance(v, list):
                return "; ".join(str(x) for x in v)
            return str(v)
    return ""


def _get_list(fields: Dict[str, ProductField], key: str) -> List[str]:
    """Return a list value or empty list."""
    f = fields.get(key)
    if f and isinstance(f.value, list):
        return [str(x) for x in f.value]
    if f and f.value:
        # Might be a JSON-encoded list string
        try:
            parsed = json.loads(str(f.value))
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except Exception:
            pass
        return [str(f.value)]
    return []


def product_record_to_row(product: ProductRecord) -> Dict[str, str]:
    """Map a product through the canonical source-backed delivery mapper."""
    mapped = map_product_fields_to_unihack_row(product.fields, title=product.name, sku="")
    return {column: mapped.get(column, "") for column in DELIVERY_COLUMNS}

def products_to_csv_bytes(products: List[ProductRecord]) -> bytes:
    """Serialize a list of ProductRecords to UTF-8 BOM CSV bytes (Excel-compatible).

    Returns the complete CSV file contents as bytes, ready to send as a
    file download response.
    """
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=DELIVERY_COLUMNS,
        extrasaction="ignore",
        lineterminator="\r\n",
        quoting=csv.QUOTE_MINIMAL,
    )
    writer.writeheader()
    for product in products:
        try:
            row = product_record_to_row(product)
            writer.writerow(row)
        except Exception as e:
            logger.error("csv_exporter: failed to export product '%s': %s", product.name, e)

    # UTF-8 BOM for Excel compatibility (matches the sample file)
    return "\ufeff".encode("utf-8") + buf.getvalue().encode("utf-8")


def single_product_to_csv_bytes(product: ProductRecord) -> bytes:
    """Export a single ProductRecord to CSV bytes."""
    return products_to_csv_bytes([product])
