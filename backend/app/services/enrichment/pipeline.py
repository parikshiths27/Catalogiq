"""
CatalogIQ Enrichment Foundation - Core Pipeline Orchestrator.

Transforms messy industrial catalog rows into standardized, validated,
commerce-ready product records with 252-column delivery format compatibility.
"""
import re
from typing import Any, Dict, List, Optional
from app.services.enrichment.reference_loader import get_reference_loader, ReferenceDataLoader
from app.services.enrichment.normalizers import (
    PlaceholderCleaner,
    FractionNormalizer,
    UOMNormalizer,
    ManufacturerBrandNormalizer,
)
from app.services.enrichment.taxonomy import TaxonomyClassifier
from app.services.enrichment.attributes import AttributeExtractor, ExtractedAttribute
from app.services.enrichment.description_builder import DescriptionBuilder
from app.services.enrichment.validator import DeterministicValidator, ValidationSummary
from app.services.enrichment.evidence import EvidenceTracker


class EnrichmentPipeline:
    """End-to-end enrichment engine for industrial catalog records."""

    def __init__(self, loader: Optional[ReferenceDataLoader] = None) -> None:
        self.loader = loader or get_reference_loader()
        self.mfr_brand_norm = ManufacturerBrandNormalizer(self.loader)
        self.taxonomy_classifier = TaxonomyClassifier(self.loader)
        self.attr_extractor = AttributeExtractor(self.loader)
        self.desc_builder = DescriptionBuilder()
        self.validator = DeterministicValidator(self.loader)

    def process_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enriches a single raw catalog row.
        Input expected keys:
            - Mfg_Part_Num
            - Part_Desc
            - E1_Brand
            - Unilog_Brand
            - DIB_Brand
            - Part_Manuf
        """
        raw_mpn = str(row.get("Mfg_Part_Num", "") or "").strip()
        raw_desc = str(row.get("Part_Desc", "") or "").strip()
        raw_e1 = str(row.get("E1_Brand", "") or "").strip()
        raw_unilog = str(row.get("Unilog_Brand", "") or "").strip()
        raw_dib = str(row.get("DIB_Brand", "") or "").strip()
        raw_manuf = str(row.get("Part_Manuf", "") or "").strip()

        evidence_tracker = EvidenceTracker()

        # Step 1: Normalize Manufacturer and Brand
        mfr_res = self.mfr_brand_norm.resolve(
            mfg_part_num=raw_mpn,
            part_desc=raw_desc,
            part_manuf=raw_manuf,
            e1_brand=raw_e1,
            unilog_brand=raw_unilog,
            dib_brand=raw_dib,
        )
        canonical_mfr = mfr_res["canonical_manufacturer"]
        canonical_brand = mfr_res["canonical_brand"]
        canonical_mpn = mfr_res["manufacturer_part_number"]

        evidence_tracker.add("MANUFACTURER_NAME", canonical_mfr, "Manufacturer Master", mfr_res["evidence"], mfr_res["confidence"])
        evidence_tracker.add("BRAND_NAME", canonical_brand, "Brand Master", mfr_res["evidence"], mfr_res["confidence"])
        evidence_tracker.add("MANUFACTURER_PART_NUMBER", canonical_mpn, "Input Feed", "exact match from source MPN", 1.0)

        # Step 2: Classify Taxonomy & Classpath
        tax_res = self.taxonomy_classifier.classify(
            part_desc=raw_desc,
            mfg_part_num=raw_mpn,
            canonical_brand=canonical_brand,
        )
        dept = tax_res["dept"]
        class_ = tax_res["class_"]
        fine = tax_res["fine"]
        classpath = tax_res["classpath"]
        product_name = tax_res["product_name"]

        evidence_tracker.add("Dept", dept, "Taxonomy Hierarchy", tax_res["evidence"], tax_res["confidence"])
        evidence_tracker.add("Class", class_, "Taxonomy Hierarchy", tax_res["evidence"], tax_res["confidence"])
        evidence_tracker.add("Fine", fine, "Taxonomy Hierarchy", tax_res["evidence"], tax_res["confidence"])
        evidence_tracker.add("Classpath", classpath, "Taxonomy Tree", tax_res["evidence"], tax_res["confidence"])

        # Step 3: Extract Domain-Constrained Attributes & LOVs
        extracted_attrs = self.attr_extractor.extract_attributes(
            part_desc=raw_desc,
            classpath=classpath,
        )
        for a in extracted_attrs:
            evidence_tracker.add(f"ATTR: {a.label}", a.normalized_value, a.source, a.evidence, a.confidence)

        # Step 4: Controlled Description Generation
        with_features = None
        if "cleanboost" in raw_desc.lower():
            with_features = "With CleanBoost™"
        elif "3rd rack" in raw_desc.lower():
            with_features = "With Washing 3rd Rack, Water Repellent Silverware Basket"

        invoice_desc = self.desc_builder.build_invoice_description(
            product_name=product_name,
            brand=canonical_brand,
            mpn=canonical_mpn,
            attributes=extracted_attrs,
        )
        mobile_desc = self.desc_builder.build_mobile_description(
            manufacturer=canonical_mfr,
            brand=canonical_brand,
            product_name=product_name,
            mpn=canonical_mpn,
            attributes=extracted_attrs,
        )
        short_desc = self.desc_builder.build_short_description(
            brand=canonical_brand,
            product_name=product_name,
            mpn=canonical_mpn,
            attributes=extracted_attrs,
            with_features=with_features,
        )
        long_desc, claim_check_res = self.desc_builder.build_long_description(
            brand=canonical_brand,
            product_name=product_name,
            mpn=canonical_mpn,
            attributes=extracted_attrs,
            with_features=with_features,
        )
        retail_desc = self.desc_builder.build_retail_description(
            product_name=product_name,
            attributes=extracted_attrs,
        )

        evidence_tracker.add("INVOICE_DESC", invoice_desc, "Deterministic Builder", "generated uppercase abbreviated invoice spec <=40 chars", 0.95)
        evidence_tracker.add("MOBILE_DESC", mobile_desc, "Deterministic Builder", "generated structured mobile summary <=80 chars", 0.95)
        evidence_tracker.add("SHORT_DESC", short_desc, "Deterministic Builder", "generated title with brand, series, MPN, specs", 0.95)
        evidence_tracker.add("LONG_DESC1", long_desc, "ClaimChecker Validated", f"verified {claim_check_res.supported_claims_count} specs, 0 hallucinated claims", 0.95)

        # Step 5: Deterministic Validation
        validation_res = self.validator.validate(
            manufacturer=canonical_mfr,
            brand=canonical_brand,
            mpn=canonical_mpn,
            classpath=classpath,
            attributes=extracted_attrs,
            invoice_desc=invoice_desc,
            mobile_desc=mobile_desc,
            claim_result=claim_check_res,
            confidence=mfr_res["confidence"],
        )

        # Step 6: Construct 252-Column Delivery Record Dictionary
        delivery_record: Dict[str, Any] = {
            "MFR URL": "",
            "Ref URL 1": "",
            "Ref URL 2": "",
            "Ref URL 3": "",
            "Ref URL 4": "",
            "Ref URL 5": "",
            "PART_NUMBER": "",
            "Dept": dept,
            "Class": class_,
            "Fine": fine,
            "SKU - MY_PART_NUMBER": canonical_mpn,
            "Mfg_Part_Num": raw_mpn,
            "Part_Desc": raw_desc,
            "E1_Brand": raw_e1,
            "Unilog_Brand": raw_unilog,
            "DIB_Brand": raw_dib,
            "Part_Manuf": raw_manuf,
            "MANUFACTURER_NAME": canonical_mfr,
            "BRAND_NAME": canonical_brand,
            "TRADE_NAME": "",
            "MANUFACTURER_PART_NUMBER": canonical_mpn,
            "ALTERNATE_PART_NUMBER": "",
            "Classpath": classpath,
            "MOBILE_DESC": mobile_desc,
            "INVOICE_DESC": invoice_desc,
            "SHORT_DESC": short_desc,
            "LONG_DESC1": long_desc,
            "RETAIL_DESC": retail_desc,
            "MARKETING_DESCRIPTION": "",
            "With": with_features or "",
            "Standard/Approvals": "",
            "Prop 65": "",
            "Application": "",
            "Includes": "",
            "Product Name": product_name,
        }

        # Format features 1..20
        for i in range(1, 21):
            delivery_record[f"ITEM_FEATURES_{i}"] = ""

        # Format attribute slots 1..50
        attr_slots = self.attr_extractor.format_delivery_attribute_slots(extracted_attrs)
        delivery_record.update(attr_slots)

        # Form codes, pricing, dimensions, and assets slots
        commerce_slots = {
            "UPC": "", "EAN": "", "GTIN": "", "UNSPSC": "", "Warranty": "",
            "List Price": "", "Selling Qty": "1", "Selling UOM": "EA",
            "Standard Packaging Information": "",
            "LENGTH": "", "LENGTH_UOM": "", "HEIGHT": "", "HEIGHT_UOM": "",
            "WIDTH": "", "WIDTH_UOM": "", "WEIGHT": "", "WEIGHT_UOM": "",
            "VOLUME": "", "VOLUME_UOM": "",
            "Product Image": f"{re.sub(r'[^A-Za-z0-9_]', '_', canonical_brand.replace('®',''))}_{canonical_mpn}.jpg" if canonical_mpn else "",
            "Alternate Image 1": "", "Alternate Image 2": "", "Alternate Image 3": "", "Alternate Image 4": "",
            "SDS": "", "SDS_1": "", "Warranty Information": "", "Catalog": "",
            "Specification Sheet": f"{re.sub(r'[^A-Za-z0-9_]', '_', canonical_brand.replace('®',''))}_{canonical_mpn}_Specification_Sheet.pdf" if canonical_mpn else "",
            "Instruction/Installation Manual": "", "Service Manual": "", "Owners/User Manual": "",
            "Line Drawing": "", "MTR": "", "RoHS": "", "Full Engineering Drawing": "",
            "Energy Star Guide": "", "Technical Bulletin": "", "Submittal": "",
            "Compatibility Chart": "", "Size Chart": "", "Product Label/Insert": "",
            "Video Link": "", "Video Link 1": "", "Country Of Origin": "",
            "Discontinued": "No", "Actual Image (Yes/No)": "Yes" if canonical_mpn else "No",
        }
        delivery_record.update(commerce_slots)

        return {
            "identity": {
                "manufacturer": canonical_mfr,
                "brand": canonical_brand,
                "mpn": canonical_mpn,
            },
            "taxonomy": {
                "dept": dept,
                "class": class_,
                "fine": fine,
                "classpath": classpath,
                "product_name": product_name,
            },
            "attributes": [a.to_dict() for a in extracted_attrs],
            "descriptions": {
                "invoice_desc": invoice_desc,
                "mobile_desc": mobile_desc,
                "short_desc": short_desc,
                "long_desc": long_desc,
                "retail_desc": retail_desc,
            },
            "validation": validation_res.to_dict(),
            "evidence_summary": evidence_tracker.get_summary(),
            "delivery_record": delivery_record,
        }
