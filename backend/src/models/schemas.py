"""Category-specific extraction schemas for SourceLedger.

Each product category (industrial pump, electrical connector, safety
fastener) has a concrete schema defining exactly which fields to
extract, their types, units, and whether they're required. These
schemas drive the Extraction Agent's structured output and the
Validation Agent's completeness checks.

The schemas are intentionally specific to each category — a pump's
"flow rate" and "head pressure" fields are meaningless for a fastener.
This domain awareness is a core differentiator vs. generic "LLM
extracts JSON" approaches.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ── Schema Definition Types ──────────────────────────────────────────


class FieldType(str, Enum):
    """Data type of a category field, used for validation."""

    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    LIST = "list"


class CategoryFieldDef(BaseModel):
    """Definition of a single field within a category schema.

    This is metadata about a field, not a field value — it tells
    the Extraction Agent what to look for and the Validation Agent
    what to check.
    """

    name: str  # Machine key, e.g. "flow_rate"
    display_name: str  # Human label, e.g. "Flow Rate"
    field_type: FieldType
    unit: Optional[str] = None  # Expected unit, e.g. "m³/h"
    required: bool = True  # Required fields reduce confidence if missing
    description: str  # What this field means — fed to the LLM prompt
    examples: list[str] = Field(default_factory=list)  # Example values for few-shot prompting


class CategorySchema(BaseModel):
    """Schema definition for a product category.

    Consumed by:
    - Extraction Agent: to build the structured output prompt
    - Validation Agent: to check completeness (are required fields present?)
    - Field Inspector UI: to render field labels and units
    """

    category_key: str  # Machine key, matches ProductRecord.category
    display_name: str  # Human-readable category name
    version: str = "1.0"
    description: str = ""  # Category description for context
    fields: list[CategoryFieldDef]

    @property
    def required_field_names(self) -> list[str]:
        """Names of all required fields in this schema."""
        return [f.name for f in self.fields if f.required]

    @property
    def optional_field_names(self) -> list[str]:
        """Names of all optional fields in this schema."""
        return [f.name for f in self.fields if not f.required]


# ═════════════════════════════════════════════════════════════════════
# Concrete Category Schemas
# ═════════════════════════════════════════════════════════════════════


INDUSTRIAL_PUMP_SCHEMA = CategorySchema(
    category_key="industrial_pump",
    display_name="Industrial Pump",
    description="Centrifugal, positive displacement, submersible, and other industrial pump types used in water treatment, HVAC, chemical processing, and general industry.",
    fields=[
        CategoryFieldDef(
            name="manufacturer",
            display_name="Manufacturer",
            field_type=FieldType.STRING,
            required=True,
            description="The manufacturer or brand name of the pump",
            examples=["Grundfos", "Xylem", "Sulzer", "KSB", "Wilo"],
        ),
        CategoryFieldDef(
            name="model_number",
            display_name="Model Number",
            field_type=FieldType.STRING,
            required=True,
            description="Manufacturer's model or part number",
            examples=["CR 15-3", "e-SV 5SV13", "SEG.40.09.2.50B"],
        ),
        CategoryFieldDef(
            name="pump_type",
            display_name="Pump Type",
            field_type=FieldType.STRING,
            required=True,
            description="Classification of pump mechanism (centrifugal, positive displacement, submersible, diaphragm, etc.)",
            examples=["centrifugal", "positive displacement", "submersible", "diaphragm", "gear pump"],
        ),
        CategoryFieldDef(
            name="flow_rate",
            display_name="Flow Rate",
            field_type=FieldType.NUMBER,
            unit="m³/h",
            required=True,
            description="Maximum or rated volumetric flow rate",
            examples=["15.0", "25.5", "120.0"],
        ),
        CategoryFieldDef(
            name="head_pressure",
            display_name="Head Pressure",
            field_type=FieldType.NUMBER,
            unit="m",
            required=True,
            description="Maximum or rated total dynamic head",
            examples=["45.0", "120.0", "32.0"],
        ),
        CategoryFieldDef(
            name="power_rating",
            display_name="Power Rating",
            field_type=FieldType.NUMBER,
            unit="kW",
            required=True,
            description="Motor power rating",
            examples=["2.2", "5.5", "11.0", "37.0"],
        ),
        CategoryFieldDef(
            name="inlet_size",
            display_name="Inlet Size",
            field_type=FieldType.STRING,
            required=False,
            description="Inlet connection diameter and type",
            examples=["DN50", "2 inch BSP", "65mm flanged"],
        ),
        CategoryFieldDef(
            name="outlet_size",
            display_name="Outlet Size",
            field_type=FieldType.STRING,
            required=False,
            description="Outlet connection diameter and type",
            examples=["DN40", "1.5 inch BSP", "50mm flanged"],
        ),
        CategoryFieldDef(
            name="material_body",
            display_name="Body Material",
            field_type=FieldType.STRING,
            required=True,
            description="Material of the pump body or casing",
            examples=["cast iron", "stainless steel 316", "bronze", "cast iron GJL-250"],
        ),
        CategoryFieldDef(
            name="material_impeller",
            display_name="Impeller Material",
            field_type=FieldType.STRING,
            required=False,
            description="Material of the impeller or rotor",
            examples=["stainless steel 304", "Noryl", "bronze", "composite"],
        ),
        CategoryFieldDef(
            name="temperature_range",
            display_name="Temperature Range",
            field_type=FieldType.STRING,
            unit="°C",
            required=False,
            description="Allowable operating temperature range of the pumped medium",
            examples=["-10 to 120", "0 to 90", "-20 to 140"],
        ),
        CategoryFieldDef(
            name="max_pressure",
            display_name="Maximum Working Pressure",
            field_type=FieldType.NUMBER,
            unit="bar",
            required=False,
            description="Maximum allowable working pressure",
            examples=["16", "25", "40"],
        ),
        CategoryFieldDef(
            name="voltage",
            display_name="Voltage / Electrical Supply",
            field_type=FieldType.STRING,
            required=False,
            description="Electrical supply specification",
            examples=["230V/1ph/50Hz", "400V/3ph/50Hz", "460V/3ph/60Hz"],
        ),
        CategoryFieldDef(
            name="weight",
            display_name="Weight",
            field_type=FieldType.NUMBER,
            unit="kg",
            required=False,
            description="Net weight of the pump assembly",
            examples=["45.0", "120.0", "18.5"],
        ),
        CategoryFieldDef(
            name="certifications",
            display_name="Certifications",
            field_type=FieldType.LIST,
            required=False,
            description="Applicable certifications, standards compliance, and approvals",
            examples=["CE", "ATEX", "API 610", "ISO 9906", "WRAS"],
        ),
    ],
)


ELECTRICAL_CONNECTOR_SCHEMA = CategorySchema(
    category_key="electrical_connector",
    display_name="Electrical Connector",
    description="Circular, rectangular, PCB, terminal block, and other electrical connectors used in industrial, military, automotive, and general electronics applications.",
    fields=[
        CategoryFieldDef(
            name="manufacturer",
            display_name="Manufacturer",
            field_type=FieldType.STRING,
            required=True,
            description="The manufacturer or brand name",
            examples=["TE Connectivity", "Molex", "Amphenol", "Phoenix Contact", "Harting"],
        ),
        CategoryFieldDef(
            name="part_number",
            display_name="Part Number",
            field_type=FieldType.STRING,
            required=True,
            description="Manufacturer's part number or catalog number",
            examples=["1-480426-0", "39-01-2100", "MS3106A-18-1S", "1776275-2"],
        ),
        CategoryFieldDef(
            name="connector_type",
            display_name="Connector Type",
            field_type=FieldType.STRING,
            required=True,
            description="Classification of connector form factor",
            examples=["circular", "rectangular", "PCB header", "terminal block", "D-sub", "modular jack"],
        ),
        CategoryFieldDef(
            name="number_of_contacts",
            display_name="Number of Contacts",
            field_type=FieldType.NUMBER,
            required=True,
            description="Total number of electrical contacts or pins",
            examples=["4", "10", "24", "37"],
        ),
        CategoryFieldDef(
            name="contact_pitch",
            display_name="Contact Pitch",
            field_type=FieldType.NUMBER,
            unit="mm",
            required=False,
            description="Center-to-center spacing between adjacent contacts",
            examples=["2.54", "1.27", "3.81", "5.08"],
        ),
        CategoryFieldDef(
            name="voltage_rating",
            display_name="Voltage Rating",
            field_type=FieldType.NUMBER,
            unit="V",
            required=True,
            description="Maximum rated voltage",
            examples=["250", "600", "1000"],
        ),
        CategoryFieldDef(
            name="current_rating",
            display_name="Current Rating",
            field_type=FieldType.NUMBER,
            unit="A",
            required=True,
            description="Maximum rated current per contact",
            examples=["5", "13", "25", "40"],
        ),
        CategoryFieldDef(
            name="gender",
            display_name="Gender",
            field_type=FieldType.STRING,
            required=True,
            description="Connector gender (plug/receptacle orientation)",
            examples=["male (plug)", "female (receptacle)", "hermaphroditic"],
        ),
        CategoryFieldDef(
            name="mounting_type",
            display_name="Mounting Type",
            field_type=FieldType.STRING,
            required=True,
            description="How the connector is mounted or installed",
            examples=["panel mount", "cable mount", "PCB through-hole", "PCB surface mount", "DIN rail"],
        ),
        CategoryFieldDef(
            name="ip_rating",
            display_name="IP Rating",
            field_type=FieldType.STRING,
            required=False,
            description="Ingress Protection rating when mated",
            examples=["IP67", "IP68", "IP44", "IP20"],
        ),
        CategoryFieldDef(
            name="material_housing",
            display_name="Housing Material",
            field_type=FieldType.STRING,
            required=False,
            description="Material of the connector housing or shell",
            examples=["nylon PA66", "polycarbonate", "die-cast aluminium", "stainless steel"],
        ),
        CategoryFieldDef(
            name="material_contacts",
            display_name="Contact Material",
            field_type=FieldType.STRING,
            required=False,
            description="Material and plating of electrical contacts",
            examples=["brass, tin-plated", "phosphor bronze, gold-plated", "copper alloy, silver-plated"],
        ),
        CategoryFieldDef(
            name="temperature_range",
            display_name="Temperature Range",
            field_type=FieldType.STRING,
            unit="°C",
            required=False,
            description="Operating temperature range",
            examples=["-40 to 105", "-25 to 85", "-55 to 125"],
        ),
        CategoryFieldDef(
            name="wire_gauge_range",
            display_name="Wire Gauge Range",
            field_type=FieldType.STRING,
            required=False,
            description="Compatible wire gauge or cross-section range",
            examples=["22-16 AWG", "18-14 AWG", "0.5-2.5 mm²"],
        ),
        CategoryFieldDef(
            name="certifications",
            display_name="Certifications",
            field_type=FieldType.LIST,
            required=False,
            description="Applicable certifications and standards compliance",
            examples=["UL", "CE", "CSA", "RoHS", "MIL-DTL-5015", "MIL-DTL-38999"],
        ),
    ],
)


SAFETY_FASTENER_SCHEMA = CategorySchema(
    category_key="safety_fastener",
    display_name="Safety Fastener",
    description="Hex bolts, lock nuts, socket cap screws, wedge-locking washers, and other safety-critical fasteners used in structural, automotive, aerospace, and heavy industry applications.",
    fields=[
        CategoryFieldDef(
            name="manufacturer",
            display_name="Manufacturer",
            field_type=FieldType.STRING,
            required=True,
            description="The manufacturer or brand name",
            examples=["Nord-Lock", "Hilti", "Huck", "Unbrako", "Bossard"],
        ),
        CategoryFieldDef(
            name="part_number",
            display_name="Part Number",
            field_type=FieldType.STRING,
            required=True,
            description="Manufacturer's part or catalog number",
            examples=["NL12", "HST3 M12x100", "BOM-R6", "HIT-HY 200-A"],
        ),
        CategoryFieldDef(
            name="fastener_type",
            display_name="Fastener Type",
            field_type=FieldType.STRING,
            required=True,
            description="Classification of fastener type",
            examples=["hex bolt", "lock nut", "socket cap screw", "wedge-locking washer", "blind rivet", "anchor bolt"],
        ),
        CategoryFieldDef(
            name="thread_size",
            display_name="Thread Size",
            field_type=FieldType.STRING,
            required=True,
            description="Thread diameter designation (metric or imperial)",
            examples=["M8", "M12", "M16", "1/2-13 UNC", "3/8-16 UNC"],
        ),
        CategoryFieldDef(
            name="thread_pitch",
            display_name="Thread Pitch",
            field_type=FieldType.NUMBER,
            unit="mm",
            required=False,
            description="Thread pitch — distance between adjacent threads (metric fasteners)",
            examples=["1.25", "1.75", "2.0"],
        ),
        CategoryFieldDef(
            name="length",
            display_name="Length",
            field_type=FieldType.NUMBER,
            unit="mm",
            required=True,
            description="Overall length or nominal length under the head",
            examples=["30", "50", "80", "100"],
        ),
        CategoryFieldDef(
            name="material",
            display_name="Material",
            field_type=FieldType.STRING,
            required=True,
            description="Primary material composition",
            examples=["carbon steel", "alloy steel", "stainless steel A2", "stainless steel A4", "titanium Grade 5"],
        ),
        CategoryFieldDef(
            name="grade_class",
            display_name="Grade / Property Class",
            field_type=FieldType.STRING,
            required=True,
            description="Strength grade (metric) or SAE grade (imperial)",
            examples=["8.8", "10.9", "12.9", "A2-70", "A4-80", "SAE Grade 5"],
        ),
        CategoryFieldDef(
            name="finish",
            display_name="Finish / Coating",
            field_type=FieldType.STRING,
            required=False,
            description="Surface treatment, coating, or plating",
            examples=["zinc-plated", "hot-dip galvanized", "geomet", "plain / self-colour", "cadmium-plated", "black oxide"],
        ),
        CategoryFieldDef(
            name="tensile_strength",
            display_name="Minimum Tensile Strength",
            field_type=FieldType.NUMBER,
            unit="MPa",
            required=False,
            description="Minimum ultimate tensile strength",
            examples=["800", "1040", "1220"],
        ),
        CategoryFieldDef(
            name="proof_load",
            display_name="Proof Load",
            field_type=FieldType.NUMBER,
            unit="kN",
            required=False,
            description="Proof load — maximum load without permanent deformation",
            examples=["28.8", "52.0", "120.0"],
        ),
        CategoryFieldDef(
            name="head_type",
            display_name="Head Type",
            field_type=FieldType.STRING,
            required=False,
            description="Shape/form of the fastener head",
            examples=["hex", "socket cap", "flanged hex", "countersunk", "button head", "pan head"],
        ),
        CategoryFieldDef(
            name="drive_type",
            display_name="Drive Type",
            field_type=FieldType.STRING,
            required=False,
            description="Tool drive interface",
            examples=["external hex", "internal hex (Allen)", "Torx", "Torx Plus", "Phillips"],
        ),
        CategoryFieldDef(
            name="locking_mechanism",
            display_name="Locking / Anti-Vibration Mechanism",
            field_type=FieldType.STRING,
            required=False,
            description="Safety locking or anti-vibration feature (key differentiator for safety fasteners)",
            examples=["nylon insert (Nyloc)", "wedge-lock", "prevailing torque", "serrated flange", "thread-locking patch"],
        ),
        CategoryFieldDef(
            name="certifications",
            display_name="Certifications / Standards",
            field_type=FieldType.LIST,
            required=False,
            description="Applicable material, dimensional, and performance standards",
            examples=["ISO 898-1", "ASTM A325", "DIN 931", "ISO 4014", "AS/NZS 1252", "ASTM F3125"],
        ),
    ],
)


# ─────────────────────────────────────────────────────────────────────
# Power Tool Schema
# ─────────────────────────────────────────────────────────────────────

POWER_TOOL_SCHEMA = CategorySchema(
    category_key="power_tool",
    display_name="Power Tool",
    description="Cordless and corded power tools — drills, drivers, saws, nailers, grinders, etc.",
    fields=[
        CategoryFieldDef(
            name="manufacturer",
            display_name="Manufacturer / Brand",
            field_type=FieldType.STRING,
            required=True,
            description="Tool manufacturer brand name",
            examples=["Milwaukee", "DEWALT", "Makita", "Bosch", "Ryobi", "Metabo", "Hilti"],
        ),
        CategoryFieldDef(
            name="model_number",
            display_name="Model Number",
            field_type=FieldType.STRING,
            required=True,
            description="Manufacturer model or part number as printed on the tool/box",
            examples=["DCD803B", "2909-20", "XNB04Z", "D25333K"],
        ),
        CategoryFieldDef(
            name="tool_type",
            display_name="Tool Type",
            field_type=FieldType.STRING,
            required=True,
            description="Type of power tool",
            examples=["Hammer Drill", "Impact Driver", "Brad Nailer", "Reciprocating Saw", "Circular Saw", "Angle Grinder"],
        ),
        CategoryFieldDef(
            name="voltage",
            display_name="Voltage (V)",
            field_type=FieldType.NUMBER,
            unit="V",
            required=True,
            description="Battery/power voltage",
            examples=["18", "20", "12", "36", "120"],
        ),
        CategoryFieldDef(
            name="battery_system",
            display_name="Battery System / Platform",
            field_type=FieldType.STRING,
            required=True,
            description="Manufacturer battery platform name",
            examples=["M18", "M12", "20V MAX", "18V LXT", "18V PROFACTOR", "ProCORE18V"],
        ),
        CategoryFieldDef(
            name="is_bare_tool",
            display_name="Bare Tool (No Battery)",
            field_type=FieldType.BOOLEAN,
            required=True,
            description="True if sold without battery/charger (bare tool only)",
            examples=["true", "false"],
        ),
        CategoryFieldDef(
            name="drive_size",
            display_name="Drive / Chuck Size",
            field_type=FieldType.STRING,
            required=False,
            description="Chuck or drive size",
            examples=["1/2\"", "1/4\"", "3/8\"", "SDS-plus", "SDS-max"],
        ),
        CategoryFieldDef(
            name="no_load_rpm",
            display_name="No-Load Speed (RPM)",
            field_type=FieldType.NUMBER,
            unit="RPM",
            required=False,
            description="Maximum no-load speed in RPM",
            examples=["0-1800", "0-2000", "0-450", "0-550"],
        ),
        CategoryFieldDef(
            name="torque",
            display_name="Max Torque",
            field_type=FieldType.STRING,
            required=False,
            description="Maximum torque output with unit",
            examples=["60 Nm", "750 in-lbs", "1200 in-lbs", "200 ft-lbs"],
        ),
        CategoryFieldDef(
            name="weight",
            display_name="Weight (kg)",
            field_type=FieldType.NUMBER,
            unit="kg",
            required=False,
            description="Tool weight in kilograms (bare tool without battery)",
            examples=["1.4", "2.1", "0.9", "1.7"],
        ),
        CategoryFieldDef(
            name="nail_gauge",
            display_name="Nail Gauge",
            field_type=FieldType.STRING,
            required=False,
            description="For nailers: accepted nail gauge",
            examples=["18 GA", "16 GA", "15 GA", "30°"],
        ),
        CategoryFieldDef(
            name="nail_length_range",
            display_name="Nail Length Range",
            field_type=FieldType.STRING,
            required=False,
            description="For nailers: accepted nail lengths",
            examples=["3/4\" to 2\"", "1\" to 2-1/2\"", "1-1/4\" to 3-1/2\""],
        ),
        CategoryFieldDef(
            name="certifications",
            display_name="Certifications",
            field_type=FieldType.LIST,
            required=False,
            description="Safety and compliance certifications",
            examples=["UL", "CSA", "CE", "RoHS"],
        ),
        CategoryFieldDef(
            name="compatible_accessories",
            display_name="Compatible Accessories",
            field_type=FieldType.LIST,
            required=False,
            description="Compatible batteries, chargers, or accessories",
            examples=["M18 REDLITHIUM", "XC5.0 Battery", "20V MAX Batteries"],
        ),
        CategoryFieldDef(
            name="color",
            display_name="Color",
            field_type=FieldType.STRING,
            required=False,
            description="Tool body color",
            examples=["Red/Black", "Yellow/Black", "Teal/Black", "Blue"],
        ),
        CategoryFieldDef(
            name="country_of_manufacture",
            display_name="Country of Manufacture",
            field_type=FieldType.STRING,
            required=False,
            description="Country where the tool is manufactured",
            examples=["USA", "China", "Japan", "Germany", "Mexico"],
        ),
        CategoryFieldDef(
            name="upc",
            display_name="UPC / EAN Barcode",
            field_type=FieldType.STRING,
            required=False,
            description="Universal Product Code or EAN barcode",
            examples=["045242488353", "638448158403"],
        ),
    ],
)


# ─────────────────────────────────────────────────────────────────────
# Home Appliance Schema
# ─────────────────────────────────────────────────────────────────────

HOME_APPLIANCE_SCHEMA = CategorySchema(
    category_key="home_appliance",
    display_name="Home Appliance",
    description="Major home appliances — dishwashers, washers, dryers, refrigerators, ranges, etc.",
    fields=[
        CategoryFieldDef(
            name="manufacturer",
            display_name="Manufacturer / Brand",
            field_type=FieldType.STRING,
            required=True,
            description="Appliance manufacturer brand",
            examples=["Frigidaire", "Whirlpool", "GE Appliances", "Bosch", "Samsung", "Miele", "LG"],
        ),
        CategoryFieldDef(
            name="model_number",
            display_name="Model Number",
            field_type=FieldType.STRING,
            required=True,
            description="Manufacturer model number",
            examples=["PDSH4816AF", "WDTS7024RZ", "WDT780SAEM"],
        ),
        CategoryFieldDef(
            name="appliance_type",
            display_name="Appliance Type",
            field_type=FieldType.STRING,
            required=True,
            description="Type of home appliance",
            examples=["Dishwasher", "Washing Machine", "Dryer", "Refrigerator", "Range", "Microwave"],
        ),
        CategoryFieldDef(
            name="color_finish",
            display_name="Color / Finish",
            field_type=FieldType.STRING,
            required=True,
            description="Appliance color or finish",
            examples=["Stainless Steel", "Black Stainless", "White", "Black", "Fingerprint Resistant"],
        ),
        CategoryFieldDef(
            name="energy_star",
            display_name="Energy Star Certified",
            field_type=FieldType.BOOLEAN,
            required=True,
            description="Whether the appliance is Energy Star certified",
            examples=["true", "false"],
        ),
        CategoryFieldDef(
            name="capacity",
            display_name="Capacity",
            field_type=FieldType.STRING,
            required=False,
            description="Capacity in relevant units (place settings, cubic feet, etc.)",
            examples=["14 Place Settings", "4.5 cu ft", "18 cu ft"],
        ),
        CategoryFieldDef(
            name="number_of_cycles",
            display_name="Number of Wash/Dry Cycles",
            field_type=FieldType.NUMBER,
            required=False,
            description="Number of wash or dry cycles/programs",
            examples=["5", "8", "12"],
        ),
        CategoryFieldDef(
            name="decibel_level",
            display_name="Noise Level (dBA)",
            field_type=FieldType.NUMBER,
            unit="dBA",
            required=False,
            description="Operating noise level in decibels",
            examples=["47", "50", "55"],
        ),
        CategoryFieldDef(
            name="installation_type",
            display_name="Installation Type",
            field_type=FieldType.STRING,
            required=False,
            description="Built-in, freestanding, slide-in, etc.",
            examples=["Built-In", "Freestanding", "Slide-In", "Drop-In"],
        ),
        CategoryFieldDef(
            name="dimensions",
            display_name="Dimensions (WxDxH)",
            field_type=FieldType.STRING,
            required=False,
            description="Width x Depth x Height in inches",
            examples=["24\" x 24\" x 34\"", "30\" x 28\" x 36\""],
        ),
        CategoryFieldDef(
            name="certifications",
            display_name="Certifications",
            field_type=FieldType.LIST,
            required=False,
            description="Safety and energy certifications",
            examples=["Energy Star", "UL Listed", "NSF Certified"],
        ),
    ],
)


# ═════════════════════════════════════════════════════════════════════
# Category Registry
# ═════════════════════════════════════════════════════════════════════


# ── Generic / Universal Schema ─────────────────────────────────────────────
GENERIC_SCHEMA = CategorySchema(
    category_key="generic",
    display_name="General Product",
    fields=[
        CategoryFieldDef(name="manufacturer",         display_name="Manufacturer",          field_type=FieldType.STRING,  required=True,  unit=None,  description="Brand or manufacturer name"),
        CategoryFieldDef(name="model_number",          display_name="Model / Part Number",   field_type=FieldType.STRING,  required=True,  unit=None,  description="Manufacturer part or model number"),
        CategoryFieldDef(name="short_desc",            display_name="Short Description",      field_type=FieldType.STRING,  required=True,  unit=None,  description="One-line e-commerce product description"),
        CategoryFieldDef(name="long_desc1",            display_name="Long Description",       field_type=FieldType.STRING,  required=False, unit=None,  description="Full product description for PDP"),
        CategoryFieldDef(name="product_image",         display_name="Product Image URL",      field_type=FieldType.STRING,  required=False, unit=None,  description="Primary product image URL"),
        CategoryFieldDef(name="mfr_url",               display_name="Manufacturer URL",       field_type=FieldType.STRING,  required=False, unit=None,  description="Official manufacturer product page URL"),
        CategoryFieldDef(name="upc",                   display_name="UPC",                    field_type=FieldType.STRING,  required=False, unit=None,  description="Universal Product Code barcode"),
        CategoryFieldDef(name="country_of_origin",     display_name="Country Of Origin",      field_type=FieldType.STRING,  required=False, unit=None,  description="Country where the product was manufactured"),
        CategoryFieldDef(name="item_features",         display_name="Item Features",          field_type=FieldType.LIST,    required=False, unit=None,  description="List of key product features / bullet points"),
        CategoryFieldDef(name="certifications",        display_name="Standards / Approvals",  field_type=FieldType.LIST,    required=False, unit=None,  description="Standards and safety certifications (UL, CE, etc.)"),
        CategoryFieldDef(name="unspsc_code",           display_name="UNSPSC Code",            field_type=FieldType.STRING,  required=False, unit=None,  description="UNSPSC commodity code"),
        CategoryFieldDef(name="specification_sheet",   display_name="Specification Sheet",    field_type=FieldType.STRING,  required=False, unit=None,  description="Link to PDF specification sheet"),
        CategoryFieldDef(name="marketing_description", display_name="Marketing Description",  field_type=FieldType.STRING,  required=False, unit=None,  description="Marketing / promotional product description"),
    ],
)


CATEGORY_REGISTRY: dict[str, CategorySchema] = {
    INDUSTRIAL_PUMP_SCHEMA.category_key:       INDUSTRIAL_PUMP_SCHEMA,
    ELECTRICAL_CONNECTOR_SCHEMA.category_key:  ELECTRICAL_CONNECTOR_SCHEMA,
    SAFETY_FASTENER_SCHEMA.category_key:       SAFETY_FASTENER_SCHEMA,
    POWER_TOOL_SCHEMA.category_key:            POWER_TOOL_SCHEMA,
    HOME_APPLIANCE_SCHEMA.category_key:        HOME_APPLIANCE_SCHEMA,
    GENERIC_SCHEMA.category_key:               GENERIC_SCHEMA,
}


def get_category_schema(category_key: str) -> CategorySchema | None:
    """Look up a category schema by key. Falls back to 'generic' for unknown categories."""
    return CATEGORY_REGISTRY.get(category_key) or CATEGORY_REGISTRY.get("generic")


def list_categories() -> list[CategorySchema]:
    """Return all registered category schemas."""
    return list(CATEGORY_REGISTRY.values())


# ── Phase 7–10 Data Models ────────────────────────────────────────────────


class FieldCandidate(BaseModel):
    """Candidate field value extracted from a specific source."""

    value: Any
    source_id: str
    trust_tier: int
    raw_excerpt: str = ""


class FieldConflict(BaseModel):
    """Recorded conflict when >= 2 sources disagree on a field value for a product."""

    id: UUID = Field(default_factory=uuid4)
    product_id: UUID
    field_name: str
    candidates: list[FieldCandidate]
    resolution: str
    resolution_reasoning: str
    resolved_confidence: int


class ProductRelationship(BaseModel):
    """Product knowledge graph relationship between two SKUs."""

    id: UUID = Field(default_factory=uuid4)
    source_sku: str
    target_sku: str
    relationship_type: Literal[
        "variant_of", "substitute_for", "compatible_with", "accessory_for", "same_family"
    ]
    confidence: int  # 0-100 scale
    reasoning: str
    evidence_field: Optional[str] = None


class CorrectionPattern(BaseModel):
    """Aggregated active learning pattern computed from reviewer corrections."""

    category: str
    field_name: str
    manufacturer: Optional[str] = None
    correction_count: int = 0
    avg_confidence_before_correction: float = 0.0
    last_updated: datetime = Field(default_factory=datetime.utcnow)


