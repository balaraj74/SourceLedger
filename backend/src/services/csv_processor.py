"""CSV Processing Service — maps input datasets into exact delivery format specifications.

Reads product catalog records from input CSV files, executes the 5-stage Google ADK agent pipeline,
and outputs enriched structured data matching the exact 252-column delivery schema seen in
'Unihack_ Expected Output - Delivery Format.csv'.
"""

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..agents.main import AgentPipeline, key_rotator
from ..models.product_record import SourceType, TrustTier
from ..models.unihack_schema import map_product_fields_to_unihack_row
from ..utils.logging import get_logger

logger = get_logger("CSVProcessor")


# Standard 252 delivery headers from Unihack_ Expected Output - Delivery Format.csv
EXPECTED_DELIVERY_HEADERS = [
    "MFR URL", "Ref URL 1", "Ref URL 2", "Ref URL 3", "Ref URL 4", "Ref URL 5",
    "PART_NUMBER", "Dept", "Class", "Fine", "SKU - MY_PART_NUMBER", "Mfg_Part_Num",
    "Part_Desc", "E1_Brand", "Unilog_Brand", "DIB_Brand", "Part_Manuf",
    "MANUFACTURER_NAME", "BRAND_NAME", "TRADE_NAME", "MANUFACTURER_PART_NUMBER",
    "ALTERNATE_PART_NUMBER", "Classpath", "MOBILE_DESC", "INVOICE_DESC",
    "SHORT_DESC", "LONG_DESC1", "RETAIL_DESC", "MARKETING_DESCRIPTION",
    "ITEM_FEATURES_1", "ITEM_FEATURES_2", "ITEM_FEATURES_3", "ITEM_FEATURES_4",
    "ITEM_FEATURES_5", "ITEM_FEATURES_6", "ITEM_FEATURES_7", "ITEM_FEATURES_8",
    "ITEM_FEATURES_9", "ITEM_FEATURES_10", "ITEM_FEATURES_11", "ITEM_FEATURES_12",
    "ITEM_FEATURES_13", "ITEM_FEATURES_14", "ITEM_FEATURES_15", "ITEM_FEATURES_16",
    "ITEM_FEATURES_17", "ITEM_FEATURES_18", "ITEM_FEATURES_19", "ITEM_FEATURES_20",
    "With", "Standard/Approvals", "Prop 65", "Application", "Includes", "Product Name"
]

# Add ATTRIBUTE_LABEL 1..50, ATTRIBUTE_VALUE 1..50, ATTRIBUTE_UOM 1..50
for i in range(1, 51):
    EXPECTED_DELIVERY_HEADERS.extend([
        f"ATTRIBUTE_LABEL {i}",
        f"ATTRIBUTE_VALUE {i}",
        f"ATTRIBUTE_UOM {i}"
    ])

EXPECTED_DELIVERY_HEADERS.extend([
    "UPC", "EAN", "GTIN", "UNSPSC", "Warranty", "List Price", "Selling Qty",
    "Selling UOM", "Standard Packaging Information", "LENGTH", "LENGTH_UOM",
    "HEIGHT", "HEIGHT_UOM", "WIDTH", "WIDTH_UOM", "WEIGHT", "WEIGHT_UOM",
    "VOLUME", "VOLUME_UOM", "Product Image", "Alternate Image 1",
    "Alternate Image 2", "Alternate Image 3", "Alternate Image 4", "SDS",
    "SDS_1", "Warranty Information", "Catalog", "Specification Sheet",
    "Instruction/Installation Manual", "Service Manual", "Owners/User Manual",
    "Line Drawing", "MTR", "RoHS", "Full Engineering Drawing", "Energy Star Guide",
    "Technical Bulletin", "Submittal", "Compatibility Chart", "Size Chart",
    "Product Label/Insert", "Video Link", "Video Link 1", "Country Of Origin",
    "Discontinued", "Actual Image (Yes/No)"
])


