"""Unihack E-Commerce Delivery Schema & Export Formatter.

Defines the exact 252 columns required by Unihack_ Expected Output - Delivery Format.csv
and maps SourceLedger ProductRecord objects into compliance rows.
"""

import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

UNIHACK_DELIVERY_COLUMNS: List[str] = [
    'MFR URL', 'Ref URL 1', 'Ref URL 2', 'Ref URL 3', 'Ref URL 4', 'Ref URL 5',
    'PART_NUMBER', 'Dept', 'Class', 'Fine', 'SKU - MY_PART_NUMBER', 'Mfg_Part_Num',
    'Part_Desc', 'E1_Brand', 'Unilog_Brand', 'DIB_Brand', 'Part_Manuf',
    'MANUFACTURER_NAME', 'BRAND_NAME', 'TRADE_NAME', 'MANUFACTURER_PART_NUMBER',
    'ALTERNATE_PART_NUMBER', 'Classpath', 'MOBILE_DESC', 'INVOICE_DESC',
    'SHORT_DESC', 'LONG_DESC1', 'RETAIL_DESC', 'MARKETING_DESCRIPTION',
] + [f'ITEM_FEATURES_{i}' for i in range(1, 21)] + [
    'With', 'Standard/Approvals', 'Prop 65', 'Application', 'Includes', 'Product Name',
]

# Add ATTRIBUTE_LABEL 1..50, ATTRIBUTE_VALUE 1..50, ATTRIBUTE_UOM 1..50
for i in range(1, 51):
    UNIHACK_DELIVERY_COLUMNS.extend([
        f'ATTRIBUTE_LABEL {i}',
        f'ATTRIBUTE_VALUE {i}',
        f'ATTRIBUTE_UOM {i}',
    ])

UNIHACK_DELIVERY_COLUMNS.extend([
    'UPC', 'EAN', 'GTIN', 'UNSPSC', 'Warranty', 'List Price', 'Selling Qty', 'Selling UOM',
    'Standard Packaging Information', 'LENGTH', 'LENGTH_UOM', 'HEIGHT', 'HEIGHT_UOM',
    'WIDTH', 'WIDTH_UOM', 'WEIGHT', 'WEIGHT_UOM', 'VOLUME', 'VOLUME_UOM',
    'Product Image', 'Alternate Image 1', 'Alternate Image 2', 'Alternate Image 3', 'Alternate Image 4',
    'SDS', 'SDS_1', 'Warranty Information', 'Catalog', 'Specification Sheet',
    'Instruction/Installation Manual', 'Service Manual', 'Owners/User Manual',
    'Line Drawing', 'MTR', 'RoHS', 'Full Engineering Drawing', 'Energy Star Guide',
    'Technical Bulletin', 'Submittal', 'Compatibility Chart', 'Size Chart',
    'Product Label/Insert', 'Video Link', 'Video Link 1', 'Country Of Origin',
    'Discontinued', 'Actual Image (Yes/No)'
])


class AttributeTriplet(BaseModel):
    label: str
    value: str
    uom: str = ""


class UnihackExtractionPayload(BaseModel):
    """Structured extraction payload produced by Agents using google.genai."""
    product_name: str = Field(description="Primary Product Name")
    manufacturer_name: str = Field(default="", description="Manufacturer Name")
    brand_name: str = Field(default="", description="Brand Name")
    mfg_part_num: str = Field(default="", description="Manufacturer Part Number")
    part_number: str = Field(default="", description="Internal or Catalog Part Number")
    dept: str = Field(default="", description="Department category")
    category_class: str = Field(default="", description="Product class")
    fine_category: str = Field(default="", description="Fine product category")
    classpath: str = Field(default="", description="Full taxonomy path e.g. Dept > Class > Fine")

    short_desc: str = Field(default="", description="Short e-commerce summary description")
    long_desc1: str = Field(default="", description="Detailed e-commerce product description")
    marketing_description: str = Field(default="", description="Marketing / promotional overview")
    mobile_desc: str = Field(default="", description="Concise mobile app product description")
    invoice_desc: str = Field(default="", description="Short billing/invoice line description")

    item_features: List[str] = Field(default_factory=list, description="List of up to 20 key features/bullet points")
    attributes: List[AttributeTriplet] = Field(default_factory=list, description="Technical attribute label, value, uom triplets up to 50")

    standards_approvals: str = Field(default="", description="Standards / Certifications e.g. CE, UL, NSF, Energy Star")
    application: str = Field(default="", description="Intended application or environment")
    includes: str = Field(default="", description="Included accessories or package contents")
    with_feature: str = Field(default="", description="Notable 'With' feature e.g. With CleanBoost")

    mfr_url: str = Field(default="", description="Official Manufacturer Product URL")
    ref_urls: List[str] = Field(default_factory=list, description="Reference URLs")
    product_image: str = Field(default="", description="Primary Product Image URL or filename")
    specification_sheet: str = Field(default="", description="PDF Specification Sheet link/filename")
    owners_manual: str = Field(default="", description="Owners / User Manual PDF link/filename")
    installation_manual: str = Field(default="", description="Installation Manual PDF link/filename")
    country_of_origin: str = Field(default="", description="Country of origin")


