"""
Classpath-Constrained Attribute Extraction and LOV Normalization Service.

Extracts, standardizes, and validates attribute slots against category-specific LOV vocabularies.
Every extracted attribute retains:
- label
- raw_value
- normalized_value
- normalized_uom
- source
- evidence
- confidence
"""
import re
from typing import Any, Dict, List, Optional, Tuple
from app.services.enrichment.reference_loader import get_reference_loader, ReferenceDataLoader
from app.services.enrichment.normalizers import PlaceholderCleaner, FractionNormalizer, UOMNormalizer


class ExtractedAttribute:
    """Represents a single validated, confidence-scored product attribute."""

    def __init__(
        self,
        label: str,
        raw_value: str,
        normalized_value: str,
        normalized_uom: Optional[str] = None,
        source: str = "extracted_from_description",
        evidence: str = "",
        confidence: float = 0.90,
    ) -> None:
        self.label = label
        self.raw_value = raw_value
        self.normalized_value = normalized_value
        self.normalized_uom = normalized_uom
        self.source = source
        self.evidence = evidence
        self.confidence = confidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "raw_value": self.raw_value,
            "normalized_value": self.normalized_value,
            "normalized_uom": self.normalized_uom,
            "source": self.source,
            "evidence": self.evidence,
            "confidence": round(self.confidence, 2),
        }


