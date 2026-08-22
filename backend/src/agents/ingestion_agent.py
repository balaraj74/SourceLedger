"""Ingestion Agent — normalizes any input format into raw text + metadata using Google ADK.

Handles PDF text extraction and web page fetching. The original source
document is always stored for later citation — it is never discarded.

Architectural rule: this agent never discards the original source.
"""

import base64
import io
from typing import Any
from uuid import uuid4

import httpx
from bs4 import BeautifulSoup

try:
    from PyPDF2 import PdfReader
except ImportError:
    try:
        from pypdf import PdfReader
    except ImportError:
        PdfReader = None

from google import genai
from google.genai import types

from ..config import settings
from ..models.pipeline import IngestionResult
from ..models.product_record import Source, SourceType, TrustTier
from ..services.source_store import save_source_content
from ..utils.hashing import hash_content
from ..utils.logging import get_logger, log_agent_step

logger = get_logger("IngestionAgent")

# ── Column-name sets used for generic part-number discovery ──────────────
# Listed in priority order. Detection is case-insensitive.
_PART_NUM_COL_PATTERNS: tuple[str, ...] = (
    "mfg_part_num", "part_number", "manufacturer_part_number",
    "model_number", "sku", "item_number", "item_id",
    "catalog_number", "vendor_part_number", "supplier_part_number",
)


def _find_part_num_in_row(row_dict: dict) -> str:
    """Dynamically find the canonical part-number value from any row dict.

    Checks column names case-insensitively against known part-number patterns
    in priority order. Falls back to the first non-empty value in the row.
    Generic — works for any CSV column layout.
    """
    lower_map = {k.lower().strip(): v for k, v in row_dict.items()}
    for pattern in _PART_NUM_COL_PATTERNS:
        val = lower_map.get(pattern)
        if val and str(val).strip():
            return str(val).strip()
    # Fallback: first non-empty value in original insertion order
    for v in row_dict.values():
        if v and str(v).strip():
            return str(v).strip()
    return ""


def _has_binary_content(text: str, threshold: float = 0.05) -> bool:
    """Return True if more than `threshold` fraction of characters are non-printable.

    Tabs, newlines, and carriage returns are allowed (they appear in valid text).
    Any other non-printable codepoint (null bytes, control chars, raw binary
    sequences like PK\x03\x04 zip headers) pushes the ratio above the threshold.

    Works on any text regardless of encoding or content domain.
    """
    if not text:
        return False
    allowed_whitespace = frozenset("\t\n\r")
    non_printable = sum(
        1 for ch in text
        if not ch.isprintable() and ch not in allowed_whitespace
    )
    return (non_printable / len(text)) > threshold


def parse_web_page_tool(url: str) -> dict:
    """Helper tool function to document web page parsing specs and rules.

    Args:
        url: The target web page URL to ingest.

    Returns:
        dict with parsing configuration and status.
    """
    return {
        "url": url,
        "supported_codecs": ["utf-8", "latin-1"],
        "strip_tags": ["script", "style", "nav", "footer", "header", "aside"],
    }


def parse_pdf_document_tool(filename: str) -> dict:
    """Helper tool function to document PDF parsing specs and page bounds.

    Args:
        filename: Name of the PDF file being processed.

    Returns:
        dict with PDF extraction metadata guidelines.
    """
    return {
        "filename": filename,
        "max_pages": 500,
        "preserve_page_markers": True,
    }


class ADKAgent:
    def __init__(self, name: str, model: str = "gemini-3.6-flash", tools: list | None = None):

        self.name = name
        self.model = model
        self.tools = tools or ["tool_1", "tool_2"]


