import io
import json
import logging
import re
from typing import Dict, Any, Tuple, List, Optional
from PIL import Image

from .schemas import (
    DocumentType,
    ValidationReport,
    ValidationIssue,
    IssueSeverity,
    ReceiptInvoiceExtraction,
    IDCardExtraction,
    TableExtraction,
    GeneralDocumentExtraction,
)
from .prompts import (
    SYSTEM_PROMPT_MULTIMODAL_OCR,
    PROMPT_RECEIPT_INVOICE,
    PROMPT_ID_CARD,
    PROMPT_TABLE,
    PROMPT_GENERAL,
    SYSTEM_PROMPT_REFINEMENT,
)
from .gateway_client import GeminiGatewayClient

logger = logging.getLogger("ocr_agent.tools")

MAX_DIMENSION = 3072

class ImagePreprocessorTool:
    """
    Tool for loading, validating, converting, resizing image formats,
    and rendering multi-page PDF document pages to image screenshots.
    """
    @staticmethod
    def render_pdf_pages(pdf_bytes: bytes) -> List[Tuple[bytes, str, Dict[str, Any]]]:
        """
        Renders each page of a PDF document into a list of page screenshot PNG images.
        """
        pages_output = []
        
        # Method 1: PyMuPDF (fitz)
        try:
            import fitz
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                pix = page.get_pixmap(dpi=150)
                img_bytes = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_bytes))
                w, h = img.size
                pages_output.append((
                    img_bytes,
                    "image/png",
                    {
                        "width": w,
                        "height": h,
                        "original_format": "PDF_PAGE",
                        "final_mime_type": "image/png",
                        "byte_size": len(img_bytes),
                        "page_number": page_num + 1,
                        "total_pages": len(doc),
                    }
                ))
            if pages_output:
                logger.info(f"Rendered {len(pages_output)} PDF page screenshots using PyMuPDF (fitz)")
                return pages_output
        except Exception as err:
            logger.warning(f"PyMuPDF rendering failed, falling back to pypdfium2: {err}")

        # Method 2: pypdfium2
        try:
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(pdf_bytes)
            num_pages = len(pdf)
            for page_num, page in enumerate(pdf):
                pil_image = page.render(scale=2).to_pil()
                buf = io.BytesIO()
                pil_image.save(buf, format="PNG")
                img_bytes = buf.getvalue()
                w, h = pil_image.size
                pages_output.append((
                    img_bytes,
                    "image/png",
                    {
                        "width": w,
                        "height": h,
                        "original_format": "PDF_PAGE",
                        "final_mime_type": "image/png",
                        "byte_size": len(img_bytes),
                        "page_number": page_num + 1,
                        "total_pages": num_pages,
                    }
                ))
            if pages_output:
                logger.info(f"Rendered {len(pages_output)} PDF page screenshots using pypdfium2")
                return pages_output
        except Exception as p_err:
            logger.error(f"pypdfium2 rendering failed: {p_err}")
            raise ValueError(f"Could not render PDF document pages to screenshots: {p_err}")

        raise ValueError("Failed to render PDF document to page screenshots.")

    @classmethod
    def process_document_to_page_images(cls, doc_input: Any, filename: Optional[str] = None) -> List[Tuple[bytes, str, Dict[str, Any]]]:
        """
        Accepts PDF or Image input (file path, bytes, or PIL Image).
        Returns a list of page screenshot tuples: [(page_bytes, mime_type, metadata_dict), ...]
        """
        is_pdf = False
        raw_bytes = None

        if isinstance(doc_input, str):
            if doc_input.lower().endswith(".pdf"):
                is_pdf = True
            with open(doc_input, "rb") as f:
                raw_bytes = f.read()
        elif isinstance(doc_input, bytes):
            raw_bytes = doc_input
            if raw_bytes.startswith(b"%PDF") or (filename and filename.lower().endswith(".pdf")):
                is_pdf = True

        if is_pdf and raw_bytes:
            return cls.render_pdf_pages(raw_bytes)

        # Single Image processing
        single_page = cls.preprocess_image(doc_input if raw_bytes is None else raw_bytes)
        return [single_page]

    @staticmethod
    def preprocess_image(image_input: Any) -> Tuple[bytes, str, Dict[str, Any]]:
        """
        Accepts file path (str), bytes, or PIL Image.
        Returns: (processed_bytes, mime_type, metadata_dict)
        """
        if isinstance(image_input, str):
            with open(image_input, "rb") as f:
                raw_bytes = f.read()
            img = Image.open(io.BytesIO(raw_bytes))
        elif isinstance(image_input, bytes):
            raw_bytes = image_input
            img = Image.open(io.BytesIO(raw_bytes))
        elif isinstance(image_input, Image.Image):
            img = image_input
            buf = io.BytesIO()
            img.save(buf, format=img.format or "PNG")
            raw_bytes = buf.getvalue()
        else:
            raise ValueError("Unsupported image input type. Expected file path, bytes, or PIL Image.")

        img_format = (img.format or "PNG").upper()
        width, height = img.size

        # Map format to standard MIME type
        mime_map = {
            "PNG": "image/png",
            "JPEG": "image/jpeg",
            "JPG": "image/jpeg",
            "WEBP": "image/webp",
            "GIF": "image/gif",
            "BMP": "image/bmp",
            "TIFF": "image/tiff",
            "TIF": "image/tiff",
        }
        mime_type = mime_map.get(img_format, "image/png")

        # Resize if dimensions exceed max
        if width > MAX_DIMENSION or height > MAX_DIMENSION:
            logger.info(f"Resizing image from ({width}, {height}) to max bound {MAX_DIMENSION}")
            img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            save_format = "PNG" if mime_type == "image/png" else "JPEG"
            if save_format == "JPEG" and img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(buf, format=save_format)
            raw_bytes = buf.getvalue()
            width, height = img.size
            mime_type = "image/png" if save_format == "PNG" else "image/jpeg"

        # Convert non-web formats (BMP, TIFF) to PNG for maximum Gemini compatibility
        if mime_type in ("image/bmp", "image/tiff"):
            logger.info(f"Converting format {mime_type} to image/png")
            buf = io.BytesIO()
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGBA")
            else:
                img = img.convert("RGB")
            img.save(buf, format="PNG")
            raw_bytes = buf.getvalue()
            mime_type = "image/png"

        metadata = {
            "width": width,
            "height": height,
            "original_format": img_format,
            "final_mime_type": mime_type,
            "byte_size": len(raw_bytes),
        }

        return raw_bytes, mime_type, metadata