# ── Approved UOM & Decimal Fraction Normalization ───────────────────────────

DECIMAL_TO_FRACTION_MAP = {
    0.5: "1/2", 0.25: "1/4", 0.75: "3/4",
    0.125: "1/8", 0.375: "3/8", 0.625: "5/8", 0.875: "7/8",
    0.0625: "1/16", 0.1875: "3/16", 0.3125: "5/16", 0.4375: "7/16",
    0.5625: "9/16", 0.6875: "11/16", 0.8125: "13/16", 0.9375: "15/16",
}

APPROVED_UOM_MAP = {
    "inch": "in", "inches": "in", "in.": "in",
    "foot": "ft", "feet": "ft", "ft.": "ft",
    "yard": "yd", "yards": "yd",
    "millimeter": "mm", "millimeters": "mm",
    "centimeter": "cm", "centimeters": "cm",
    "meter": "m", "meters": "m",
    "volt": "V", "volts": "V", "v": "V",
    "amp": "A", "amps": "A", "ampere": "A", "amperes": "A",
    "watt": "W", "watts": "W",
    "pound": "lbs", "pounds": "lbs", "lb": "lbs", "lbs.": "lbs",
    "ounce": "oz", "ounces": "oz", "oz.": "oz",
    "kilogram": "kg", "kilograms": "kg",
    "gram": "g", "grams": "g",
    "gallon": "gal", "gallons": "gal",
}

def normalize_uom(uom_str: str) -> str:
    """Normalize unit string to approved Unilog Master UOM abbreviation."""
    if not uom_str:
        return ""
    clean = uom_str.strip().lower()
    return APPROVED_UOM_MAP.get(clean, uom_str.strip())


def normalize_decimal_dimension(val_str: str) -> str:
    """Convert decimal dimension values to fractional inches (e.g. 50.25 in -> 50-1/4 in)."""
    if not val_str:
        return ""
    import re
    match = re.match(r"^(\d+)\.(\d+)(\s*[a-zA-Z]*)$", val_str.strip())
    if match:
        whole = int(match.group(1))
        dec = float(f"0.{match.group(2)}")
        unit = match.group(3).strip()
        # Find closest fraction match
        closest = min(DECIMAL_TO_FRACTION_MAP.keys(), key=lambda k: abs(k - dec))
        if abs(closest - dec) <= 0.02:
            frac = DECIMAL_TO_FRACTION_MAP[closest]
            norm_unit = normalize_uom(unit) or "in"
            prefix = f"{whole}-" if whole > 0 else ""
            return f"{prefix}{frac} {norm_unit}".strip()
    return val_str.strip()


def build_invoice_desc(brand: str, prod_name: str, mpn: str) -> str:
    """Generate INVOICE_DESC (<= 40 chars, ALL UPPERCASE) per Content Guidelines."""
    base = f"{brand} {prod_name} {mpn}".strip().upper()
    # Replace symbols and strip
    base = base.replace("®", "").replace("™", "")
    if len(base) <= 40:
        return base
    # Truncate cleanly
    return base[:40].strip()


def build_mobile_desc(mfr: str, brand: str, prod_name: str, mpn: str) -> str:
    """Generate MOBILE_DESC (60-80 chars) per Content Guidelines."""
    base = f"{mfr} {brand}, {prod_name}, {mpn}".strip()
    if 60 <= len(base) <= 80:
        return base
    if len(base) < 60:
        base = f"{mfr} {brand} Professional {prod_name}, Model {mpn}".strip()
    return base[:80].strip()


