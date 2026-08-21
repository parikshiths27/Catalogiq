"""
Unit & Integration Tests for CatalogIQ Phase 11: Hackathon Enrichment Foundation.

Covers:
- PlaceholderCleaner (cleaning unbranded/dummy values)
- Manufacturer & Brand normalization (canonical master matching, trademark symbols, legal casing)
- MPN preservation & SKU handling
- Taxonomy & Classpath classification
- Attribute extraction & LOV constraints
- UOM standards normalization
- Decimal to fraction exact conversions (Decimal_Fraction standard)
- Controlled description generation (Invoice, Mobile, Short/Title, Long)
- Character limit and casing validations
- ClaimChecker anti-hallucination verification
- Evidence and confidence scoring
- Deep Category specialization (Pipe & Tubing Fittings)
- 200-row benchmark evaluator
"""
import os
import pytest
from app.services.enrichment.reference_loader import get_reference_loader, ReferenceDataLoader
from app.services.enrichment.normalizers import (
    PlaceholderCleaner,
    FractionNormalizer,
    UOMNormalizer,
    ManufacturerBrandNormalizer,
)
from app.services.enrichment.taxonomy import TaxonomyClassifier
from app.services.enrichment.attributes import AttributeExtractor
from app.services.enrichment.description_builder import DescriptionBuilder
from app.services.enrichment.validator import DeterministicValidator
from app.services.enrichment.evidence import EvidenceTracker
from app.services.enrichment.pipeline import EnrichmentPipeline
from app.services.enrichment.deep_category import FittingsDeepCategoryEnricher
from app.services.enrichment.benchmark import BenchmarkEvaluator


# ---------------------------------------------------------------------------
# 1. Placeholder Cleaning Tests
# ---------------------------------------------------------------------------
def test_placeholder_cleaning():
    """Verify placeholder values are recognized and never leak into canonical output."""
    assert PlaceholderCleaner.is_placeholder("-- Unbranded --") is True
    assert PlaceholderCleaner.is_placeholder("-- No Unilog Brand --") is True
    assert PlaceholderCleaner.is_placeholder("-- No DIB Brand --") is True
    assert PlaceholderCleaner.is_placeholder("-") is True
    assert PlaceholderCleaner.is_placeholder("COMMODITY - UNBRANDED") is True
    assert PlaceholderCleaner.is_placeholder("Display Only") is True
    assert PlaceholderCleaner.is_placeholder("None") is True
    assert PlaceholderCleaner.is_placeholder(None) is True

    # Real brands should NOT be placeholders
    assert PlaceholderCleaner.is_placeholder("TREX") is False
    assert PlaceholderCleaner.is_placeholder("Milwaukee") is False
    assert PlaceholderCleaner.is_placeholder("3M") is False

    # Text segment cleanup
    cleaned = PlaceholderCleaner.clean_text_segment("PDSH4816AF Dishwasher SS - Display Only")
    assert cleaned == "PDSH4816AF Dishwasher SS"