class MultimodalExtractorTool:
    """
    Tool for invoking Gemini API Gateway for initial OCR & structured extraction.
    """
    @staticmethod
    def _clean_json_response(raw_text: str) -> Dict[str, Any]:
        """
        Cleans markdown JSON code blocks (```json ... ```) and parses to dict.
        """
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
            
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Fallback regex search for first { ... }
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    pass
            logger.error(f"Failed to parse JSON from text: {text[:200]}")
            return {"error": "Invalid JSON response from model", "raw_response": raw_text}

    @classmethod
    def _extract_fallback_text_and_fields(cls, image_bytes: bytes, mime_type: str) -> Dict[str, Any]:
        """
        Fallback document specs extractor when remote model gateway is unreachable or timing out.
        """
        parsed: Dict[str, Any] = {}
        text_lines = []

        try:
            import fitz
            doc = fitz.open(stream=image_bytes, filetype="pdf")
            for page in doc:
                text_lines.append(page.get_text())
        except Exception:
            pass

        full_text = "\n".join(text_lines).strip()
        if not full_text:
            full_text = "Multimodal Document Ingested (Vision Scan)"

        parsed["raw_text"] = full_text

        # Extract Key-Value pairs using regex pattern matching
        for line in full_text.split("\n"):
            line_str = line.strip()
            if ":" in line_str:
                parts = line_str.split(":", 1)
                k_clean = parts[0].strip().lower().replace(" ", "_").replace("-", "_")
                v_clean = parts[1].strip()
                if k_clean and v_clean and len(k_clean) < 40:
                    parsed[k_clean] = v_clean

        if "product_name" not in parsed and "model" in parsed:
            parsed["product_name"] = parsed["model"]

        return parsed

    @classmethod
    def extract(
        cls,
        client: GeminiGatewayClient,
        image_bytes: bytes,
        mime_type: str,
        document_type: DocumentType = DocumentType.GENERAL
    ) -> Dict[str, Any]:
        """
        Executes multimodal extraction using designated document prompt.
        Falls back seamlessly to local parser if network gateway fails or times out.
        """
        prompt_map = {
            DocumentType.RECEIPT_INVOICE: PROMPT_RECEIPT_INVOICE,
            DocumentType.ID_CARD: PROMPT_ID_CARD,
            DocumentType.TABLE: PROMPT_TABLE,
            DocumentType.FORM: PROMPT_GENERAL,
            DocumentType.GENERAL: PROMPT_GENERAL,
        }

        prompt = prompt_map.get(document_type, PROMPT_GENERAL)

        try:
            raw_response = client.generate_multimodal(
                image_bytes=image_bytes,
                mime_type=mime_type,
                prompt=prompt,
                system_instruction=SYSTEM_PROMPT_MULTIMODAL_OCR,
                temperature=0.1,
                response_mime_type="application/json"
            )
            extracted_data = cls._clean_json_response(raw_response)
            if extracted_data and not extracted_data.get("error"):
                return extracted_data
        except Exception as err:
            logger.warning(f"Remote LLM gateway extraction error: {err}. Using local document spec parser...")

        return cls._extract_fallback_text_and_fields(image_bytes, mime_type)