def map_product_fields_to_unihack_row(fields: List[Any], title: str = "", sku: str = "") -> Dict[str, str]:
    """Converts SourceLedger ProductRecord fields to the 252-column Unihack delivery row."""
    row: Dict[str, str] = {col: "" for col in UNIHACK_DELIVERY_COLUMNS}

    # -- Build a fast name→value lookup (handle list values as-is)
    field_map: Dict[str, Any] = {}
    for f in fields:
        if f.value is not None and f.name not in field_map:
            field_map[f.name] = f.value

    def _val(*keys: str) -> str:
        """Return string value of first matching key, joining lists with semicolons."""
        for k in keys:
            v = field_map.get(k)
            if v is not None:
                if isinstance(v, list):
                    return "; ".join(str(x) for x in v if x)
                s = str(v).strip()
                if s:
                    return s
        return ""

    def _list(*keys: str) -> List[str]:
        for k in keys:
            v = field_map.get(k)
            if isinstance(v, list):
                return [str(x) for x in v]
            if isinstance(v, str) and v:
                try:
                    import json
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        return [str(x) for x in parsed]
                except Exception:
                    pass
                return [v]
        return []

    # ── Brand placeholders ────────────────────────────────────────────
    row["E1_Brand"] = _val("e1_brand")
    row["Unilog_Brand"] = _val("unilog_brand")
    row["DIB_Brand"] = _val("dib_brand")
    row["Part_Manuf"] = _val("part_manuf")
    row["Discontinued"] = _val("discontinued")

    # ── Identity and taxonomy: preserve source values; never substitute guesses.
    prod_name = _val("product_name", "part_desc") or title
    mfg_part = _val("mfg_part_num", "manufacturer_part_number", "model_number", "part_number", "part_num")
    source_sku = _val("sku_my_part_number", "sku") or sku
    supplied_internal = _val("internal_part_number")
    identity_for_internal = mfg_part or source_sku
    if supplied_internal and supplied_internal != identity_for_internal:
        internal_part = supplied_internal
    elif identity_for_internal:
        import hashlib
        internal_part = "SL-" + hashlib.sha256(identity_for_internal.encode("utf-8")).hexdigest()[:12].upper()
    else:
        internal_part = ""

    mfr_name = _val("manufacturer_name", "manufacturer", "part_manuf", "e1_brand", "unilog_brand", "dib_brand", "brand")
    brand_name = _val("brand_name", "brand", "part_manuf", "e1_brand", "unilog_brand", "dib_brand", "manufacturer")
    dept = _val("dept")
    cls = _val("category_class", "class")
    fine = _val("fine_category", "fine")
    classpath = _val("classpath", "category_path")
    if not classpath and dept and cls and fine:
        classpath = f"{dept}>{cls}>{fine}"

    row["Product Name"] = prod_name
    row["Part_Desc"] = _val("part_desc") or prod_name
    row["MANUFACTURER_NAME"] = mfr_name
    row["BRAND_NAME"] = brand_name
    row["Mfg_Part_Num"] = mfg_part
    row["MANUFACTURER_PART_NUMBER"] = mfg_part
    row["PART_NUMBER"] = internal_part
    row["SKU - MY_PART_NUMBER"] = source_sku
    row["ALTERNATE_PART_NUMBER"] = _val("alternate_part_number")
    row["TRADE_NAME"] = _val("trade_name")
    row["Dept"] = dept
    row["Class"] = cls
    row["Fine"] = fine
    row["Classpath"] = classpath

    # ── Descriptions ─────────────────────────────────────────────────
    short = _val('short_desc') or prod_name
    long1 = _val('long_desc1', 'marketing_description') or short

    mob = _val("mobile_desc") or build_mobile_desc(mfr_name or brand_name or "Industrial", brand_name or mfr_name or "Brand", prod_name, mfg_part)
    inv = _val("invoice_desc") or build_invoice_desc(brand_name or mfr_name or "GENERIC", prod_name, mfg_part)

    row["SHORT_DESC"] = short
    row["LONG_DESC1"] = long1
    row["RETAIL_DESC"] = _val("long_desc2", "retail_desc") or short
    row["MARKETING_DESCRIPTION"] = _val("marketing_description") or long1
    row["MOBILE_DESC"] = mob
    row["INVOICE_DESC"] = inv

    # ── ITEM_FEATURES_1…20 ───────────────────────────────────────────
    features = _list('item_features')
    for idx, feat in enumerate(features[:20], start=1):
        row[f'ITEM_FEATURES_{idx}'] = feat

    # Fill any empty feature slots with key selling points
    selling = _list('item_key_selling_points', 'key_selling_points')
    filled = sum(1 for i in range(1, 21) if row.get(f'ITEM_FEATURES_{i}'))
    for idx, pt in enumerate(selling[:20 - filled], start=filled + 1):
        row[f'ITEM_FEATURES_{idx}'] = pt

    # ── Compliance & application ──────────────────────────────────────
    certs = _list('certifications', 'standards_approvals')
    row['Standard/Approvals'] = "; ".join(certs) if certs else _val('standard_approvals')
    row['Application']        = _val('application')
    row['Includes']           = _val('includes')
    row['With']               = _val('with_feature')
    row['Prop 65']            = _val('prop_65')

    # ── Media & documents ─────────────────────────────────────────────
    row['MFR URL']                          = _val('mfr_url', 'manufacturer_url')
    row['Product Image']                    = _val('product_image')
    row['Alternate Image 1']                = _val('alternate_image_1')
    row['Alternate Image 2']                = _val('alternate_image_2')
    row['Specification Sheet']              = _val('specification_sheet')
    row['Owners/User Manual']               = _val('owners_manual', 'owners_user_manual')
    row['Instruction/Installation Manual']  = _val('installation_manual')
    row['Service Manual']                   = _val('service_manual')
    row['SDS']                              = _val('sds')
    row['Video Link']                       = _val('video_link')
    row['RoHS']                             = _val('rohs')
    row['Actual Image (Yes/No)']            = 'Yes' if row['Product Image'] else ''

    # ── Identifiers & Pricing ───────────────────────────────────────────
    row["UPC"] = _val("upc")
    row["EAN"] = _val("ean")
    row["GTIN"] = _val("gtin")
    row["UNSPSC"] = _val("unspsc_code", "unspsc")
    row["List Price"] = _val("list_price")
    row["Selling Qty"] = _val("selling_qty")
    row["Selling UOM"] = _val("selling_uom")

    # ── Dimensions & weight ──────────────────────────────────────────────
    row['LENGTH']      = _val('length')
    row["LENGTH_UOM"] = _val("length_uom") if row["LENGTH"] else ""
    row["HEIGHT"] = _val("height")
    row["HEIGHT_UOM"] = _val("height_uom") if row["HEIGHT"] else ""
    row["WIDTH"] = _val("width")
    row["WIDTH_UOM"] = _val("width_uom") if row["WIDTH"] else ""
    row["WEIGHT"] = _val("weight")
    row["WEIGHT_UOM"] = _val("weight_uom") if row["WEIGHT"] else ""

    # ── Country of origin ────────────────────────────────────────────────
    row['Country Of Origin'] = _val('country_of_origin', 'country_of_manufacture')

    # ── Compliance & application (now populated by enrichment LLM) ────────
    row['Application'] = _val('application')
    row['Includes']    = _val('includes')
    row['Warranty']    = _val('warranty')
    row['Prop 65']     = _val('prop_65')
    row['Standard/Approvals'] = (
        "; ".join(_list('certifications', 'standards_approvals'))
        or _val('standard_approvals', 'standards_approvals')
    )

    # ── Ref URLs ─────────────────────────────────────────────────────────
    # Merge ref_urls list + individual ref_url_1..5 fields from enrichment
    all_ref_urls = [
        _val('ref_url_1'), _val('ref_url_2'),
        _val('ref_url_3'), _val('ref_url_4'), _val('ref_url_5'),
    ] + _list('ref_urls')
    seen_refs: set = set()
    ref_slot = 1
    for u in all_ref_urls:
        if u and u not in seen_refs:
            row[f'Ref URL {ref_slot}'] = u
            seen_refs.add(u)
            ref_slot += 1
            if ref_slot > 5:
                break

    # ── Phase 2: item_features_N → ITEM_FEATURES_N columns ──────────────────
    # Multi-phase extractor emits individual item_features_1…20 fields.
    # Map them directly to their output columns before the generic attr loop.
    import re as _re
    for f in fields:
        m = _re.match(r"^item_features_(\d+)$", f.name)
        if m:
            idx = int(m.group(1))
            if 1 <= idx <= 20 and not row.get(f"ITEM_FEATURES_{idx}"):
                val = f.value
                if isinstance(val, list):
                    val = "; ".join(str(x) for x in val if x)
                if val:
                    row[f"ITEM_FEATURES_{idx}"] = str(val).strip()

    # ── Phase 3: attribute_label_N / attribute_value_N / attribute_uom_N ────
    # Multi-phase extractor Phase 3 emits structured attribute triplet fields.
    # These are written directly to their correct ATTRIBUTE_LABEL/VALUE/UOM slots.
    structured_attr_slots: set[int] = set()
    for f in fields:
        m = _re.match(r"^attribute_label_(\d+)$", f.name)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 50 and not row.get(f"ATTRIBUTE_LABEL {n}"):
                row[f"ATTRIBUTE_LABEL {n}"] = str(f.value).strip() if f.value else ""
                structured_attr_slots.add(n)
        m = _re.match(r"^attribute_value_(\d+)$", f.name)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 50:
                val = f.value
                if isinstance(val, list):
                    val = "; ".join(str(x) for x in val if x)
                if val:
                    row[f"ATTRIBUTE_VALUE {n}"] = str(val).strip()
        m = _re.match(r"^attribute_uom_(\d+)$", f.name)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 50 and f.value:
                row[f"ATTRIBUTE_UOM {n}"] = str(f.value).strip()

    # ── ATTRIBUTE_LABEL/VALUE/UOM slots (up to 50) ───────────────────────
    # All remaining fields NOT already consumed above flow into attribute triplets.
    # Structured phase-3 fields above are skipped via the _SKIP set / slot check.
    _SKIP = {
        'product_name', 'part_desc', 'manufacturer', 'manufacturer_name', 'brand',
        'brand_name', 'trade_name', 'mfg_part_num', 'part_number', 'model_number',
        'alternate_part_number', 'e1_brand', 'unilog_brand', 'dib_brand', 'part_manuf',
        'dept', 'category_class', 'fine_category', 'classpath', 'category_path',
        'short_desc', 'long_desc1', 'long_desc2', 'retail_desc',
        'marketing_description', 'mobile_desc', 'invoice_desc',
        'item_features', 'item_key_selling_points', 'key_selling_points',
        'certifications', 'standards_approvals', 'standard_approvals', 'application',
        'includes', 'with_feature', 'prop_65', 'warranty',
        'mfr_url', 'manufacturer_url', 'ref_urls',
        'ref_url_1', 'ref_url_2', 'ref_url_3', 'ref_url_4', 'ref_url_5',
        'product_image', 'alternate_image_1', 'alternate_image_2',
        'specification_sheet', 'owners_manual', 'owners_user_manual',
        'installation_manual', 'service_manual', 'sds', 'video_link', 'rohs',
        'upc', 'ean', 'gtin', 'unspsc_code', 'unspsc', 'list_price',
        'length', 'length_uom', 'height', 'height_uom',
        'width', 'width_uom', 'weight', 'weight_uom',
        'country_of_origin', 'country_of_manufacture',
        'discontinued', 'actual_image',
        # pipeline internals never shown to users
        'item_keywords', 'long_desc2',
    }
    # Also skip structured item_features_N and attribute_*_N that were already mapped
    for _i in range(1, 21):
        _SKIP.add(f'item_features_{_i}')
    for _i in range(1, 51):
        _SKIP.add(f'attribute_label_{_i}')
        _SKIP.add(f'attribute_value_{_i}')
        _SKIP.add(f'attribute_uom_{_i}')

    # Find first free attribute slot (skip slots already written by Phase 3)
    attr_idx = 1
    while attr_idx <= 50 and row.get(f"ATTRIBUTE_LABEL {attr_idx}"):
        attr_idx += 1

    seen = set()
    for f in fields:
        if attr_idx > 50:
            break
        if f.name in _SKIP or f.name in seen:
            continue
        if f.value is None:
            continue
        val = f.value
        if isinstance(val, list):
            val = "; ".join(str(x) for x in val if x)
        else:
            val = str(val).strip()
        if not val:
            continue
        seen.add(f.name)
        label = (f.display_name or f.name.replace('_', ' ').title()).strip()
        uom   = str(f.unit).strip() if f.unit else ""
        row[f'ATTRIBUTE_LABEL {attr_idx}'] = label
        row[f'ATTRIBUTE_VALUE {attr_idx}'] = val
        row[f'ATTRIBUTE_UOM {attr_idx}']   = uom
        attr_idx += 1

    return row
