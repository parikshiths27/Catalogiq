"""
Normalizer Services for CatalogIQ Enrichment Foundation.

Includes:
- PlaceholderCleaner (reusable across all fields)
- FractionNormalizer (Decimal_Fraction.xlsx lookup)
- UOMNormalizer (Master UOM Standards)
- ManufacturerBrandNormalizer (Canonical legal names, trademarks, and distributor resolution)
"""
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from app.services.enrichment.reference_loader import get_reference_loader, ReferenceDataLoader


class PlaceholderCleaner:
    """Detects and cleans placeholder / dummy values from input catalog feeds."""

    PLACEHOLDERS: Set[str] = {
        "-- unbranded --",
        "-- no unilog brand --",
        "-- no dib brand --",
        "-",
        "--",
        "---",
        "none",
        "null",
        "n/a",
        "na",
        "not available",
        "unbranded",
        "commodity - unbranded",
        "display only",
        "display",
        "ss - display only",
        "ss-display only",
        "unknown",
        "undefined",
        "nan",
    }

    @classmethod
    def is_placeholder(cls, value: Optional[str]) -> bool:
        """Returns True if the string is empty or matches a known placeholder."""
        if value is None:
            return True
        val = str(value).strip().lower()
        if not val or val in cls.PLACEHOLDERS:
            return True
        return False

    @classmethod
    def clean(cls, value: Optional[str]) -> Optional[str]:
        """Cleans a string, returning None if it is a placeholder or whitespace."""
        if cls.is_placeholder(value):
            return None
        return str(value).strip()

    @classmethod
    def clean_text_segment(cls, text: str) -> str:
        """Strips placeholder suffixes like '- Display Only' from descriptions."""
        if not text:
            return ""
        cleaned = re.sub(r"\s*-\s*Display\s*Only\b", "", text, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*-\s*Display\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*Display\s*Only\b", "", cleaned, flags=re.IGNORECASE)
        return cleaned.strip()


class FractionNormalizer:
    """Bidirectional exact decimal to fraction converter based on authoritative lookup."""

    def __init__(self, loader: Optional[ReferenceDataLoader] = None) -> None:
        self.loader = loader or get_reference_loader()

    def decimal_to_fraction(self, value: float) -> str:
        """Converts a float into fractional notation (e.g. 50.25 -> '50-1/4', 0.5 -> '1/2')."""
        whole = int(value)
        frac = round(value - whole, 5)

        if frac == 0:
            return str(whole)

        # Check exact lookup with small rounding tolerance
        for dec_val, frac_str in self.loader.decimal_to_fraction_map.items():
            if abs(frac - dec_val) < 0.005:
                if whole > 0:
                    return f"{whole}-{frac_str}"
                return frac_str

        # Fallback to standard 2 decimal places if non-standard fraction
        return f"{value:.2f}".rstrip("0").rstrip(".")

    def normalize_dimension_string(self, text: str) -> str:
        """Normalizes dimension patterns like '50.25 in' -> '50-1/4 in', '0.5\"' -> '1/2 in'."""
        if not text:
            return text

        # Replace decimal dimension followed by in/inch/\"
        def _replace_dec(match: re.Match) -> str:
            whole_num = float(match.group(1))
            frac_repr = self.decimal_to_fraction(whole_num)
            unit = match.group(2)
            unit_norm = "in" if unit in ('"', "''", "in", "inch", "inches") else unit
            return f"{frac_repr} {unit_norm}".strip()

        pattern = r"\b(\d+\.\d+)\s*(\"|''|in|inch|inches|ft|feet|mm|cm|m)\b"
        return re.sub(pattern, _replace_dec, text)


class UOMNormalizer:
    """Enforces approved UOM abbreviations according to master standards."""

    def __init__(self, loader: Optional[ReferenceDataLoader] = None) -> None:
        self.loader = loader or get_reference_loader()

    def normalize(self, raw_uom: Optional[str]) -> Optional[str]:
        """Maps raw UOM string to approved standard abbreviation."""
        if PlaceholderCleaner.is_placeholder(raw_uom):
            return None
        cleaned = str(raw_uom).strip()
        key = cleaned.lower()
        if key in self.loader.uom_alias_map:
            return self.loader.uom_alias_map[key]
        if cleaned in self.loader.approved_uoms:
            return cleaned
        return cleaned


class ManufacturerBrandNormalizer:
    """Resolves and normalizes messy manufacturer/distributor strings to canonical master entities."""

    def __init__(self, loader: Optional[ReferenceDataLoader] = None) -> None:
        self.loader = loader or get_reference_loader()

    def resolve(
        self,
        mfg_part_num: Optional[str],
        part_desc: Optional[str],
        part_manuf: Optional[str],
        e1_brand: Optional[str] = None,
        unilog_brand: Optional[str] = None,
        dib_brand: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Resolves manufacturer and brand against approved master.
        Returns:
            - canonical_manufacturer: str
            - canonical_brand: str
            - manufacturer_part_number: str
            - confidence: float
            - evidence: str
            - needs_review: bool
        """
        clean_mpn = (mfg_part_num or "").strip()
        clean_desc = PlaceholderCleaner.clean_text_segment(part_desc or "")
        clean_manuf_raw = PlaceholderCleaner.clean(part_manuf)
        
        # Check brand candidates
        brand_candidates = [
            PlaceholderCleaner.clean(e1_brand),
            PlaceholderCleaner.clean(unilog_brand),
            PlaceholderCleaner.clean(dib_brand),
        ]
        explicit_brand = next((b for b in brand_candidates if b), None)

        matched_mfr: Optional[str] = None
        matched_brand: Optional[str] = None
        match_evidence: List[str] = []
        confidence: float = 0.50

        # Step A: Check explicit brand if supplied and not placeholder
        if explicit_brand:
            brand_key = re.sub(r"[®™]", "", explicit_brand).strip().upper()
            if brand_key in self.loader.brands:
                matched_brand = self.loader.brands[brand_key]["canonical_brand"]
                matched_mfr = self.loader.brands[brand_key]["canonical_manufacturer"]
                match_evidence.append(f"matched explicit brand '{explicit_brand}' in Brand Master")
                confidence = 0.95

        # Step B: Check description tokens for well-known brands/series
        if not matched_brand and clean_desc:
            desc_upper = clean_desc.upper()
            # Prioritize longer brand names first
            sorted_brands = sorted(self.loader.brands.keys(), key=len, reverse=True)
            for b_key in sorted_brands:
                pattern = rf"\b{re.escape(b_key)}\b"
                if re.search(pattern, desc_upper):
                    matched_brand = self.loader.brands[b_key]["canonical_brand"]
                    matched_mfr = self.loader.brands[b_key]["canonical_manufacturer"]
                    match_evidence.append(f"extracted brand '{matched_brand}' from product description")
                    confidence = 0.92
                    break

        # Step C: Handle special distributor mappings where Part_Manuf is a co-op or distributor
        if clean_manuf_raw and not matched_mfr:
            manuf_upper = clean_manuf_raw.upper()
            if "APPDE" in manuf_upper or "APPLIANCE DEALERS" in manuf_upper:
                # Resolve based on product description / brand
                if clean_desc:
                    d_upper = clean_desc.upper()
                    if "FRIGIDAIRE" in d_upper or "PDSH" in d_upper or "GCFG" in d_upper or "PCFE" in d_upper or "PRFS" in d_upper or "FCM" in d_upper:
                        matched_mfr = "Rheem Manufacturing"
                        matched_brand = "FRIGIDAIRE®"
                    elif "WHIRLPOOL" in d_upper or "WDTS" in d_upper or "WSGS" in d_upper or "WMMS" in d_upper:
                        matched_mfr = "Whirlpool Corporation"
                        matched_brand = "Whirlpool®"
                    elif "KITCHENAID" in d_upper or "KITCHEN AID" in d_upper or "KDTS" in d_upper or "KDFM" in d_upper or "KDPS" in d_upper or "KSES" in d_upper or "KMMF" in d_upper:
                        matched_mfr = "Whirlpool Corporation"
                        matched_brand = "KitchenAid®"
                    elif "GE" in d_upper or "PDT" in d_upper or "PDD" in d_upper or "PTD" in d_upper or "PTW" in d_upper or "GCST" in d_upper or "PCWK" in d_upper or "PEP" in d_upper or "PS960" in d_upper or "PB900" in d_upper or "GDE" in d_upper or "GNE" in d_upper or "PAD28" in d_upper or "PGE29" in d_upper:
                        matched_mfr = "GE Appliances, a Haier company"
                        matched_brand = "GE®"
                    elif "CAFÉ" in d_upper or "CAFE" in d_upper or "C7CD" in d_upper or "C7CE" in d_upper or "CES700" in d_upper or "CHP90" in d_upper or "CVM517" in d_upper or "C9TM" in d_upper or "C90A" in d_upper or "CVE28" in d_upper:
                        matched_mfr = "GE Appliances, a Haier company"
                        matched_brand = "Café™"
                    elif "LG" in d_upper or "LDPH" in d_upper or "WKE100" in d_upper or "MSER2090" in d_upper or "LSEL6333" in d_upper or "LT18S" in d_upper:
                        matched_mfr = "LG Electronics USA, Inc."
                        matched_brand = "LG®"
                    elif "SPEED QUEEN" in d_upper or "DF700" in d_upper or "DR700" in d_upper or "DV200" in d_upper or "DC500" in d_upper or "FF701" in d_upper or "TR700" in d_upper or "TR500" in d_upper or "TC500" in d_upper or "TV200" in d_upper:
                        matched_mfr = "Alliance Laundry Systems LLC"
                        matched_brand = "Speed Queen®"
                    elif "BEKO" in d_upper or "WOSP" in d_upper:
                        matched_mfr = "Beko US, Inc."
                        matched_brand = "Beko®"
                    elif "ELEMENT" in d_upper or "ERFD" in d_upper or "EUF" in d_upper:
                        matched_mfr = "Element Electronics"
                        matched_brand = "Element®"
                    elif "SHARP" in d_upper or "SMC" in d_upper or "SMD" in d_upper:
                        matched_mfr = "Sharp Electronics Corporation"
                        matched_brand = "Sharp®"
                match_evidence.append(f"resolved cooperative distributor '{clean_manuf_raw}' via product family")
                confidence = 0.90
            elif "US LUMBER" in manuf_upper or "3073" in manuf_upper or "BOICA" in manuf_upper or "BOISE CASCADE" in manuf_upper:
                if clean_desc:
                    d_upper = clean_desc.upper()
                    if "TREX" in d_upper or "543" in d_upper or "1513" in d_upper or "1516" in d_upper:
                        matched_mfr = "Trex Company, Inc."
                        matched_brand = "Trex®"
                    elif "HARDIE" in d_upper or "891" in d_upper or "890" in d_upper:
                        matched_mfr = "James Hardie Building Products Inc."
                        matched_brand = "James Hardie®"
                    elif "SMARTSIDE" in d_upper or "25796" in d_upper or "40503" in d_upper or "25825" in d_upper or "25822" in d_upper:
                        matched_mfr = "Louisiana-Pacific Corporation"
                        matched_brand = "LP® SmartSide®"
                    elif "PROVIA" in d_upper or "15018" in d_upper:
                        matched_mfr = "ProVia LLC"
                        matched_brand = "ProVia®"
                match_evidence.append(f"resolved lumber distributor '{clean_manuf_raw}' via brand/series")
                confidence = 0.90
            elif "PARKSITE" in manuf_upper or "6151" in manuf_upper:
                matched_mfr = "The AZEK Company Inc."
                matched_brand = "TimberTech®"
                match_evidence.append(f"resolved Parksite distributor to '{matched_mfr}'")
                confidence = 0.92
            elif "PALDO" in manuf_upper or "PALMER DONAVIN" in manuf_upper:
                if clean_desc:
                    d_upper = clean_desc.upper()
                    if "WESTBURY" in d_upper or "DSI" in d_upper or "73272" in d_upper or "156436" in d_upper or "17395" in d_upper:
                        matched_mfr = "Digger Specialties, Inc."
                        matched_brand = "Westbury®"
                    elif "HENRY" in d_upper or "2733" in d_upper:
                        matched_mfr = "Henry Company"
                        matched_brand = "Henry®"
                    elif "OWENS CORNING" in d_upper or "OC " in d_upper or "1504345" in d_upper:
                        matched_mfr = "Owens Corning"
                        matched_brand = "Owens Corning®"
                match_evidence.append(f"resolved Palmer Donavin distributor to '{matched_mfr}'")
                confidence = 0.90

        # Step D: If brand/mfr still unresolved, analyze Part_Manuf string (which may have vendor codes)
        if clean_manuf_raw and not matched_mfr:
            # Strip trailing vendor code in parentheses like "(2435)", "(APPDE)", "(BOICA)", "(3073)"
            manuf_name_clean = re.sub(r"\s*\([A-Z0-9_-]+\)\s*$", "", clean_manuf_raw).strip()
            manuf_lower = manuf_name_clean.lower()

            # Direct match against master manufacturer aliases
            for mfr_name, mfr_data in self.loader.manufacturers.items():
                if any(alias in manuf_lower for alias in mfr_data["aliases"]) or manuf_lower in mfr_data["aliases"]:
                    if not matched_mfr:
                        matched_mfr = mfr_name
                    if not matched_brand and mfr_data["brands"]:
                        matched_brand = mfr_data["brands"][0]
                    match_evidence.append(f"matched manufacturer '{mfr_name}' via supplier string '{clean_manuf_raw}'")
                    confidence = max(confidence, 0.90)
                    break

        # Final Fallbacks
        if not matched_mfr:
            matched_mfr = clean_manuf_raw or "Unknown Manufacturer"
            confidence = 0.40
            needs_review = True
        else:
            needs_review = False

        if not matched_brand:
            matched_brand = matched_mfr
            needs_review = True

        evidence_str = "; ".join(match_evidence) if match_evidence else "default fallback resolution"

        return {
            "canonical_manufacturer": matched_mfr,
            "canonical_brand": matched_brand,
            "manufacturer_part_number": clean_mpn,
            "confidence": round(confidence, 2),
            "evidence": evidence_str,
            "needs_review": needs_review,
        }