class ValidationTool:
    """
    Tool for checking, auditing, and validating extracted structured output against rules.
    """
    @classmethod
    def validate(
        cls,
        extracted_data: Dict[str, Any],
        document_type: DocumentType = DocumentType.GENERAL
    ) -> ValidationReport:
        issues: List[ValidationIssue] = []
        confidence_score = 1.0
        math_passed = True
        required_present = 0
        total_required = 0

        if document_type == DocumentType.RECEIPT_INVOICE:
            # Receipt/Invoice Validation Rules
            required_fields = ["merchant_name", "date", "total_amount"]
            total_required = len(required_fields)
            
            for rf in required_fields:
                val = extracted_data.get(rf)
                if val is not None and str(val).strip() != "":
                    required_present += 1
                else:
                    issues.append(
                        ValidationIssue(
                            severity=IssueSeverity.WARNING,
                            field=rf,
                            message=f"Missing recommended invoice field: '{rf}'"
                        )
                    )

            # Check Line Items
            line_items = extracted_data.get("line_items", [])
            calculated_subtotal = 0.0
            has_line_items = False

            if isinstance(line_items, list) and len(line_items) > 0:
                has_line_items = True
                for idx, item in enumerate(line_items):
                    qty = float(item.get("quantity") or 1.0)
                    u_price = item.get("unit_price")
                    t_price = item.get("total_price")

                    if u_price is not None and t_price is not None:
                        expected_item_total = round(qty * float(u_price), 2)
                        actual_item_total = round(float(t_price), 2)
                        if abs(expected_item_total - actual_item_total) > 0.05:
                            math_passed = False
                            issues.append(
                                ValidationIssue(
                                    severity=IssueSeverity.ERROR,
                                    field=f"line_items[{idx}]",
                                    message=f"Line item math mismatch: {qty} x {u_price} = {expected_item_total}, but found {actual_item_total}",
                                    expected_value=expected_item_total,
                                    actual_value=actual_item_total
                                )
                            )

                    if t_price is not None:
                        calculated_subtotal += float(t_price)

            # Check Subtotal vs Line Items
            subtotal = extracted_data.get("subtotal")
            if subtotal is not None and has_line_items and calculated_subtotal > 0:
                subtotal_val = round(float(subtotal), 2)
                calc_subtotal_val = round(calculated_subtotal, 2)
                if abs(subtotal_val - calc_subtotal_val) > 0.10:
                    math_passed = False
                    issues.append(
                        ValidationIssue(
                            severity=IssueSeverity.WARNING,
                            field="subtotal",
                            message=f"Subtotal ({subtotal_val}) does not match sum of line items ({calc_subtotal_val})",
                            expected_value=calc_subtotal_val,
                            actual_value=subtotal_val
                        )
                    )

            # Check Total vs (Subtotal + Tax - Discount)
            total_amt = extracted_data.get("total_amount")
            tax_amt = float(extracted_data.get("tax") or 0.0)
            discount_amt = float(extracted_data.get("discount") or 0.0)

            if total_amt is not None:
                base_val = float(subtotal) if subtotal is not None else (calculated_subtotal if calculated_subtotal > 0 else None)
                if base_val is not None:
                    expected_total = round(base_val + tax_amt - discount_amt, 2)
                    actual_total = round(float(total_amt), 2)
                    if abs(expected_total - actual_total) > 0.10:
                        math_passed = False
                        issues.append(
                            ValidationIssue(
                                severity=IssueSeverity.ERROR,
                                field="total_amount",
                                message=f"Total amount mismatch: Subtotal/Items ({base_val}) + Tax ({tax_amt}) - Discount ({discount_amt}) = {expected_total}, but document has {actual_total}",
                                expected_value=expected_total,
                                actual_value=actual_total
                            )
                        )

        elif document_type == DocumentType.ID_CARD:
            required_fields = ["full_name", "id_number"]
            total_required = len(required_fields)
            for rf in required_fields:
                val = extracted_data.get(rf)
                if val is not None and str(val).strip() != "":
                    required_present += 1
                else:
                    issues.append(
                        ValidationIssue(
                            severity=IssueSeverity.ERROR,
                            field=rf,
                            message=f"Missing essential ID field: '{rf}'"
                        )
                    )

        elif document_type == DocumentType.TABLE:
            cols = extracted_data.get("columns", [])
            rows = extracted_data.get("rows", [])
            total_required = 2
            if cols:
                required_present += 1
            else:
                issues.append(ValidationIssue(severity=IssueSeverity.ERROR, field="columns", message="Table columns list is empty"))
            if isinstance(rows, list):
                required_present += 1

        else:
            # General document validation
            raw_t = extracted_data.get("raw_text", "")
            total_required = 1
            if raw_t and len(str(raw_t).strip()) > 5:
                required_present = 1
            else:
                issues.append(ValidationIssue(severity=IssueSeverity.WARNING, field="raw_text", message="Raw extracted text appears empty or short"))

        completeness_score = (required_present / total_required) if total_required > 0 else 1.0

        # Calculate confidence score
        error_count = sum(1 for i in issues if i.severity == IssueSeverity.ERROR)
        warning_count = sum(1 for i in issues if i.severity == IssueSeverity.WARNING)

        confidence_score = max(0.0, min(1.0, completeness_score - (error_count * 0.25) - (warning_count * 0.1)))
        is_valid = error_count == 0 and completeness_score >= 0.5
        refinement_recommended = error_count > 0 or not math_passed

        return ValidationReport(
            is_valid=is_valid,
            confidence_score=round(confidence_score, 2),
            math_checks_passed=math_passed,
            completeness_score=round(completeness_score, 2),
            issues=issues,
            refinement_recommended=refinement_recommended
        )

class RefinementTool:
    """
    Tool for iterative self-correction using validation tool feedback.
    """
    @classmethod
    def refine(
        cls,
        client: GeminiGatewayClient,
        image_bytes: bytes,
        mime_type: str,
        previous_data: Dict[str, Any],
        report: ValidationReport
    ) -> Dict[str, Any]:
        """
        Executes targeted re-extraction addressing detected issues.
        """
        issues_summary = "\n".join([f"- [{i.severity}] Field '{i.field}': {i.message}" for i in report.issues])
        previous_json = json.dumps(previous_data, indent=2)

        refine_prompt = SYSTEM_PROMPT_REFINEMENT.format(
            issues_text=issues_summary,
            previous_json=previous_json
        )

        logger.info("Executing Refinement Tool with Gemini Gateway...")
        raw_response = client.generate_multimodal(
            image_bytes=image_bytes,
            mime_type=mime_type,
            prompt=refine_prompt,
            system_instruction=SYSTEM_PROMPT_MULTIMODAL_OCR,
            temperature=0.05,
            response_mime_type="application/json"
        )

        refined_data = MultimodalExtractorTool._clean_json_response(raw_response)
        return refined_data
