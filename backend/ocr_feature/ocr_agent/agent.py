import logging
from typing import Any, Dict, List, Optional, Tuple

from .schemas import (
    DocumentType,
    ExtractionResult,
    ValidationReport,
    AgentStep,
)
from .gateway_client import GeminiGatewayClient
from .tools import (
    ImagePreprocessorTool,
    MultimodalExtractorTool,
    ValidationTool,
    RefinementTool,
)

logger = logging.getLogger("ocr_agent.agent")

class OCRAgentSystem:
    """
    Autonomous Agent System for Multimodal Structured OCR Text Extraction.
    Uses tool loop (Preprocessing -> Multimodal Extraction -> Validation -> Refinement Loop).
    """
    def __init__(
        self,
        gateway_client: Optional[GeminiGatewayClient] = None,
        max_refinement_iterations: int = 2
    ):
        self.client = gateway_client or GeminiGatewayClient()
        self.max_refinement_iterations = max_refinement_iterations

    def extract_structured_text(
        self,
        image_input: Any,
        document_type: DocumentType = DocumentType.GENERAL,
        enable_refinement: bool = True,
        filename: Optional[str] = None
    ) -> ExtractionResult:
        """
        Main Agent Execution Pipeline:
        1. Tool: Image / PDF Preprocessing (Renders PDF pages to Screenshots 1..N if PDF)
        2. Tool: Multimodal Vision Extraction per Page Screenshot via Gemini API Gateway
        3. Tool: Output Aggregation & Consolidation across pages
        4. Tool: Output Validation & Math Audit
        5. Tool (Iterative): Refinement Loop if errors detected
        """
        trajectory: List[AgentStep] = []
        step_counter = 1

        # Step 1: Preprocessing Tool (PDF page screenshot rendering or Image loading)
        logger.info(f"Agent Step {step_counter}: Running Document Preprocessor Tool...")
        try:
            pages = ImagePreprocessorTool.process_document_to_page_images(image_input, filename=filename)
            page_count = len(pages)
            trajectory.append(
                AgentStep(
                    step_number=step_counter,
                    tool_name="ImagePreprocessorTool",
                    action_summary=f"Processed document into {page_count} page screenshot(s) for vision analysis",
                    status="SUCCESS",
                    output_summary=f"Total Page Screenshots: {page_count}"
                )
            )
        except Exception as e:
            logger.error(f"Document preprocessing failed: {e}")
            return ExtractionResult(
                document_type=document_type,
                structured_data={"error": f"Document preprocessing failed: {e}"},
                validation_report=ValidationReport(is_valid=False, confidence_score=0.0, issues=[]),
                agent_trajectory=[
                    AgentStep(
                        step_number=step_counter,
                        tool_name="ImagePreprocessorTool",
                        action_summary=f"Failed to process input: {e}",
                        status="FAILED"
                    )
                ]
            )

        step_counter += 1

        # Step 2: Multi-Page Multimodal Extraction Loop (Parallel Concurrency)
        logger.info(f"Agent Step {step_counter}: Running Concurrent Multimodal Extraction across {len(pages)} page screenshot(s)...")
        aggregated_data: Dict[str, Any] = {}
        all_raw_texts: List[str] = []
        primary_image_bytes, primary_mime_type, _ = pages[0]

        import concurrent.futures

        def _process_single_page(p_item: Tuple[int, Tuple[bytes, str, Dict[str, Any]]]):
            p_idx, (p_bytes, p_mime, p_meta) = p_item
            page_num = p_meta.get("page_number", p_idx + 1)
            logger.info(f"Extracting structured text from Page {page_num}/{len(pages)} screenshot...")
            try:
                page_data = MultimodalExtractorTool.extract(
                    client=self.client,
                    image_bytes=p_bytes,
                    mime_type=p_mime,
                    document_type=document_type
                )
                return (page_num, page_data, None)
            except Exception as p_err:
                logger.warning(f"Vision extraction failed for Page {page_num}: {p_err}")
                return (page_num, {}, p_err)

        max_workers = min(5, len(pages))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            page_results = list(executor.map(_process_single_page, enumerate(pages)))

        # Sort results by page number
        page_results.sort(key=lambda x: x[0])

        for page_num, page_data, p_err in page_results:
            if p_err:
                trajectory.append(
                    AgentStep(
                        step_number=step_counter,
                        tool_name="MultimodalExtractionTool",
                        action_summary=f"[Page {page_num}/{len(pages)}] Vision extraction warning: {p_err}",
                        status="WARNING"
                    )
                )
            else:
                p_text = page_data.get("raw_text", "")
                if p_text:
                    all_raw_texts.append(f"--- Page {page_num} ---\n{p_text}")

                # Merge top-level dict attributes
                for k, v in page_data.items():
                    if k == "raw_text":
                        continue
                    if k not in aggregated_data or aggregated_data[k] is None or aggregated_data[k] == "":
                        aggregated_data[k] = v
                    elif isinstance(v, list) and isinstance(aggregated_data[k], list):
                        aggregated_data[k].extend(v)
                    elif isinstance(v, dict) and isinstance(aggregated_data[k], dict):
                        aggregated_data[k].update(v)

                trajectory.append(
                    AgentStep(
                        step_number=step_counter,
                        tool_name="MultimodalExtractionTool",
                        action_summary=f"[Page {page_num}/{len(pages)}] Extracted vision attributes from screenshot",
                        status="SUCCESS",
                        output_summary=f"Extracted {len(page_data)} attributes from Page {page_num}"
                    )
                )
            step_counter += 1

        combined_raw_text = "\n\n".join(all_raw_texts)
        if combined_raw_text:
            aggregated_data["raw_text"] = combined_raw_text

        # Step 3: Validation Tool on Combined Aggregated Output
        logger.info(f"Agent Step {step_counter}: Running Validation Tool on combined document data...")
        val_report = ValidationTool.validate(aggregated_data, document_type)
        trajectory.append(
            AgentStep(
                step_number=step_counter,
                tool_name="ValidationTool",
                action_summary=f"Audited combined multi-page document: Valid={val_report.is_valid}, Confidence={val_report.confidence_score}, MathPassed={val_report.math_checks_passed}",
                status="SUCCESS",
                output_summary=f"{len(val_report.issues)} issue(s) detected across {len(pages)} page(s). Refinement Recommended: {val_report.refinement_recommended}"
            )
        )

        step_counter += 1

        # Step 4: Refinement Tool Loop if issues found
        iteration = 0
        while (
            enable_refinement
            and val_report.refinement_recommended
            and iteration < self.max_refinement_iterations
        ):
            iteration += 1
            logger.info(f"Agent Step {step_counter}: Running Refinement Tool (Iteration {iteration})...")

            try:
                refined_data = RefinementTool.refine(
                    client=self.client,
                    image_bytes=primary_image_bytes,
                    mime_type=primary_mime_type,
                    previous_data=aggregated_data,
                    report=val_report
                )

                # Re-validate refined output
                new_val_report = ValidationTool.validate(refined_data, document_type)

                trajectory.append(
                    AgentStep(
                        step_number=step_counter,
                        tool_name="RefinementTool",
                        action_summary=f"Executed self-correction iteration {iteration}. New Confidence={new_val_report.confidence_score}",
                        status="SUCCESS",
                        output_summary=f"Issues changed from {len(val_report.issues)} to {len(new_val_report.issues)}"
                    )
                )

                aggregated_data = refined_data
                val_report = new_val_report

            except Exception as ref_err:
                logger.warning(f"Refinement iteration {iteration} failed: {ref_err}")
                trajectory.append(
                    AgentStep(
                        step_number=step_counter,
                        tool_name="RefinementTool",
                        action_summary=f"Refinement iteration {iteration} encountered error: {ref_err}",
                        status="WARNING"
                    )
                )
                break

            step_counter += 1

        return ExtractionResult(
            document_type=document_type,
            structured_data=aggregated_data,
            validation_report=val_report,
            raw_text=aggregated_data.get("raw_text", combined_raw_text),
            agent_trajectory=trajectory
        )