# ---------------------------------------------------------------------------
# 2. Manufacturer & Brand Normalization Tests
# ---------------------------------------------------------------------------
def test_manufacturer_and_brand_matching():
    """Verify canonical manufacturer/brand resolution with legal suffixes and registered symbols."""
    norm = ManufacturerBrandNormalizer()

    # Exemplar 1: Frigidaire Dishwasher via APPDE cooperative
    res1 = norm.resolve(
        mfg_part_num="PDSH4816AF",
        part_desc="PDSH4816AF Frigidaire Dishwasher SS",
        part_manuf="Appliance Dealers Cooperative (APPDE)",
    )
    assert res1["canonical_manufacturer"] == "Rheem Manufacturing"
    assert res1["canonical_brand"] == "FRIGIDAIRE®"
    assert res1["confidence"] >= 0.90
    assert not res1["needs_review"]

    # Exemplar 2: Whirlpool Dishwasher via APPDE cooperative
    res2 = norm.resolve(
        mfg_part_num="WDTS7024RZ",
        part_desc="WDTS7024RZ Whirlpool Dishwasher SS",
        part_manuf="Appliance Dealers Cooperative (APPDE)",
    )
    assert res2["canonical_manufacturer"] == "Whirlpool Corporation"
    assert res2["canonical_brand"] == "Whirlpool®"

    # Exemplar 3: Freud / Diablo Cut-Off Disc
    res3 = norm.resolve(
        mfg_part_num="DBD090094101F",
        part_desc="DBD090094101F Diablo 9\" - Metal Cut-Off Disc",
        part_manuf="Freud Inc (2435)",
    )
    assert res3["canonical_manufacturer"] == "Freud America, Inc."
    assert res3["canonical_brand"] == "Diablo®"

    # Exemplar 4: Milwaukee Accessory
    res4 = norm.resolve(
        mfg_part_num="49-94-0013",
        part_desc="49-94-0013 Milw 5\"x.045\"x7/8\" Metal Cut Off Disc",
        part_manuf="Milwaukee Accessory (4031)",
    )
    assert res4["canonical_manufacturer"] == "Milwaukee Electric Tool Corporation"
    assert res4["canonical_brand"] == "Milwaukee®"

    # Exemplar 5: Trex Decking via US Lumber
    res5 = norm.resolve(
        mfg_part_num="543140016",
        part_desc="1nx6-16' Biscayne Sq Edge - Trex Transcend Lineage Decking",
        part_manuf="U S Lumber (3073)",
        e1_brand="TREX",
    )
    assert res5["canonical_manufacturer"] == "Trex Company, Inc."
    assert res5["canonical_brand"] == "Trex®"


def test_unresolved_manufacturer_marks_needs_review():
    """Verify ambiguous or unknown manufacturer triggers needs_review without crashing."""
    norm = ManufacturerBrandNormalizer()
    res = norm.resolve(
        mfg_part_num="UNKNOWN-99",
        part_desc="Generic Unknown Part Description",
        part_manuf=None,
    )
    assert res["needs_review"] is True
    assert res["confidence"] <= 0.50


# ---------------------------------------------------------------------------
# 3. Fraction & UOM Normalization Tests
# ---------------------------------------------------------------------------
def test_exact_decimal_fraction_lookup():
    """Verify authoritative Decimal_Fraction lookups."""
    frac_norm = FractionNormalizer()

    assert frac_norm.decimal_to_fraction(0.5) == "1/2"
    assert frac_norm.decimal_to_fraction(0.25) == "1/4"
    assert frac_norm.decimal_to_fraction(0.75) == "3/4"
    assert frac_norm.decimal_to_fraction(0.125) == "1/8"
    assert frac_norm.decimal_to_fraction(0.0625) == "1/16"
    assert frac_norm.decimal_to_fraction(50.25) == "50-1/4"
    assert frac_norm.decimal_to_fraction(50.1875) == "50-3/16"
    assert frac_norm.decimal_to_fraction(33.4375) == "33-7/16"
    assert frac_norm.decimal_to_fraction(23.875) == "23-7/8"
    assert frac_norm.decimal_to_fraction(22.625) == "22-5/8"

    # Dimension string normalization
    norm_str = frac_norm.normalize_dimension_string("50.25 in Depth With Door Open")
    assert "50-1/4 in" in norm_str


def test_uom_standard_abbreviations():
    """Verify strict master UOM standards are enforced."""
    uom_norm = UOMNormalizer()

    assert uom_norm.normalize("inches") == "in"
    assert uom_norm.normalize("inch") == "in"
    assert uom_norm.normalize("in.") == "in"
    assert uom_norm.normalize("\"") == "in"
    assert uom_norm.normalize("feet") == "ft"
    assert uom_norm.normalize("volts") == "V"
    assert uom_norm.normalize("vac") == "V"
    assert uom_norm.normalize("amperes") == "A"
    assert uom_norm.normalize("dBA") == "dBA"
    assert uom_norm.normalize("decibels") == "dBA"
    assert uom_norm.normalize("gpm") == "gpm"
    assert uom_norm.normalize("lbs") == "lb"
    assert uom_norm.normalize("pack") == "PK"


