"""Regression tests for source-backed delivery CSV processing."""

import asyncio
import csv
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from src.models.product_record import FieldStatus, ProductField, SourceExcerpt
from src.services.csv_processor import CSVProcessor, EXPECTED_DELIVERY_HEADERS


class FakePipeline:
    async def run(self, **kwargs):
        row = json.loads(kwargs["content"])
        source = SourceExcerpt(source_id=uuid4(), text="CSV source")
        fields = [
            ProductField(name="mfg_part_num", display_name="Mfg part", value=row["Manufacturer Part Number"], confidence=95, source_excerpt=source, reasoning="source", status=FieldStatus.AUTO_COMMITTED),
            ProductField(name="sku", display_name="SKU", value=row["SKU"], confidence=95, source_excerpt=source, reasoning="source", status=FieldStatus.AUTO_COMMITTED),
            ProductField(name="part_desc", display_name="Description", value=row["Description"], confidence=95, source_excerpt=source, reasoning="source", status=FieldStatus.AUTO_COMMITTED),
        ]
        return SimpleNamespace(id=uuid4(), name=row["Description"], category="generic", confidence_overall=95, fields=fields)


def test_csv_processor_preserves_source_identity_and_manifest(tmp_path):
    async def run():
        sample_csv = tmp_path / "input.csv"
        output_dir = tmp_path / "output"
        sample_csv.write_text("Manufacturer Part Number,SKU,Description\nMPN-1,SKU-1,Example widget\n", encoding="utf-8")
        summary = await CSVProcessor(FakePipeline()).process_file(sample_csv, output_dir)

        with Path(summary["output_csv"]).open(encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            row = next(reader)
            assert len(reader.fieldnames or []) == len(EXPECTED_DELIVERY_HEADERS)
        manifest = json.loads(Path(summary["output_manifest"]).read_text(encoding="utf-8"))

        assert row["Mfg_Part_Num"] == "MPN-1"
        assert row["MANUFACTURER_PART_NUMBER"] == "MPN-1"
        assert row["SKU - MY_PART_NUMBER"] == "SKU-1"
        assert row["PART_NUMBER"].startswith("SL-")
        assert row["PART_NUMBER"] not in {row["Mfg_Part_Num"], row["SKU - MY_PART_NUMBER"]}
        assert row["UPC"] == "" and row["List Price"] == ""
        assert manifest["rows"][0]["status"] == "needs_review"

    asyncio.run(run())


def test_delivery_sanity_flags_repeated_values_and_identifier_collapse():
    rows = [
        {"Mfg_Part_Num": f"MPN-{index}", "PART_NUMBER": f"MPN-{index}", "SKU - MY_PART_NUMBER": f"MPN-{index}", "UPC": "010000000000", "List Price": "24.99", "Product Name": f"Product {index}", "Classpath": "General"}
        for index in range(6)
    ]
    manifest = [{"row_number": index, "status": "enriched"} for index in range(1, 7)]
    issues = CSVProcessor._delivery_sanity_issues({row["Mfg_Part_Num"] for row in rows}, rows, manifest)

    assert any(issue.startswith("repeated UPC") for issue in issues)
    assert any(issue.startswith("repeated List Price") for issue in issues)
    assert "identifier collapse in 6 rows" in issues
    assert "classification diversity requires review" in issues
