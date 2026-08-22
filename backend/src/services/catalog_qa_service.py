"""Catalog Q&A RAG Engine over Structured Product Records (Phase 12e).

Answers natural language queries across the validated ProductRecord database
by performing real grounded queries and synthesizing sourced responses with exact SKU citations.
"""

from typing import Any, Dict, List, Optional
import json
import re
from google import genai

from ..db.store import store
from ..models.product_record import ProductRecord
from ..utils.logging import get_logger

logger = get_logger("catalog_qa_service")


async def answer_catalog_question(
    question: str,
    store_instance: Optional[Any] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Answer natural language catalog queries grounded on live ProductRecord database for user."""
    target_store = store_instance or store
    products = await target_store.list_products(user_id=user_id)
    
    if not products:
        return {
            "question": question,
            "answer": "The catalog currently contains no processed product records to query.",
            "cited_skus": [],
            "matching_count": 0,
        }

    # Prepare compact record context (up to 30 records for context efficiency)
    catalog_summary: List[Dict[str, Any]] = []
    for p in products[:30]:
        fields_summary = {f.name: f.value for f in p.fields if f.value is not None}
        catalog_summary.append({
            "sku": p.mfg_part_num or p.name,
            "name": p.name,
            "category": p.category,
            "confidence_overall": p.confidence_overall,
            "fields": fields_summary,
        })

    # Grounded prompt synthesis
    prompt = (
        f"You are the SourceLedger Catalog Q&A AI engine.\n"
        f"User Question: '{question}'\n\n"
        f"Available Validated Catalog Database ({len(catalog_summary)} records):\n"
        f"{json.dumps(catalog_summary, indent=2)}\n\n"
        f"Provide a concise, professional answer. Every claim must cite exact product SKUs. "
        f"Return raw JSON with keys: 'answer' (str), 'cited_skus' (list of strings), 'matching_count' (int)."
    )

    try:
        from ..agents.key_rotator import key_rotator
        import os
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "proxy-enabled"
        client = genai.Client(api_key=api_key)
        
        response = key_rotator.call_with_rotation(
            client.models.generate_content,
            model="gemini-3.6-flash",
            contents=prompt,
        )
        text = response.text or ""
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            return {
                "question": question,
                "answer": data.get("answer", "No direct match found."),
                "cited_skus": data.get("cited_skus", []),
                "matching_count": data.get("matching_count", len(data.get("cited_skus", []))),
            }
    except Exception as e:
        logger.warning("Gemini Catalog Q&A API call failed, using deterministic fallback: %s", e)

    # Fallback deterministic keyword search
    q_lower = question.lower()
    matching_prods = []
    for p in products:
        sku = p.mfg_part_num or p.name
        text_corp = f"{sku} {p.name} {p.category} " + " ".join(str(f.value) for f in p.fields)
        if any(term in text_corp.lower() for term in q_lower.split() if len(term) > 3):
            matching_prods.append(p)

    cited = [p.mfg_part_num or p.name for p in matching_prods[:5]]
    return {
        "question": question,
        "answer": f"Found {len(matching_prods)} products matching query terms in the catalog. Top matches include: {', '.join(cited) if cited else 'None'}.",
        "cited_skus": cited,
        "matching_count": len(matching_prods),
    }
