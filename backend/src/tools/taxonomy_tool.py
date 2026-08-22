"""Taxonomy & UNSPSC Classification Tool for SourceLedger Agents.

Standardizes UNSPSC codes and 4-tier taxonomy hierarchy (Dept, Class, Fine, Classpath).
"""

from typing import Dict
from ..utils.logging import get_logger

logger = get_logger("taxonomy_tool")

TAXONOMY_REGISTRY = {
    "pump": {
        "unspsc": "40151500",
        "dept": "Industrial & Commercial",
        "class": "Fluid Handling & Pumps",
        "fine": "Centrifugal Pumps",
        "classpath": "Industrial & Commercial>Fluid Handling & Pumps>Centrifugal Pumps"
    },
    "connector": {
        "unspsc": "39121400",
        "dept": "Electronics & Electrical",
        "class": "Connectors & Terminals",
        "fine": "Industrial Plugs & Receptacles",
        "classpath": "Electronics & Electrical>Connectors & Terminals>Industrial Plugs & Receptacles"
    },
    "fastener": {
        "unspsc": "31161600",
        "dept": "Hardware & Fasteners",
        "class": "Threaded Fasteners",
        "fine": "Hex Bolts & Cap Screws",
        "classpath": "Hardware & Fasteners>Threaded Fasteners>Hex Bolts & Cap Screws"
    },
    "appliance": {
        "unspsc": "52141500",
        "dept": "Appliances",
        "class": "Large Appliances",
        "fine": "Built-In Dishwashers",
        "classpath": "Appliances>Large Appliances>Built-In Dishwashers"
    }
}


def lookup_product_taxonomy(product_name: str, category: str) -> Dict[str, str]:
    """Looks up UNSPSC code and taxonomy hierarchy for a product name and category.

    Args:
        product_name: Product title or description
        category: Category string or key

    Returns:
        Dict with unspsc, dept, class, fine, and classpath.
    """
    logger.info("▶ TaxonomyTool: resolving taxonomy for '%s' (%s)", product_name, category)
    text_lower = (product_name + " " + category).lower()
    
    for key, info in TAXONOMY_REGISTRY.items():
        if key in text_lower:
            return {
                "unspsc": info["unspsc"],
                "dept": info["dept"],
                "category_class": info["class"],
                "fine_category": info["fine"],
                "classpath": info["classpath"]
            }

    # An unrecognized product is not safely classifiable from keywords alone.
    # Return an explicit review signal rather than a catalogue-wide fallback.
    return {"needs_review": "taxonomy not source-verified"}