class CSVProcessor:
    """Processes product catalog CSV inputs into the exact Expected Delivery Format."""

    def __init__(self, pipeline: Optional[AgentPipeline] = None) -> None:
        self.pipeline = pipeline or AgentPipeline()


    @staticmethod
    def _normalise_column(name: str) -> str:
        return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", str(name).lower())).strip("_")


    @classmethod
    def _source_value(cls, row: dict[str, Any], aliases: tuple[str, ...]) -> str:
        values = {cls._normalise_column(key): value for key, value in row.items() if key}
        for alias in aliases:
            value = values.get(alias)
            if value is not None and str(value).strip():
                return str(value).strip()
        for key, value in values.items():
            if value is not None and str(value).strip() and any(alias in key for alias in aliases):
                return str(value).strip()
        return ""


    @staticmethod
    def _delivery_sanity_issues(input_ids: set[str], rows: list[dict[str, str]], manifest: list[dict[str, Any]]) -> list[str]:
        """Report suspect delivery data without replacing source-backed values."""
        from collections import Counter

        issues: list[str] = []
        output_ids = {row.get("Mfg_Part_Num", "").strip() for row in rows if row.get("Mfg_Part_Num", "").strip()}
        unexpected = output_ids - input_ids
        if unexpected:
            issues.append("out-of-scope manufacturer part numbers")
        if len(rows) != len(manifest):
            issues.append("coverage mismatch between rows and manifest")

        for column in ("UPC", "EAN", "GTIN", "List Price"):
            values = [row.get(column, "").strip() for row in rows if row.get(column, "").strip()]
            if values:
                value, count = Counter(values).most_common(1)[0]
                if count > 1 and count / len(rows) > 0.05:
                    issues.append(f"repeated {column} value {value!r} in {count}/{len(rows)} rows")

        collapsed = [
            row for row in rows
            if row.get("PART_NUMBER", "").strip()
            and row.get("PART_NUMBER", "").strip() == row.get("Mfg_Part_Num", "").strip() == row.get("SKU - MY_PART_NUMBER", "").strip()
        ]
        if collapsed:
            issues.append(f"identifier collapse in {len(collapsed)} rows")

        product_names = {row.get("Product Name", "").strip() or row.get("Part_Desc", "").strip() for row in rows}
        classpaths = {row.get("Classpath", "").strip() for row in rows if row.get("Classpath", "").strip()}
        if len(rows) >= 6 and len(product_names - {""}) > 1 and len(classpaths) == 1:
            issues.append("classification diversity requires review")
        return issues

    def get_delivery_headers(self, sample_delivery_file: Optional[Path] = None) -> list[str]:
        """Load delivery column headers from sample expected file if present."""
        if sample_delivery_file and sample_delivery_file.exists():
            try:
                with open(sample_delivery_file, mode="r", encoding="utf-8-sig") as f:
                    reader = csv.reader(f)
                    return next(reader)
            except Exception as e:
                logger.warning("Could not read delivery template header: %s", e)
        return EXPECTED_DELIVERY_HEADERS

    async def process_file(
        self,
        input_csv_path: str | Path,
        output_dir: str | Path = "output",
        max_rows: Optional[int] = None,
        template_csv_path: Optional[str | Path] = None,
    ) -> dict[str, Any]:
        """Process input CSV and export results in the exact Expected Delivery Format.

        Args:
            input_csv_path: Path to input CSV file.
            output_dir: Output folder directory.
            max_rows: Limit rows processed (for testing/batching).
            template_csv_path: Optional reference expected delivery template file.

        Returns:
            dict containing summary execution metrics and file output paths.
        """
        input_path = Path(input_csv_path)
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        if not input_path.exists():
            raise FileNotFoundError(f"Input CSV file not found: {input_path}")

        template_path = Path(template_csv_path) if template_csv_path else out_dir / "Unihack_ Expected Output - Delivery Format.csv"
        headers = self.get_delivery_headers(template_path if template_path.exists() else None)

        logger.info("Starting delivery-formatted CSV processing for file: %s", input_path)

        delivery_rows = []
        json_records = []
        manifest: list[dict[str, Any]] = []

        with open(input_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        if max_rows is not None:
            rows = rows[:max_rows]

        total_rows = len(rows)
        logger.info("Processing %d records into delivery format", total_rows)

        manufacturer_identifier_columns = ("mfg_part_num", "manufacturer_part_number", "mpn", "model_number", "part_number", "part_num", "catalog_number", "vendor_part_number")
        sku_columns = ("sku_my_part_number", "sku", "item_number", "item_id")
        identifier_columns = manufacturer_identifier_columns + sku_columns
        description_columns = ("part_desc", "product_description", "product_name", "description", "item_description", "long_description", "short_description", "item_name", "name", "title")
        input_ids = {self._source_value(source_row, identifier_columns) for source_row in rows if self._source_value(source_row, identifier_columns)}

        for idx, row in enumerate(rows, start=1):
            mfg_part_num = self._source_value(row, manufacturer_identifier_columns)
            source_sku = self._source_value(row, sku_columns)
            input_identifier = mfg_part_num or source_sku
            part_desc = self._source_value(row, description_columns)
            part_manuf = self._source_value(row, ("part_manuf",))
            e1_brand = self._source_value(row, ("e1_brand",))
            unilog_brand = self._source_value(row, ("unilog_brand",))
            dib_brand = self._source_value(row, ("dib_brand",))
            raw_text = json.dumps(row, ensure_ascii=False)

            try:
                product = await self.pipeline.run(
                    source_type=SourceType.CSV,
                    content=raw_text,
                    category="generic",
                    filename=input_path.name,
                    trust_tier=TrustTier.DISTRIBUTOR,
                )

                # Map every agent-produced field through the canonical delivery
                # formatter so live URLs/specs do not get discarded.
                mapped_row = map_product_fields_to_unihack_row(
                    product.fields,
                    title=product.name,
                    sku="",
                ) or {}
                d_row = {header: mapped_row.get(header, "") for header in headers}


                # Preserve only explicit source values. PART_NUMBER remains the distinct internal ID, and SKU is never copied from an MPN.
                for header, value in {
                    "Mfg_Part_Num": mfg_part_num,
                    "MANUFACTURER_PART_NUMBER": mfg_part_num,
                    "SKU - MY_PART_NUMBER": source_sku,
                    "Part_Desc": part_desc,
                    "E1_Brand": e1_brand,
                    "Unilog_Brand": unilog_brand,
                    "DIB_Brand": dib_brand,
                    "Part_Manuf": part_manuf,
                }.items():
                    if value:
                        d_row[header] = value

                d_row["Product Name"] = product.name or part_desc
                delivery_rows.append(d_row)
                review_reasons = []
                if not input_identifier:
                    review_reasons.append("no recognizable source identifier")
                if not d_row.get("Classpath"):
                    review_reasons.append("classification not source-verified")
                manifest.append({"row_number": idx, "input_identifier": input_identifier,
                                 "status": "enriched" if not review_reasons else "needs_review",
                                 "reasons": review_reasons, "product_id": str(product.id)})

                json_records.append({
                    "row_number": idx,
                    "status": manifest[-1]["status"],
                    "mfg_part_num": mfg_part_num,
                    "input_identifier": input_identifier,
                    "product_id": str(product.id),
                    "product_name": product.name,
                    "category": product.category,
                    "confidence_overall": product.confidence_overall,
                    "fields": [
                        {
                            "id": str(f.id),
                            "name": f.name,
                            "display_name": f.display_name,
                            "value": f.value,
                            "unit": f.unit,
                            "confidence": f.confidence,
                            "reasoning": f.reasoning,
                            "status": f.status.value if hasattr(f.status, "value") else str(f.status),
                        }
                        for f in product.fields
                    ],
                })

            except Exception as e:
                logger.error("Error processing row %d (%s): %s", idx, mfg_part_num, e)
                d_row = {h: "" for h in headers}
                d_row["Mfg_Part_Num"] = mfg_part_num
                d_row["Part_Desc"] = part_desc
                # Failed rows intentionally contain no synthetic product description.
                delivery_rows.append(d_row)
                manifest.append({"row_number": idx, "input_identifier": input_identifier,
                                 "status": "skipped_unprocessable", "reasons": [str(e)], "product_id": None})

        sanity_issues = self._delivery_sanity_issues(input_ids, delivery_rows, manifest)
        scope_issues = [issue for issue in sanity_issues if issue.startswith("out-of-scope") or issue.startswith("coverage mismatch")]
        if scope_issues:
            raise RuntimeError("Delivery validation failed: " + "; ".join(scope_issues))

        # Write Output Delivery CSV
        output_csv_file = out_dir / "Unihack_ Output - Delivery Format.csv"
        with open(output_csv_file, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(delivery_rows)

        # Write Output JSON
        output_json_file = out_dir / "Unihack_ Output - Delivery Format.json"
        with open(output_json_file, mode="w", encoding="utf-8") as f:
            json.dump(
                {
                    "processed_count": len(delivery_rows),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "records": json_records,
                    "manifest": manifest,
                    "sanity_issues": sanity_issues,
                },
                f,
                indent=2,
            )

        manifest_file = out_dir / "Unihack_ Output - Delivery Manifest.json"
        with open(manifest_file, mode="w", encoding="utf-8") as f:
            json.dump({"input_file": input_path.name, "rows": manifest, "sanity_issues": sanity_issues}, f, indent=2)

        logger.info("Successfully wrote delivery format to %s and %s", output_csv_file, output_json_file)

        return {
            "total_processed": len(delivery_rows),
            "output_csv": str(output_csv_file),
            "output_json": str(output_json_file),
            "output_manifest": str(manifest_file),
            "sanity_issues": sanity_issues,
        }

    def _detect_category_from_row(self, raw_text: str) -> str:
        text_lower = raw_text.lower()
        if any(kw in text_lower for kw in ["connector", "contact", "pin", "plug", "socket", "terminal block"]):
            return "electrical_connector"
        elif any(kw in text_lower for kw in ["bolt", "nut", "screw", "fastener", "washer", "thread"]):
            return "safety_fastener"
        elif any(kw in text_lower for kw in ["centrifugal pump", "flow rate", "head pressure", "impeller"]):
            return "industrial_pump"
        else:
            return "generic"
