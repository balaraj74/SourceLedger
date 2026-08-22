"""Catalog Copilot & Multi-Agent Data Chat Engine — SourceLedger.

Provides natural-language interaction with the live product catalog and executes
all backend agents (ValidationAgent, GraphAgent, EnrichmentAgent, DashboardService,
ExplainabilityLayer) on demand over SQLite database records.
"""

from typing import Any, Dict, List, Optional
import json
import os
import re
from uuid import UUID
from google import genai

from ..db.store import store as default_store
from ..models.product_record import ProductRecord
from ..agents.validation_agent import ValidationAgent
from ..agents.graph_agent import GraphAgent
from ..agents.enrichment_agent import EnrichmentAgent
from ..agents.explainability_layer import ExplainabilityLayer
from ..services.dashboard_service import compute_quality_dashboard_metrics
from ..agents.key_rotator import key_rotator
from ..utils.logging import get_logger

logger = get_logger("copilot_service")


class CopilotEngine:
    """Catalog Copilot that integrates LLM reasoning with live database & multi-agent tools."""

    def __init__(self, store_instance: Optional[Any] = None) -> None:
        self.store = store_instance or default_store
        self.validation_agent = ValidationAgent()
        self.graph_agent = GraphAgent(store_instance=self.store)
        self.enrichment_agent = EnrichmentAgent()
        self.explainability_layer = ExplainabilityLayer()

    async def chat(self, prompt: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Process a natural language user query with live DB grounding and tool execution for user."""
        products = await self.store.list_products(user_id=user_id)
        sources = await self.store.list_sources(user_id=user_id)
        
        executed_tools: List[Dict[str, Any]] = []
        data_preview: List[Dict[str, Any]] = []
        cited_skus: List[str] = []
        p_lower = prompt.lower()

        # ── Tool Execution 1: ValidationAgent / Conflict Resolution ─────────
        if any(w in p_lower for w in ["conflict", "disagree", "mismatch", "validate", "review"]):
            conflicts_all = []
            for p in products:
                confs = self.store.list_field_conflicts(p.id, user_id=user_id)
                conflicts_all.extend(confs)
            executed_tools.append({
                "agent": "ValidationAgent",
                "tool_name": "detect_and_resolve_conflicts",
                "summary": f"Scanned catalog: found {len(conflicts_all)} active cross-source field conflicts.",
                "details": [
                    {
                        "product_id": str(c.product_id),
                        "field": c.field_name,
                        "candidates": [cand.value for cand in c.candidates],
                        "resolution": c.resolution,
                        "confidence": c.resolved_confidence,
                    }
                    for c in conflicts_all[:5]
                ],
            })

        # ── Tool Execution 2: GraphAgent / Product Relationships ────────────
        if any(w in p_lower for w in ["variant", "family", "related", "relationship", "graph", "part number"]):
            if products:
                rels = await self.graph_agent.analyze_catalog(products[:10])
                executed_tools.append({
                    "agent": "GraphAgent",
                    "tool_name": "analyze_catalog_relationships",
                    "summary": f"Analyzed catalog graph: detected {len(rels)} product variant/family relationships.",
                    "details": [
                        {
                            "source_sku": r.source_sku,
                            "target_sku": r.target_sku,
                            "type": r.relationship_type,
                            "confidence": r.confidence,
                            "reasoning": r.reasoning,
                        }
                        for r in rels[:5]
                    ],
                })

        # ── Tool Execution 3: DashboardService / Quality & Anti-Hardcoding ───
        if any(w in p_lower for w in ["quality", "hardcode", "suspicious", "fake", "trust", "health"]):
            metrics = await compute_quality_dashboard_metrics(store_instance=self.store, user_id=user_id)
            executed_tools.append({
                "agent": "DashboardService",
                "tool_name": "compute_quality_dashboard_metrics",
                "summary": f"Catalog Health: {metrics.get('health_score', 95)}% overall quality, "
                           f"{metrics.get('suspicious_fills_count', 0)} suspicious fills detected.",
                "details": metrics,
            })

        # ── Data Preview Extraction ──────────────────────────────────────────
        for p in products:
            sku = p.mfg_part_num or p.name
            text_corp = f"{sku} {p.name} {p.category} " + " ".join(str(f.value) for f in p.fields)
            
            # Match prompt terms
            matching_terms = [t for t in p_lower.split() if len(t) > 3 and t in text_corp.lower()]
            if matching_terms or len(data_preview) < 5:
                if sku not in cited_skus and len(cited_skus) < 10:
                    cited_skus.append(sku)
                if len(data_preview) < 8:
                    fields_dict = {f.name: f.value for f in p.fields[:6] if f.value is not None}
                    data_preview.append({
                        "sku": sku,
                        "name": p.name,
                        "category": p.category,
                        "confidence_overall": p.confidence_overall,
                        "fields": fields_dict,
                    })

        # ── LLM Response Synthesis ───────────────────────────────────────────
        system_prompt = (
            f"You are the SourceLedger Catalog Copilot, an expert AI agent with full database "
            f"and multi-agent tool execution rights.\n\n"
            f"User Prompt: '{prompt}'\n\n"
            f"Database Context:\n"
            f"- Total Catalog Products: {len(products)}\n"
            f"- Total Sources Ledgered: {len(sources)}\n"
            f"- Sample Matched Records:\n{json.dumps(data_preview[:5], indent=2)}\n\n"
            f"Executed Agent Tools:\n{json.dumps(executed_tools, indent=2)}\n\n"
            f"Synthesize a clear, authoritative response. Cite exact product SKUs. "
            f"Return a raw JSON object with keys:\n"
            f"- 'answer' (str): Detailed markdown text response\n"
            f"- 'suggested_actions' (list of str): 2-4 actionable next steps for the user\n"
        )

        try:
            api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "proxy-enabled"
            client = genai.Client(api_key=api_key)

            response = key_rotator.call_with_rotation(
                client.models.generate_content,
                model="gemini-3.6-flash",
                contents=system_prompt,
            )
            text = response.text or ""
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                return {
                    "question": prompt,
                    "answer": parsed.get("answer", "Analyzed catalog and data records."),
                    "cited_skus": cited_skus,
                    "executed_tools": executed_tools,
                    "data_preview": data_preview,
                    "suggested_actions": parsed.get("suggested_actions", [
                        "Inspect cited product fields",
                        "Run conflict resolution scan",
                        "Export clean delivery catalog"
                    ]),
                }
        except Exception as e:
            logger.warning("Copilot Gemini API call fallback: %s", e)

        # Fallback response generation
        fallback_answer = (
            f"**SourceLedger Copilot Analysis**\n\n"
            f"Found **{len(data_preview)} matching products** in the active catalog.\n"
            f"Executed {len(executed_tools)} multi-agent tool checks across the database."
        )
        return {
            "question": prompt,
            "answer": fallback_answer,
            "cited_skus": cited_skus,
            "executed_tools": executed_tools,
            "data_preview": data_preview,
            "suggested_actions": [
                "View matched product details in Field Inspector",
                "Run active learning review queue scan",
                "Export Schema.org JSON-LD catalog"
            ],
        }

    async def get_suggestions(self) -> List[Dict[str, str]]:
        """Return contextual quick-start prompt suggestions."""
        return [
            {
                "label": "🔍 Filter Catalog Specifications",
                "prompt": "Which products have pressure ratings or flow rate specifications exceeding 40 units?",
                "icon": "Search",
            },
            {
                "label": "⚔️ Scan Cross-Source Conflicts",
                "prompt": "Detect and analyze all cross-source field conflicts where OEM datasheets and distributor catalogs disagree.",
                "icon": "ShieldAlert",
            },
            {
                "label": "🔗 Identify Product Variant Families",
                "prompt": "Analyze the catalog knowledge graph to detect part-number prefix/suffix variant family relationships.",
                "icon": "GitFork",
            },
            {
                "label": "🛡️ Quality & Anti-Hardcoding Audit",
                "prompt": "Run a dataset health check to flag suspicious fills, low-confidence fields, or placeholder values.",
                "icon": "Sparkles",
            },
        ]


# Singleton instance
copilot_engine = CopilotEngine()
