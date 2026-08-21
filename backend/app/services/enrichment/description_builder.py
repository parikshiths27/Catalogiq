"""
Controlled Description Builder for CatalogIQ Enrichment Foundation.

Implements deterministic construction formulas aligned with Unilog Content Guidelines:
- INVOICE_DESC (uppercase, standard abbreviations, max 40 chars)
- MOBILE_DESC (concise, structured comma list, 60-80 chars)
- SHORT_DESC / PRODUCT TITLE (Brand® + MPN + Name + Verified Specs)
- LONG_DESC1 (Structured sentence linking verified attributes, verified by ClaimChecker)
- RETAIL_DESC (Customer-facing catalog title)
"""
import re
from typing import Any, Dict, List, Optional, Tuple
from app.services.enrichment.normalizers import PlaceholderCleaner, FractionNormalizer
from app.services.enrichment.attributes import ExtractedAttribute
from app.services.claim_checker import ClaimChecker, ClaimCheckResult
from app.services.llm.base import CommerceEnrichment


class DescriptionBuilder:
    """Constructs validated commerce descriptions from normalized product records."""

    def __init__(self) -> None:
        self.fraction_norm = FractionNormalizer()
        self.claim_checker = ClaimChecker()

    def _get_spec_tokens(self, attr_dict: Dict[str, str]) -> Dict[str, str]:
        """Extracts and standardizes key attribute tokens."""
        return {
            "diameter": attr_dict.get("Diameter", ""),
            "thickness": attr_dict.get("Thickness", ""),
            "arbor": attr_dict.get("Arbor Size", ""),
            "grit": attr_dict.get("Grit", ""),
            "pack": attr_dict.get("Package Quantity", ""),
            "application": attr_dict.get("Application", ""),
            "material": attr_dict.get("Material", ""),
            "color": attr_dict.get("Color", ""),
            "series": attr_dict.get("Series", ""),
            "volt": attr_dict.get("Voltage Rating", ""),
            "amp": attr_dict.get("Amperage Rating", ""),
            "mounting": attr_dict.get("Mounting Type", ""),
            "cycles": attr_dict.get("Number of Wash Cycles", ""),
            "sound": attr_dict.get("Sound Level", ""),
            "depth": attr_dict.get("Depth With Door Open", ""),
            "length": attr_dict.get("Length", ""),
            "width": attr_dict.get("Width", ""),
            "edge": attr_dict.get("Edge Profile", ""),
            "fitting_type": attr_dict.get("Fitting Type", ""),
            "conn_type": attr_dict.get("Connection Type", ""),
            "faucet_type": attr_dict.get("Faucet Type", ""),
            "flow_rate": attr_dict.get("Flow Rate", ""),
            "chuck": attr_dict.get("Chuck Size", ""),
            "drive": attr_dict.get("Drive Size", ""),
            "teeth": attr_dict.get("Number of Teeth", ""),
            "tooth_mat": attr_dict.get("Tooth Material", ""),
        }

    def build_invoice_description(
        self,
        product_name: str,
        brand: str,
        mpn: str,
        attributes: List[ExtractedAttribute],
    ) -> str:
        """
        Generates strict uppercase, abbreviated invoice description <= 40 chars.
        Formula: [PRODUCT] [KEY SPECS / DIMENSIONS] [MATERIAL / APP] [ELECTRICAL / PACK]
        """
        attr_dict = {a.label: a.normalized_value for a in attributes}
        specs = self._get_spec_tokens(attr_dict)
        tokens: List[str] = []

        p_upper = (product_name or "").upper().strip()

        # Category 1: Abrasives & Cut-off Discs
        if "CUT-OFF" in p_upper or "DISC" in p_upper or "WHEEL" in p_upper:
            tokens.append("CUT OFF DISC")
            if specs["diameter"]:
                tokens.append(f"{specs['diameter']}IN")
            if specs["thickness"]:
                tokens.append(f"{specs['thickness']}IN")
            if specs["arbor"]:
                tokens.append(f"{specs['arbor']}IN")
            if specs["application"] and "metal" in specs["application"].lower():
                tokens.append("MTL")
            elif specs["application"]:
                tokens.append(specs["application"][:5].upper())

        elif "SANDING" in p_upper or "BELT" in p_upper:
            tokens.append("SANDING BELT")
            if specs["diameter"] and specs["thickness"]:
                tokens.append(f"{specs['diameter']}X{specs['thickness']}")
            if specs["grit"]:
                tokens.append(f"P{specs['grit'].replace('P', '')}")
            if specs["pack"]:
                tokens.append(f"{specs['pack']}PK")

        # Category 2: Saw Blades
        elif "SAW BLADE" in p_upper or "BLADE" in p_upper:
            tokens.append("SAW BLADE")
            if specs["diameter"]:
                tokens.append(f"{specs['diameter']}IN")
            if specs["teeth"]:
                tokens.append(f"{specs['teeth']}T")
            if specs["tooth_mat"]:
                tokens.append("CRB" if "carbide" in specs["tooth_mat"].lower() else specs["tooth_mat"][:3].upper())
            if specs["application"]:
                tokens.append(specs["application"][:6].upper())

        # Category 3: Power Tools
        elif "DRILL" in p_upper or "DRIVER" in p_upper:
            tokens.append("DRILL/DRIVER")
            if specs["volt"]:
                tokens.append(f"{specs['volt']}V")
            if specs["chuck"]:
                tokens.append(f"{specs['chuck']}IN")
            if specs["drive"]:
                tokens.append(f"{specs['drive']}")

        elif "SAW" in p_upper:
            tokens.append("CIRC SAW")
            if specs["diameter"]:
                tokens.append(f"{specs['diameter']}IN")
            if specs["volt"]:
                tokens.append(f"{specs['volt']}V")

        # Category 4: Decking & Railing
        elif "DECKING" in p_upper or "FASCIA" in p_upper:
            tokens.append("DECKING")
            if specs["length"]:
                tokens.append(f"{specs['length']}FT")
            if specs["edge"] and "sq" in specs["edge"].lower():
                tokens.append("SQ EDGE")
            elif specs["edge"]:
                tokens.append("GROOVE")
            if specs["material"]:
                tokens.append("COMP" if "comp" in specs["material"].lower() else specs["material"][:4].upper())

        # Category 5: Plumbing Fittings & Faucets
        elif "FITTING" in p_upper or "ELBOW" in p_upper or "TEE" in p_upper:
            tokens.append(specs["fitting_type"].upper() if specs["fitting_type"] else "FITTING")
            if specs["diameter"]:
                tokens.append(f"{specs['diameter']}IN")
            if specs["material"]:
                tokens.append("PVC" if "pvc" in specs["material"].lower() else specs["material"][:4].upper())
            if specs["conn_type"]:
                tokens.append(specs["conn_type"][:4].upper())

        elif "FAUCET" in p_upper:
            tokens.append("FAUCET")
            if specs["faucet_type"]:
                tokens.append(specs["faucet_type"][:8].upper())
            if specs["flow_rate"]:
                tokens.append(f"{specs['flow_rate']}GPM")
            if specs["color"]:
                tokens.append("CHR" if "chrome" in specs["color"].lower() else specs["color"][:3].upper())

        # Category 6: Appliances
        elif "DISHWASHER" in p_upper:
            tokens.append("DISHWASHER")
            if specs["mounting"]:
                tokens.append("BLTLN" if "built" in specs["mounting"].lower() else "LEG")
            if specs["cycles"]:
                tokens.append(f"{specs['cycles']}CYC")
            if specs["material"] and "stainless" in specs["material"].lower():
                tokens.append("SST")
            if specs["volt"]:
                tokens.append(f"{specs['volt']}V")

        else:
            if specs["diameter"] and (specs["thickness"] or specs["arbor"]):
                tokens.append("CUT OFF DISC")
                if specs["diameter"]:
                    tokens.append(f"{specs['diameter']}IN")
                if specs["thickness"]:
                    tokens.append(f"{specs['thickness']}IN")
                if specs["arbor"]:
                    tokens.append(f"{specs['arbor']}IN")
                if specs["application"] and "metal" in specs["application"].lower():
                    tokens.append("MTL")
            elif specs["diameter"]:
                tokens.append(f"DISC {specs['diameter']}IN")
            elif specs["volt"]:
                tokens.append(f"TOOL {specs['volt']}V")
            else:
                first_word = p_upper.split()[0] if p_upper and p_upper not in ("INDUSTRIAL PRODUCT", "PRODUCT", "UNKNOWN", "UNCATEGORIZED") else (mpn.split("-")[0] if mpn else "SPEC")
                tokens.append(first_word)
                if specs["material"]:
                    tokens.append(specs["material"][:4].upper())

        invoice_str = " ".join(t for t in tokens if t).upper().strip()

        # Enforce max 40 characters limit cleanly
        if len(invoice_str) > 40:
            parts = invoice_str.split()
            while len(" ".join(parts)) > 40 and len(parts) > 1:
                parts.pop()
            invoice_str = " ".join(parts)[:40]

        return invoice_str or (mpn[:40].upper() if mpn else "PRODUCT SPEC")

    def build_mobile_description(
        self,
        manufacturer: str,
        brand: str,
        product_name: str,
        mpn: str,
        attributes: List[ExtractedAttribute],
    ) -> str:
        """
        Generates structured comma-separated mobile description (60-80 chars).
        Format: "[Brand], [Dimensions/Specs] [Product Name], [MPN]"
        """
        clean_brand = re.sub(r"[®™]", "", brand or "").strip()
        clean_mfr = re.sub(r"[®™]", "", manufacturer or "").strip()

        if not clean_brand or clean_brand.lower() == "unbranded":
            brand_token = clean_mfr.split()[0] if clean_mfr else "Universal"
        else:
            brand_token = clean_brand

        attr_dict = {a.label: a.normalized_value for a in attributes}
        specs = self._get_spec_tokens(attr_dict)

        # Build spec modifier
        spec_parts: List[str] = []
        if specs["diameter"] and specs["thickness"] and specs["arbor"]:
            spec_parts.append(f"{specs['diameter']} in x {specs['thickness']} in x {specs['arbor']} in")
        elif specs["diameter"] and specs["thickness"]:
            spec_parts.append(f"{specs['diameter']} in x {specs['thickness']} in")
        elif specs["diameter"]:
            spec_parts.append(f"{specs['diameter']} in")

        if specs["grit"]:
            spec_parts.append(f"P{specs['grit'].replace('P', '')}")
        if specs["teeth"]:
            spec_parts.append(f"{specs['teeth']}-Tooth")
        if specs["application"]:
            spec_parts.append(specs["application"])
        if specs["length"]:
            spec_parts.append(f"{specs['length']} ft")
        if specs["volt"]:
            spec_parts.append(f"{specs['volt']}V")

        clean_pname = product_name
        if clean_pname.lower() in ("industrial product", "product", "uncategorized"):
            if "cut" in spec_parts or "disc" in clean_pname.lower() or specs["diameter"]:
                clean_pname = "Cut-Off Disc"
            else:
                clean_pname = "Specification Component"

        spec_str = " ".join(spec_parts[:2]).strip()
        desc_core = f"{spec_str} {clean_pname}".strip() if spec_str else clean_pname

        parts: List[str] = [brand_token, desc_core]
        if mpn:
            parts.append(mpn)

        mobile_desc = ", ".join(p for p in parts if p)

        # Fit within 60-80 chars target
        if len(mobile_desc) > 80:
            mobile_desc = f"{brand_token}, {clean_pname}, {mpn}"[:80]

        return mobile_desc

    def build_short_description(
        self,
        brand: str,
        product_name: str,
        mpn: str,
        attributes: List[ExtractedAttribute],
        with_features: Optional[str] = None,
    ) -> str:
        """
        Generates standard short description / Product Title.
        Format: "Brand® [MPN] [Specs] [Product Name] [With Features]"
        """
        clean_brand = brand or "Universal"
        attr_dict = {a.label: a.normalized_value for a in attributes}
        specs = self._get_spec_tokens(attr_dict)

        spec_parts: List[str] = []
        if specs["diameter"] and specs["thickness"] and specs["arbor"]:
            spec_parts.append(f"{specs['diameter']} in x {specs['thickness']} in x {specs['arbor']} in")
        elif specs["diameter"]:
            spec_parts.append(f"{specs['diameter']} in")

        if specs["grit"]:
            spec_parts.append(f"P{specs['grit'].replace('P', '')} Grit")
        if specs["teeth"]:
            spec_parts.append(f"{specs['teeth']}-Tooth")
        if specs["application"]:
            spec_parts.append(specs["application"])
        if specs["material"] and specs["material"] not in ("Steel", "Composite"):
            spec_parts.append(specs["material"])
        if specs["volt"]:
            spec_parts.append(f"{specs['volt']}V")

        clean_pname = product_name
        if clean_pname.lower() in ("industrial product", "product", "uncategorized"):
            clean_pname = "Cut-Off Disc" if specs["diameter"] else "Hardware Product"

        title_components = [clean_brand]
        if mpn:
            title_components.append(mpn)
        if spec_parts:
            title_components.append(" ".join(spec_parts[:2]))
        title_components.append(clean_pname)

        if with_features:
            title_components.append(with_features)

        return " ".join(c for c in title_components if c).strip()

    def build_long_description(
        self,
        brand: str,
        product_name: str,
        mpn: str,
        attributes: List[ExtractedAttribute],
        with_features: Optional[str] = None,
    ) -> Tuple[str, ClaimCheckResult]:
        """
        Constructs comprehensive long description from verified attributes and validates via ClaimChecker.
        """
        attr_dict = {a.label: a.normalized_value for a in attributes}
        specs = self._get_spec_tokens(attr_dict)

        clean_pname = product_name
        if clean_pname.lower() in ("industrial product", "product", "uncategorized"):
            clean_pname = "Cut-Off Disc" if specs["diameter"] else "Component"

        lead = f"{brand} {mpn} {clean_pname}".strip()
        if with_features:
            lead += f" {with_features}"

        clauses: List[str] = []
        if specs["diameter"]:
            clauses.append(f"{specs['diameter']} in Diameter")
        if specs["thickness"]:
            clauses.append(f"{specs['thickness']} in Thickness")
        if specs["arbor"]:
            clauses.append(f"{specs['arbor']} in Arbor Size")
        if specs["grit"]:
            clauses.append(f"Grit {specs['grit']}")
        if specs["teeth"]:
            clauses.append(f"{specs['teeth']} Teeth")
        if specs["application"]:
            clauses.append(f"Engineered for {specs['application']} Applications")
        if specs["volt"]:
            clauses.append(f"{specs['volt']} V")
        if specs["amp"]:
            clauses.append(f"{specs['amp']} A")
        if specs["material"]:
            clauses.append(f"{specs['material']} Construction")
        if specs["color"]:
            clauses.append(f"{specs['color']} Finish")
        if specs["mounting"]:
            clauses.append(f"{specs['mounting']} Mounting")
        if specs["cycles"]:
            clauses.append(f"{specs['cycles']} Wash Cycles")
        if specs["sound"]:
            clauses.append(f"{specs['sound']} dBA Sound Level")
        if specs["length"]:
            clauses.append(f"{specs['length']} ft Length")
        if specs["edge"]:
            clauses.append(f"{specs['edge']} Profile")
        if specs["fitting_type"]:
            clauses.append(f"{specs['fitting_type']} Fitting")
        if specs["conn_type"]:
            clauses.append(f"{specs['conn_type']} Connection")
        if specs["flow_rate"]:
            clauses.append(f"{specs['flow_rate']} gpm Flow Rate")

        if clauses:
            desc_text = f"{lead} delivers reliable commercial performance. Key specifications include {', '.join(clauses)}."
        else:
            desc_text = f"{lead} delivers reliable commercial performance and meets standard industrial quality specifications."

        # Validate with ClaimChecker to guarantee zero hallucinated claims
        verified_attrs_map = {a.label.lower(): a.normalized_value for a in attributes}
        verified_features = [with_features] if with_features else []
        enrichment_obj = CommerceEnrichment(
            commerce_description=desc_text,
            short_description=desc_text[:100],
            features=verified_features,
        )

        claim_result = self.claim_checker.check(
            enrichment=enrichment_obj,
            verified_attributes=verified_attrs_map,
            verified_features=verified_features,
            verified_applications=[],
            product_identity_text=f"{brand} {clean_pname} {mpn}",
        )

        return desc_text, claim_result

    def build_retail_description(
        self,
        product_name: str,
        attributes: List[ExtractedAttribute],
    ) -> str:
        """Generates catalog retail description."""
        attr_dict = {a.label: a.normalized_value for a in attributes}
        specs = self._get_spec_tokens(attr_dict)

        clean_pname = product_name
        if clean_pname.lower() in ("industrial product", "product", "uncategorized"):
            clean_pname = "Cut-Off Disc" if specs["diameter"] else "Product"

        parts: List[str] = [clean_pname]
        if specs["diameter"] and specs["thickness"]:
            parts.append(f"{specs['diameter']} in x {specs['thickness']} in")
        elif specs["diameter"]:
            parts.append(f"{specs['diameter']} in")

        if specs["application"]:
            parts.append(specs["application"])
        if specs["material"]:
            parts.append(specs["material"])
        if specs["volt"]:
            parts.append(f"{specs['volt']}V")

        return ", ".join(p for p in parts if p)