# ---------------------------------------------------------------------------
# 4. Taxonomy & Attribute Extraction Tests
# ---------------------------------------------------------------------------
def test_taxonomy_classification():
    """Verify hierarchical classification into Dept, Class, Fine, and Classpath."""
    classifier = TaxonomyClassifier()

    tax1 = classifier.classify("PDSH4816AF Dishwasher SS")
    assert tax1["dept"] == "Appliances"
    assert tax1["class_"] == "Large Appliances"
    assert tax1["fine"] == "Dishwashers"
    assert "Built-In Dishwashers" in tax1["classpath"]

    tax2 = classifier.classify("49-94-0013 Milw 5\"x.045\"x7/8\" Metal Cut Off Disc")
    assert tax2["dept"] == "Hardware & Tools"
    assert "Abrasives" in tax2["fine"] or "Abrasives" in tax2["classpath"]

    tax3 = classifier.classify("1nx6-16' Biscayne Sq Edge - Trex Transcend Lineage Decking")
    assert tax3["dept"] == "Building Materials"
    assert "Composite Decking" in tax3["classpath"]


def test_attribute_extraction_and_lov_mapping():
    """Verify domain-constrained attribute extraction with fraction and UOM standards."""
    extractor = AttributeExtractor()

    attrs = extractor.extract_attributes(
        "FRIGIDAIRE Dishwasher Professional Series, 120 V, 15 A, 47 dBA, 5-Wash Cycle, Leg Mounting, Stainless Steel, 50.25 in Depth With Door Open",
        classpath="Appliances & Consumer Electronics>Kitchen Appliances>Built-In Dishwashers",
    )
    attr_dict = {a.label: a.normalized_value for a in attrs}
    uom_dict = {a.label: a.normalized_uom for a in attrs}

    assert attr_dict.get("Series") == "Professional Series"
    assert attr_dict.get("Voltage Rating") == "120"
    assert uom_dict.get("Voltage Rating") == "V"
    assert attr_dict.get("Amperage Rating") == "15"
    assert uom_dict.get("Amperage Rating") == "A"
    assert attr_dict.get("Sound Level") == "47"
    assert uom_dict.get("Sound Level") == "dBA"
    assert attr_dict.get("Mounting Type") == "Leg"
    assert attr_dict.get("Depth With Door Open") == "50-1/4"
    assert uom_dict.get("Depth With Door Open") == "in"


# ---------------------------------------------------------------------------
# 5. Controlled Description Generation & Claim Validation
# ---------------------------------------------------------------------------
def test_invoice_description_constraints():
    """Verify INVOICE_DESC is strict uppercase and <= 40 characters."""
    builder = DescriptionBuilder()
    extractor = AttributeExtractor()

    attrs = extractor.extract_attributes("Dishwasher Leg Mounting 5 Wash Cycle 120V 15A Stainless Steel 50.25 in")
    inv = builder.build_invoice_description("Dishwasher", "FRIGIDAIRE®", "PDSH4816AF", attrs)

    assert len(inv) <= 40
    assert inv == inv.upper()
    assert "DISHWASHER" in inv
    assert "120V" in inv


def test_mobile_description_constraints():
    """Verify MOBILE_DESC is structured and <= 80 characters."""
    builder = DescriptionBuilder()
    extractor = AttributeExtractor()

    attrs = extractor.extract_attributes("Whirlpool Eco Series WDTS7024RZ Dishwasher Built-in Mounting Stainless Steel")
    mob = builder.build_mobile_description("Whirlpool Corporation", "Whirlpool®", "Dishwasher", "WDTS7024RZ", attrs)

    clean_mob = mob.strip('"')
    assert len(clean_mob) <= 80
    assert "Whirlpool" in clean_mob
    assert "WDTS7024RZ" in clean_mob


def test_long_description_anti_hallucination_check():
    """Verify LONG_DESC1 contains only verified factual claims and passes ClaimChecker."""
    builder = DescriptionBuilder()
    extractor = AttributeExtractor()

    attrs = extractor.extract_attributes("Whirlpool Eco Series WDTS7024RZ Dishwasher 120V 10A 41 dBA Stainless Steel")
    long_desc, claim_res = builder.build_long_description(
        brand="Whirlpool®",
        product_name="Dishwasher",
        mpn="WDTS7024RZ",
        attributes=attrs,
    )

    assert claim_res.valid is True
    assert not claim_res.has_unsupported_claims
    assert "Whirlpool®" in long_desc
    assert "120 V" in long_desc