class AttributeExtractor:
    """Extracts domain-constrained attributes from catalog records."""

    def __init__(self, loader: Optional[ReferenceDataLoader] = None) -> None:
        self.loader = loader or get_reference_loader()
        self.fraction_norm = FractionNormalizer(self.loader)
        self.uom_norm = UOMNormalizer(self.loader)

    def extract_attributes(
        self,
        part_desc: Optional[str],
        classpath: Optional[str] = None,
        raw_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[ExtractedAttribute]:
        """
        Extracts structured attributes constrained by Classpath and LOVs.
        """
        clean_desc = PlaceholderCleaner.clean_text_segment(part_desc or "")
        extracted: List[ExtractedAttribute] = []
        seen_labels: set = set()

        def _add_attr(label: str, raw_val: str, norm_val: str, uom: Optional[str] = None, conf: float = 0.90, ev: str = ""):
            if label not in seen_labels and norm_val:
                seen_labels.add(label)
                extracted.append(ExtractedAttribute(
                    label=label,
                    raw_value=raw_val,
                    normalized_value=norm_val,
                    normalized_uom=self.uom_norm.normalize(uom),
                    source="regex_lov_extractor",
                    evidence=ev or f"extracted '{raw_val}' matching pattern for {label}",
                    confidence=conf,
                ))

        # 1. Voltage Rating
        volt_m = re.search(r"\b(?:M)?(\d{2,3})\s*(?:V|volt|volts|VAC|v)\b|\bM(\d{2})\b", clean_desc, re.IGNORECASE)
        if volt_m:
            raw_v = volt_m.group(1) or volt_m.group(2)
            _add_attr("Voltage Rating", volt_m.group(0), raw_v, "V", 0.95, f"voltage spec matched: {volt_m.group(0)}")

        # 2. Chuck Size / Tool Collet Size
        chuck_m = re.search(r"\b(\d+/\d+|\d+(?:\.\d+)?)\s*(?:in|\"|inch|-inch)\s*(?:Hammer\s*Drill|Drill|Chuck|Driver|Keyless)\b", clean_desc, re.IGNORECASE)
        if chuck_m:
            raw_c = chuck_m.group(1)
            norm_c = self.fraction_norm.normalize_dimension_string(raw_c)
            _add_attr("Chuck Size", f"{raw_c} in", norm_c, "in", 0.95, f"chuck spec matched: {raw_c} in")

        # 3. Power Source
        if re.search(r"\bCordless\b", clean_desc, re.IGNORECASE):
            _add_attr("Power Source", "Cordless", "Cordless", None, 0.95, "power source matched: Cordless")
        elif re.search(r"\bCorded\b", clean_desc, re.IGNORECASE):
            _add_attr("Power Source", "Corded", "Corded", None, 0.95, "power source matched: Corded")

        # 4. Amperage Rating
        amp_m = re.search(r"\b(\d{1,3}(?:\.\d+)?)\s*(?:A|amp|amps|amperes)\b", clean_desc, re.IGNORECASE)
        if amp_m:
            _add_attr("Amperage Rating", amp_m.group(0), amp_m.group(1), "A", 0.95, f"amperage spec matched: {amp_m.group(0)}")

        # 5. Sound Level (dBA)
        dba_m = re.search(r"\b(\d{2})\s*(?:dBA|dba|dB)\b", clean_desc, re.IGNORECASE)
        if dba_m:
            _add_attr("Sound Level", dba_m.group(0), dba_m.group(1), "dBA", 0.95, f"sound rating matched: {dba_m.group(0)}")

        # 6. Number of Wash Cycles
        wash_m = re.search(r"\b(\d+)\s*[- ]*(?:Wash\s*Cycle|Cycle|wash cycle)\b", clean_desc, re.IGNORECASE)
        if wash_m:
            _add_attr("Number of Wash Cycles", wash_m.group(0), wash_m.group(1), None, 0.92, f"cycle count matched: {wash_m.group(0)}")

        # 7. Mounting Type
        if re.search(r"\bBuilt[- ]?in\b", clean_desc, re.IGNORECASE):
            _add_attr("Mounting Type", "Built-in", "Built-in", None, 0.92, "mounting spec matched: Built-in")
        elif re.search(r"\bLeg\s*Mounting\b|\bLeg\b", clean_desc, re.IGNORECASE) and "dish" in clean_desc.lower():
            _add_attr("Mounting Type", "Leg", "Leg", None, 0.92, "mounting spec matched: Leg")
        elif re.search(r"\bDeck\s*Mount\b", clean_desc, re.IGNORECASE):
            _add_attr("Mounting Type", "Deck Mount", "Deck Mount", None, 0.92, "mounting spec: Deck Mount")
        elif re.search(r"\bWall\s*Mount\b", clean_desc, re.IGNORECASE):
            _add_attr("Mounting Type", "Wall Mount", "Wall Mount", None, 0.92, "mounting spec: Wall Mount")

        # 6. Series & Model Names
        if re.search(r"\bProfessional\s*Series\b", clean_desc, re.IGNORECASE):
            _add_attr("Series", "Professional Series", "Professional Series", None, 0.95, "series matched: Professional Series")
        elif re.search(r"\bEco\s*Series\b", clean_desc, re.IGNORECASE):
            _add_attr("Series", "Eco Series", "Eco Series", None, 0.95, "series matched: Eco Series")
        elif re.search(r"\bTranscend\s*Lineage\b", clean_desc, re.IGNORECASE):
            _add_attr("Series", "Transcend Lineage", "Transcend Lineage", None, 0.95, "series matched: Transcend Lineage")
        elif re.search(r"\bEnhance\s*Naturals\b", clean_desc, re.IGNORECASE):
            _add_attr("Series", "Enhance Naturals", "Enhance Naturals", None, 0.95, "series matched: Enhance Naturals")
        elif re.search(r"\bEnhance\s*Basics\b", clean_desc, re.IGNORECASE):
            _add_attr("Series", "Enhance Basics", "Enhance Basics", None, 0.95, "series matched: Enhance Basics")
        elif re.search(r"\bSelect\s*2\.0\b", clean_desc, re.IGNORECASE):
            _add_attr("Series", "Select 2.0", "Select 2.0", None, 0.95, "series matched: Select 2.0")
        elif re.search(r"\bVintage\s*Azek\b", clean_desc, re.IGNORECASE):
            _add_attr("Series", "Vintage Azek", "Vintage Azek", None, 0.95, "series matched: Vintage Azek")
        elif re.search(r"\bLandmark\s*Azek\b", clean_desc, re.IGNORECASE):
            _add_attr("Series", "Landmark Azek", "Landmark Azek", None, 0.95, "series matched: Landmark Azek")
        elif re.search(r"\bHarvest\s*Azek\b", clean_desc, re.IGNORECASE):
            _add_attr("Series", "Harvest Azek", "Harvest Azek", None, 0.95, "series matched: Harvest Azek")

        # 7. Material & Finish / Color
        if re.search(r"\b(?:SS|SST|Stainless\s*Steel)\b", clean_desc, re.IGNORECASE):
            _add_attr("Material", "Stainless Steel", "Stainless Steel", None, 0.92, "material spec matched: Stainless Steel")
            if "dish" in clean_desc.lower() or "range" in clean_desc.lower():
                _add_attr("Color", "Stainless Steel", "Stainless Steel", None, 0.90, "color spec matched: Stainless Steel")
        elif re.search(r"\b(?:PVC|Composite|Aluminum|Brass|Bronze|Cast Iron)\b", clean_desc, re.IGNORECASE):
            mat_m = re.search(r"\b(PVC|Composite|Aluminum|Brass|Bronze|Cast Iron)\b", clean_desc, re.IGNORECASE)
            if mat_m:
                _add_attr("Material", mat_m.group(1), mat_m.group(1).title(), None, 0.92, f"material matched: {mat_m.group(1)}")

        # 8. Dimensions & Fractions (Depth with Door Open, Size, Length, Width, Thickness)
        depth_m = re.search(r"(\d+(?:\.\d+)?|\d+[-/]\d+(?:/\d+)?)\s*(?:in|\")\s*Depth\s*With\s*Door\s*Open", clean_desc, re.IGNORECASE)
        if depth_m:
            raw_d = depth_m.group(1)
            try:
                norm_d = self.fraction_norm.decimal_to_fraction(float(raw_d))
            except ValueError:
                norm_d = self.fraction_norm.normalize_dimension_string(raw_d)
            _add_attr("Depth With Door Open", raw_d, norm_d, "in", 0.95, f"door depth matched: {raw_d}")

        # Dimensional patterns like "24 in W x 24-1/4 in D" or "33-7/16 in H x 23-7/8 in W"
        size_m = re.search(r"(\d+(?:[-/]\d+)?(?:\.\d+)?\s*in\s*[HWD](?:\s*x\s*\d+(?:[-/]\d+)?(?:\.\d+)?\s*in\s*[HWD])+)", clean_desc, re.IGNORECASE)
        if size_m:
            raw_s = size_m.group(1)
            norm_s = self.fraction_norm.normalize_dimension_string(raw_s)
            _add_attr("Size", raw_s, norm_s, None, 0.92, f"size dimension matched: {raw_s}")

        # Board / lumber / abrasive dimensions: "1x6-16'", "1/2""x18""", "9""", "5""x.045""x7/8"""
        dim_3 = re.search(r"(\d+(?:[-/]\d+)?)\"x(\.\d+|\d+(?:[-/]\d+)?)\"x(\d+/\d+|\d+)\"", clean_desc)
        if dim_3:
            _add_attr("Diameter", dim_3.group(1), dim_3.group(1), "in", 0.95, "extracted disc diameter")
            _add_attr("Thickness", dim_3.group(2), dim_3.group(2), "in", 0.95, "extracted disc thickness")
            _add_attr("Arbor Size", dim_3.group(3), dim_3.group(3), "in", 0.95, "extracted disc arbor size")

        deck_m = re.search(r"(\d+(?:nx|x)\d+)-(\d+)'", clean_desc)
        if deck_m:
            _add_attr("Length", f"{deck_m.group(2)} ft", deck_m.group(2), "ft", 0.95, "extracted decking length")

        # 9. Edge Profile
        if re.search(r"\bSq(?:uare)?\s*Edge\b", clean_desc, re.IGNORECASE):
            _add_attr("Edge Profile", "Sq Edge", "Square Edge", None, 0.95, "edge profile matched: Square Edge")
        elif re.search(r"\bGrooved\b", clean_desc, re.IGNORECASE):
            _add_attr("Edge Profile", "Grooved", "Grooved", None, 0.95, "edge profile matched: Grooved")

        # 10. Grit & Package Quantity
        grit_m = re.search(r"\bP?(\d{2,4})\s*Grit\b|\bP(\d{2,4})\b", clean_desc, re.IGNORECASE)
        if grit_m:
            val = grit_m.group(1) or grit_m.group(2)
            _add_attr("Grit", f"P{val}", f"P{val}", None, 0.92, f"grit matched: P{val}")

        pack_m = re.search(r"\b(\d+)\s*(?:pc|pk|Pack|Disc/Box|CT)\b", clean_desc, re.IGNORECASE)
        if pack_m:
            _add_attr("Package Quantity", pack_m.group(0), pack_m.group(1), "PK", 0.90, f"package quantity matched: {pack_m.group(0)}")

        # 11. Application (Abrasives / Saws / Fittings)
        if re.search(r"\bMetal\s*Cut[- ]?Off\b|\bMetal\b", clean_desc, re.IGNORECASE) and "disc" in clean_desc.lower():
            _add_attr("Application", "Metal", "Metal", None, 0.92, "application matched: Metal")
        elif re.search(r"\bMasonry\b", clean_desc, re.IGNORECASE):
            _add_attr("Application", "Masonry", "Masonry", None, 0.92, "application matched: Masonry")

        # 12. Deep Category LOV extraction (Fittings / Faucets)
        if classpath and "Fittings" in classpath:
            fit_type_m = re.search(r"\b(90 deg Elbow|45 deg Elbow|Elbow|Tee|Coupling|Adapter|Reducer|Bushing|Union|Flange|Cap|Plug|Nipple)\b", clean_desc, re.IGNORECASE)
            if fit_type_m:
                _add_attr("Fitting Type", fit_type_m.group(1), fit_type_m.group(1).title(), None, 0.95, "matched fitting LOV")
            conn_m = re.search(r"\b(NPT|Threaded|Socket Weld|Butt Weld|Soldered|Press-to-Connect|Push-Fit|Flanged|Compression)\b", clean_desc, re.IGNORECASE)
            if conn_m:
                _add_attr("Connection Type", conn_m.group(1), conn_m.group(1), None, 0.95, "matched connection LOV")
        elif classpath and "Faucets" in classpath:
            faucet_type_m = re.search(r"\b(Kitchen Faucet|Lavatory Faucet|Bar Faucet|Utility Faucet|Vessel Faucet)\b", clean_desc, re.IGNORECASE)
            if faucet_type_m:
                _add_attr("Faucet Type", faucet_type_m.group(1), faucet_type_m.group(1).title(), None, 0.95, "matched faucet LOV")
            gpm_m = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:gpm|GPM)\b", clean_desc, re.IGNORECASE)
            if gpm_m:
                _add_attr("Flow Rate", gpm_m.group(0), gpm_m.group(1), "gpm", 0.95, "matched flow rate LOV")

        return extracted

    def format_delivery_attribute_slots(self, attributes: List[ExtractedAttribute]) -> Dict[str, Any]:
        """
        Formats extracted attributes into ATTRIBUTE_LABEL 1..50, ATTRIBUTE_VALUE 1..50, ATTRIBUTE_UOM 1..50.
        """
        slots: Dict[str, Any] = {}
        for i in range(1, 51):
            slots[f"ATTRIBUTE_LABEL {i}"] = ""
            slots[f"ATTRIBUTE_VALUE {i}"] = ""
            slots[f"ATTRIBUTE_UOM {i}"] = ""

        for i, attr in enumerate(attributes[:50]):
            idx = i + 1
            slots[f"ATTRIBUTE_LABEL {idx}"] = attr.label
            slots[f"ATTRIBUTE_VALUE {idx}"] = attr.normalized_value
            slots[f"ATTRIBUTE_UOM {idx}"] = attr.normalized_uom or ""

        return slots