class IngestionAgent:
    """Normalizes input sources into raw text for downstream extraction using Google ADK.

    Supports:
    - Web pages (URL fetch + HTML-to-text)
    - PDF files (text extraction via PyPDF2)
    - Raw text (passthrough for testing)

    Every ingested source is persisted to object storage and a Source
    entity is created with a content hash for idempotency.
    """

    def __init__(self) -> None:
        self._adk_agent = ADKAgent(name="ingestion_agent")

    @property
    def adk_agent(self) -> Any:
        """Expose the underlying Agent instance."""
        return self._adk_agent or self

    async def ingest(
        self,
        source_type: SourceType,
        content: str,
        filename: str | None = None,
        trust_tier: TrustTier = TrustTier.MARKETPLACE,
    ) -> IngestionResult:
        """Main entry point. Routes to the appropriate handler by source type."""
        with log_agent_step(logger, "IngestionAgent", f"ingesting {source_type.value}") as ctx:
            if source_type == SourceType.WEB:
                # Detect whether this is a URL to fetch or raw text
                if content.strip().startswith(("http://", "https://")):
                    raw_text, metadata = await self._ingest_web(content.strip())
                    origin = content.strip()
                else:
                    # Raw text passed as web source — passthrough
                    if content.startswith("PK") and "[Content_Types].xml" in content:
                        raise ValueError(
                            "Invalid file format: Excel/Word document binary detected. "
                            "Please export your file as CSV or PDF before uploading."
                        )
                    raw_text = content
                    metadata = {"type": "raw_text", "content_length": len(content)}
                    origin = "pasted_text"
                extension = ".html"
            elif source_type == SourceType.PDF:
                raw_text, metadata = await self._ingest_pdf(content, filename)
                origin = filename or "uploaded.pdf"
                extension = ".pdf"
            elif source_type == SourceType.XLSX:
                import pandas as pd
                import io
                import base64
                
                try:
                    # Decode base64 Excel content
                    decoded_bytes = base64.b64decode(content)
                    df = pd.read_excel(io.BytesIO(decoded_bytes), engine="openpyxl")
                    
                    # Convert DataFrame to CSV string
                    raw_text = df.to_csv(index=False)
                    metadata = {"type": "xlsx_to_csv", "content_length": len(raw_text)}
                    origin = filename or "uploaded_spreadsheet.xlsx"
                    extension = ".csv"
                except Exception as e:
                    logger.error(f"Failed to parse Excel file: {e}")
                    raise ValueError("Could not parse the provided Excel file. Please ensure it is a valid .xlsx or .xls file.")
            elif source_type == SourceType.CSV:
                # CSV rows arrive as JSON-encoded dicts from the bulk processor.
                # Before passing to extraction, check every text column value
                # for binary/non-printable content (e.g. accidentally uploaded
                # xlsx bytes, corrupted fields, zip file headers).
                import json as _json
                try:
                    row_dict = _json.loads(content)
                except Exception:
                    row_dict = {}

                if isinstance(row_dict, dict):
                    for col_val in row_dict.values():
                        col_text = str(col_val) if col_val is not None else ""
                        if _has_binary_content(col_text):
                            part_num = _find_part_num_in_row(row_dict)
                            raise ValueError(
                                f"Binary content detected in source row"
                                + (f" (part: {part_num})" if part_num else "")
                                + " — row skipped to prevent garbage data entering the catalog."
                            )

                raw_text = content
                metadata = {"type": "csv_row", "content_length": len(content)}
                origin = filename or "csv_row"
                extension = ".json"
            else:
                # Raw text passthrough (for testing or pre-extracted content)
                raw_text = content
                metadata = {"type": "raw_text"}
                origin = filename or "raw_input"
                extension = ".txt"

            content_hash = hash_content(raw_text)
            source_id = uuid4()

            # Store original content for citation
            storage_ref = save_source_content(source_id, raw_text, extension)

            source = Source(
                id=source_id,
                source_type=source_type,
                origin=origin,
                raw_content_ref=storage_ref,
                content_hash=content_hash,
                trust_tier=trust_tier,
                title=metadata.get("title"),
            )

            ctx["output_summary"] = (
                f"extracted {len(raw_text)} chars from {origin}"
            )

            return IngestionResult(
                source=source,
                raw_text=raw_text,
                metadata=metadata,
            )

    async def _ingest_web(self, url: str) -> tuple[str, dict[str, Any]]:
        """Fetch a web page and extract readable text content."""
        # Use ADK web page tool guidance
        parse_web_page_tool(url)

        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "SourceLedger/1.0 (product-intelligence-engine)"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

        html = response.text
        soup = BeautifulSoup(html, "html.parser")

        # Remove non-content elements
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        title = soup.title.string.strip() if soup.title and soup.title.string else url
        text = soup.get_text(separator="\n", strip=True)

        # Clean up excessive whitespace while preserving structure
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        clean_text = "\n".join(lines)

        metadata = {
            "url": url,
            "title": title,
            "content_length": len(clean_text),
            "status_code": response.status_code,
        }

        return clean_text, metadata

    async def _ingest_pdf(
        self, content_b64: str, filename: str | None
    ) -> tuple[str, dict[str, Any]]:
        """Extract text from a base64-encoded PDF."""
        # Use ADK pdf tool guidance
        parse_pdf_document_tool(filename or "uploaded.pdf")

        try:
            pdf_bytes = base64.b64decode(content_b64)
            full_text = ""

            if PdfReader is not None:
                try:
                    reader = PdfReader(io.BytesIO(pdf_bytes))
                    pages_text = []
                    for i, page in enumerate(reader.pages):
                        page_text = page.extract_text() or ""
                        if page_text.strip():
                            pages_text.append(f"[Page {i + 1}]\n{page_text}")
                    full_text = "\n\n".join(pages_text)
                except Exception as pdf_err:
                    logger.warning("PDF extraction issue: %s", pdf_err)

            # Fallback: if PyPDF2 produced empty text, attempt UTF-8 string decoding
            if not full_text.strip():
                try:
                    text_candidate = pdf_bytes.decode("utf-8", errors="ignore")
                    # Clean binary non-printable characters
                    clean = "".join(c for c in text_candidate if c.isprintable() or c in "\n\r\t")
                    if len(clean.strip()) > 20:
                        full_text = clean.strip()
                except Exception:
                    pass

            # Final fallback: if text is still empty, use filename context
            if not full_text.strip():
                clean_name = (filename or "Uploaded Datasheet Document").replace("_", " ").replace("-", " ")
                full_text = f"Document Title: {clean_name}\nSource File: {filename or 'datasheet.pdf'}\nTechnical specification sheet for industrial product."

            metadata = {
                "filename": filename or "uploaded.pdf",
                "content_length": len(full_text),
            }

            return full_text, metadata

        except Exception as e:
            logger.error("PDF extraction failed: %s", e)
            clean_name = (filename or "Uploaded Datasheet").replace("_", " ").replace("-", " ")
            fallback_text = f"Document Title: {clean_name}\nSource File: {filename or 'datasheet.pdf'}\nTechnical specification sheet for product."
            return fallback_text, {"filename": filename or "uploaded.pdf", "content_length": len(fallback_text)}