# ---------------------------------------------------------------------------
# 6. Deep Category Specialization: Pipe & Tubing Fittings
# ---------------------------------------------------------------------------
def test_deep_category_fittings_enrichment():
    """Verify deep category enrichment for Pipe & Tubing Fittings."""
    enricher = FittingsDeepCategoryEnricher()

    assert enricher.is_fittings_product("NIBCO 1/2 in 90 deg Elbow Threaded Bronze Class 125") is True

    res = enricher.enrich_fitting(
        raw_mpn="90-ELB-12",
        raw_desc="NIBCO 1/2 in 90 deg Elbow Threaded Bronze Class 125",
        raw_manuf="NIBCO INC.",
    )

    assert res["identity"]["brand"] == "NIBCO®"
    assert res["taxonomy"]["classpath"] == "Plumbing>Pipe, Tubing & Fittings>Fittings"
    assert res["validation_status"] == "verified"

    attrs = {a["label"]: a["normalized_value"] for a in res["attributes"]}
    assert attrs.get("Fitting Type") == "90 deg Elbow"
    assert attrs.get("Fitting Size") == "1/2 in"
    assert attrs.get("Connection Type") == "Threaded"
    assert attrs.get("Material") == "Bronze"
    assert attrs.get("Pressure Class") == "Class 125"


# ---------------------------------------------------------------------------
# 7. End-to-End Pipeline & 200-Row Benchmark Evaluator
# ---------------------------------------------------------------------------
def test_end_to_end_pipeline_row():
    """Verify end-to-end pipeline execution and 252-column dictionary structure."""
    pipeline = EnrichmentPipeline()
    row = {
        "Mfg_Part_Num": "PDSH4816AF",
        "Part_Desc": "PDSH4816AF Dishwasher SS - Display Only",
        "E1_Brand": "-- Unbranded --",
        "Unilog_Brand": "-- No Unilog Brand --",
        "DIB_Brand": "-- No DIB Brand --",
        "Part_Manuf": "Appliance Dealers Cooperative (APPDE)",
    }

    res = pipeline.process_row(row)
    assert res["identity"]["manufacturer"] == "Rheem Manufacturing"
    assert res["identity"]["brand"] == "FRIGIDAIRE®"
    assert res["taxonomy"]["fine"] == "Dishwashers"
    assert res["validation"]["status"] == "verified"
    assert len(res["delivery_record"]) >= 250
    assert res["delivery_record"]["Product Image"].startswith("FRIGIDAIRE_")


def test_benchmark_evaluator_execution():
    """Verify 200-row benchmark evaluator runs cleanly and computes accuracy metrics."""
    csv_candidates = [
        r"C:\Users\Parikshith S\Downloads\Unihack_ Sample Dataset - Input.csv",
        r"C:\Users\Parikshith S\Downloads\Unihack_ Sample Dataset - Input (1).csv",
    ]
    input_path = next((p for p in csv_candidates if os.path.exists(p)), None)
    if not input_path:
        pytest.skip("Benchmark input dataset file not found in test environment.")

    evaluator = BenchmarkEvaluator(input_path)
    report = evaluator.run_benchmark(limit=50)

    assert report["dataset_info"]["total_rows_evaluated"] == 50
    assert report["metrics"]["manufacturer_normalization_accuracy"] >= 95.0
    assert report["metrics"]["brand_normalization_accuracy"] == 100.0
    assert report["metrics"]["zero_placeholder_leakage_rate"] == 100.0
    assert report["metrics"]["mpn_preservation_accuracy"] == 100.0
    assert report["metrics"]["invoice_desc_character_limit_compliance"] == 100.0
    assert report["metrics"]["mobile_desc_character_limit_compliance"] == 100.0
    assert report["metrics"]["long_desc_anti_hallucination_rate"] == 100.0
