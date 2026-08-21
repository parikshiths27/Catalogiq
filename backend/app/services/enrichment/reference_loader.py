"""
Reference Data Loader for CatalogIQ Enrichment Foundation.

Loads and encapsulates:
1. Master UOM Standards & standard abbreviations.
2. Decimal / Fraction lookup table (bidirectional exact mapping).
3. Approved Manufacturer & Brand Master Registry (with legal names and registered trademark symbols).
4. Taxonomy and LOV vocabularies (Faucets, Fittings, Dishwashers, Tools, Electrical, Decking, Siding).
"""
import re
from typing import Any, Dict, List, Optional, Set, Tuple


class ReferenceDataLoader:
    """Central authoritative repository of reference standards, LOVs, fractions, and master data."""

    def __init__(self) -> None:
        self._init_uom_standards()
        self._init_fraction_table()
        self._init_manufacturer_brand_master()
        self._init_taxonomy_and_lov()

    # -------------------------------------------------------------------------
    # 1. Master UOM Standards
    # -------------------------------------------------------------------------
    def _init_uom_standards(self) -> None:
        """Initialize approved master UOM standards."""
        # Canonical units
        self.approved_uoms: Set[str] = {
            "in", "ft", "mm", "cm", "m", "yd",
            "lb", "oz", "g", "kg", "ton",
            "V", "A", "mA", "W", "kW", "HP", "hp", "Hz", "Ah", "AH",
            "dBA", "dB", "RPM", "rpm", "gpm", "GPM", "cfm", "CFM",
            "psi", "PSI", "bar", "Pa", "kPa",
            "°F", "°C", "deg", "°",
            "EA", "PK", "pk", "BX", "bx", "CT", "ct", "RL", "rl", "SET", "set",
            "LF", "SQ", "sq", "gal", "qt", "pt", "oz.", "fl oz", "TPI", "tpi", "GA", "ga",
        }

        # Raw aliases -> Canonical UOM mapping
        self.uom_alias_map: Dict[str, str] = {
            # Length
            "inch": "in", "inches": "in", "in.": "in", "in": "in", "\"": "in", "''": "in",
            "foot": "ft", "feet": "ft", "ft.": "ft", "ft": "ft", "'": "ft",
            "millimeter": "mm", "millimeters": "mm", "mm": "mm",
            "centimeter": "cm", "centimeters": "cm", "cm": "cm",
            "meter": "m", "meters": "m", "m": "m",
            # Weight
            "pound": "lb", "pounds": "lb", "lbs": "lb", "lb.": "lb", "lb": "lb",
            "ounce": "oz", "ounces": "oz", "oz.": "oz", "oz": "oz",
            "gram": "g", "grams": "g", "g": "g",
            "kilogram": "kg", "kilograms": "kg", "kg": "kg",
            # Electrical
            "volt": "V", "volts": "V", "vac": "V", "v": "V", "V": "V", "v.": "V",
            "ampere": "A", "amperes": "A", "amp": "A", "amps": "A", "a": "A", "A": "A", "a.": "A",
            "milliampere": "mA", "milliamperes": "mA", "ma": "mA", "mA": "mA",
            "watt": "W", "watts": "W", "w": "W", "W": "W",
            "kilowatt": "kW", "kilowatts": "kW", "kw": "kW", "kW": "kW",
            "horsepower": "HP", "hp": "HP", "HP": "HP",
            "hertz": "Hz", "hz": "Hz", "Hz": "Hz",
            "amp-hour": "Ah", "amp-hours": "Ah", "ah": "Ah", "Ah": "Ah", "AH": "AH",
            # Sound & Flow
            "decibel": "dBA", "decibels": "dBA", "dba": "dBA", "dBA": "dBA", "db": "dBA", "dB": "dBA",
            "rpm": "RPM", "RPM": "RPM", "r/min": "RPM", "rev/min": "RPM",
            "gpm": "gpm", "GPM": "gpm", "gallons per minute": "gpm",
            "cfm": "cfm", "CFM": "cfm",
            # Pressure & Fasteners
            "psi": "psi", "PSI": "psi", "bar": "bar",
            "gauge": "GA", "ga": "GA", "GA": "GA",
            "teeth per inch": "TPI", "tpi": "TPI", "TPI": "TPI",
            # Packaging
            "each": "EA", "ea": "EA", "EA": "EA",
            "pack": "PK", "pk": "PK", "PK": "PK",
            "box": "BX", "bx": "BX", "BX": "BX",
            "count": "CT", "ct": "CT", "CT": "CT",
            "roll": "RL", "rl": "RL", "RL": "RL",
            "set": "SET", "SET": "SET",
        }

    # -------------------------------------------------------------------------
    # 2. Decimal to Fraction Lookup Table
    # -------------------------------------------------------------------------
    def _init_fraction_table(self) -> None:
        """Initialize authoritative exact decimal to fraction lookups."""
        self.decimal_to_fraction_map: Dict[float, str] = {
            0.03125: "1/32",
            0.040: ".040",
            0.045: ".045",
            0.046875: "3/64",
            0.0625: "1/16",
            0.09375: "3/32",
            0.125: "1/8",
            0.15625: "5/32",
            0.1875: "3/16",
            0.21875: "7/32",
            0.25: "1/4",
            0.28125: "9/32",
            0.3125: "5/16",
            0.34375: "11/32",
            0.375: "3/8",
            0.40625: "13/32",
            0.4375: "7/16",
            0.46875: "15/32",
            0.5: "1/2",
            0.53125: "17/32",
            0.5625: "9/16",
            0.59375: "19/32",
            0.625: "5/8",
            0.65625: "21/32",
            0.6875: "11/16",
            0.71875: "23/32",
            0.75: "3/4",
            0.78125: "25/32",
            0.8125: "13/16",
            0.84375: "27/32",
            0.875: "7/8",
            0.90625: "29/32",
            0.9375: "15/16",
            0.96875: "31/32",
        }

        # Reverse map for parsing fraction string -> decimal
        self.fraction_to_decimal_map: Dict[str, float] = {
            v: k for k, v in self.decimal_to_fraction_map.items()
        }

    # -------------------------------------------------------------------------
    # 3. Approved Manufacturer & Brand Master Registry
    # -------------------------------------------------------------------------
    def _init_manufacturer_brand_master(self) -> None:
        """Initialize authoritative manufacturer and brand records with legal casing and trademarks."""
        self.manufacturers: Dict[str, Dict[str, Any]] = {
            "Rheem Manufacturing": {
                "canonical_name": "Rheem Manufacturing",
                "aliases": ["rheem", "rheem manufacturing", "rheem manufacturing company"],
                "brands": ["FRIGIDAIRE®", "Rheem®", "Ruud®"],
            },
            "Whirlpool Corporation": {
                "canonical_name": "Whirlpool Corporation",
                "aliases": ["whirlpool", "whirlpool corp", "whirlpool corporation", "kitchenaid", "maytag", "jennair", "amana"],
                "brands": ["Whirlpool®", "KitchenAid®", "Maytag®", "Amana®", "JennAir®"],
            },
            "GE Appliances, a Haier company": {
                "canonical_name": "GE Appliances, a Haier company",
                "aliases": ["ge", "ge appliances", "general electric", "cafe", "café", "ge profile", "monogram", "hotpoint"],
                "brands": ["GE®", "Café™", "GE Profile™", "Monogram®", "Hotpoint®"],
            },
            "LG Electronics USA, Inc.": {
                "canonical_name": "LG Electronics USA, Inc.",
                "aliases": ["lg", "lg electronics", "lg electronics usa"],
                "brands": ["LG®", "LG SIGNATURE®"],
            },
            "Alliance Laundry Systems LLC": {
                "canonical_name": "Alliance Laundry Systems LLC",
                "aliases": ["speed queen", "speedqueen", "alliance laundry"],
                "brands": ["Speed Queen®"],
            },
            "Beko US, Inc.": {
                "canonical_name": "Beko US, Inc.",
                "aliases": ["beko", "beko us"],
                "brands": ["Beko®"],
            },
            "Element Electronics": {
                "canonical_name": "Element Electronics",
                "aliases": ["element", "element electronics"],
                "brands": ["Element®"],
            },
            "Sharp Electronics Corporation": {
                "canonical_name": "Sharp Electronics Corporation",
                "aliases": ["sharp", "sharp electronics"],
                "brands": ["Sharp®"],
            },
            "Freud America, Inc.": {
                "canonical_name": "Freud America, Inc.",
                "aliases": ["freud", "freud inc", "diablo", "freud america"],
                "brands": ["Diablo®", "Freud®"],
            },
            "3M Company": {
                "canonical_name": "3M Company",
                "aliases": ["3m", "3 m", "3 m co", "3m company", "cubitron", "stikit"],
                "brands": ["3M®", "Cubitron™ II", "Scotch®"],
            },
            "Mirka USA Inc.": {
                "canonical_name": "Mirka USA Inc.",
                "aliases": ["mirka", "mirka abrasives", "mirka abrasives inc", "mirka usa"],
                "brands": ["Mirka®", "Abranet®", "Hiolit®", "Iridium®"],
            },
            "Milwaukee Electric Tool Corporation": {
                "canonical_name": "Milwaukee Electric Tool Corporation",
                "aliases": ["milwaukee", "milw", "milwaukee accessory", "milwaukee tool"],
                "brands": ["Milwaukee®", "Sawzall®", "Packout™"],
            },
            "Stanley Black & Decker, Inc.": {
                "canonical_name": "Stanley Black & Decker, Inc.",
                "aliases": ["dewalt", "black & decker", "black & decker/dewlt", "irwin", "bostitch", "craftsman", "stanley"],
                "brands": ["DEWALT®", "Black & Decker®", "Irwin®", "Craftsman®", "Bostitch®"],
            },
            "Makita U.S.A., Inc.": {
                "canonical_name": "Makita U.S.A., Inc.",
                "aliases": ["makita", "makita usa", "makita usa inc"],
                "brands": ["Makita®"],
            },
            "Festool USA": {
                "canonical_name": "Festool USA",
                "aliases": ["festool", "festool usa"],
                "brands": ["Festool®"],
            },
            "Robert Bosch Tool Corporation": {
                "canonical_name": "Robert Bosch Tool Corporation",
                "aliases": ["bosch", "robt bosch tool corp", "robert bosch", "dremel"],
                "brands": ["Bosch®", "Dremel®"],
            },
            "Kreg Tool Company": {
                "canonical_name": "Kreg Tool Company",
                "aliases": ["kreg", "kreg tool", "kreg tool company"],
                "brands": ["Kreg®"],
            },
            "KYOCERA SENCO Industrial Tools, Inc.": {
                "canonical_name": "KYOCERA SENCO Industrial Tools, Inc.",
                "aliases": ["senco", "senco products inc", "senco products"],
                "brands": ["Senco®"],
            },
            "Illinois Tool Works Inc.": {
                "canonical_name": "Illinois Tool Works Inc.",
                "aliases": ["paslode", "national nail", "national nail corp", "itw"],
                "brands": ["Paslode®", "National Nail®"],
            },
            "Prebena North America Inc.": {
                "canonical_name": "Prebena North America Inc.",
                "aliases": ["prebena", "prebena na"],
                "brands": ["Prebena®"],
            },
            "Vessel Tools USA Inc.": {
                "canonical_name": "Vessel Tools USA Inc.",
                "aliases": ["vessel", "vessel tools", "vessel tools usa"],
                "brands": ["Vessel®"],
            },
            "Wera Tools Inc.": {
                "canonical_name": "Wera Tools Inc.",
                "aliases": ["wera", "wera tools", "wera tools na inc"],
                "brands": ["Wera®"],
            },
            "Trex Company, Inc.": {
                "canonical_name": "Trex Company, Inc.",
                "aliases": ["trex", "trex company"],
                "brands": ["Trex®"],
            },
            "The AZEK Company Inc.": {
                "canonical_name": "The AZEK Company Inc.",
                "aliases": ["timbertech", "azek", "the azek company"],
                "brands": ["TimberTech®", "AZEK®"],
            },
            "Barrette Outdoor Living, Inc.": {
                "canonical_name": "Barrette Outdoor Living, Inc.",
                "aliases": ["rdi", "finyline", "barrette"],
                "brands": ["RDI®", "Finyline®"],
            },
            "Digger Specialties, Inc.": {
                "canonical_name": "Digger Specialties, Inc.",
                "aliases": ["dsi", "westbury", "digger specialties"],
                "brands": ["Westbury®", "DSI®"],
            },
            "ProVia LLC": {
                "canonical_name": "ProVia LLC",
                "aliases": ["provia", "provia door"],
                "brands": ["ProVia®"],
            },
            "United Window & Door Mfg, Inc.": {
                "canonical_name": "United Window & Door Mfg, Inc.",
                "aliases": ["united window & door", "united window"],
                "brands": ["United Window & Door®"],
            },
            "Velux America LLC": {
                "canonical_name": "Velux America LLC",
                "aliases": ["velux", "velux america", "velux america inc"],
                "brands": ["Velux®"],
            },
            "Andersen Corporation": {
                "canonical_name": "Andersen Corporation",
                "aliases": ["andersen", "andersen windows"],
                "brands": ["Andersen®"],
            },
            "James Hardie Building Products Inc.": {
                "canonical_name": "James Hardie Building Products Inc.",
                "aliases": ["james hardie", "hardie", "hardieplank", "hardiepanel"],
                "brands": ["James Hardie®", "HardiePlank®"],
            },
            "Louisiana-Pacific Corporation": {
                "canonical_name": "Louisiana-Pacific Corporation",
                "aliases": ["lp smartside", "lp", "louisiana pacific", "smartside"],
                "brands": ["LP® SmartSide®"],
            },
            "Huber Engineered Woods LLC": {
                "canonical_name": "Huber Engineered Woods LLC",
                "aliases": ["huber", "huber eng wood", "zip system", "advanTech"],
                "brands": ["ZIP System®", "AdvanTech®"],
            },
            "CertainTeed LLC": {
                "canonical_name": "CertainTeed LLC",
                "aliases": ["certainteed", "certainteed gypsum"],
                "brands": ["CertainTeed®"],
            },
            "Owens Corning": {
                "canonical_name": "Owens Corning",
                "aliases": ["owens corning", "oc duration"],
                "brands": ["Owens Corning®"],
            },
            "Henry Company": {
                "canonical_name": "Henry Company",
                "aliases": ["henry", "henry company", "eaveguard"],
                "brands": ["Henry®"],
            },
            "Satco Products, Inc.": {
                "canonical_name": "Satco Products, Inc.",
                "aliases": ["satco", "satco prod inc", "nuvo"],
                "brands": ["Satco®", "Nuvo®", "Starfish™"],
            },
            "Kichler Lighting LLC": {
                "canonical_name": "Kichler Lighting LLC",
                "aliases": ["kichler", "kichler lighting"],
                "brands": ["Kichler®"],
            },
            "Signify North America Corporation": {
                "canonical_name": "Signify North America Corporation",
                "aliases": ["philips", "phillips lighting", "wiz", "signify"],
                "brands": ["Philips®", "WiZ®"],
            },
            "Acuity Brands Lighting, Inc.": {
                "canonical_name": "Acuity Brands Lighting, Inc.",
                "aliases": ["lithonia", "lithonia lighting", "acuity brands"],
                "brands": ["Lithonia Lighting®"],
            },
            "Cooper Lighting Solutions": {
                "canonical_name": "Cooper Lighting Solutions",
                "aliases": ["cooper lighting", "halo"],
                "brands": ["Cooper Lighting®", "Halo®"],
            },
            "Feit Electric Company, Inc.": {
                "canonical_name": "Feit Electric Company, Inc.",
                "aliases": ["feit", "feit electric"],
                "brands": ["Feit Electric®"],
            },
            "Leviton Manufacturing Co., Inc.": {
                "canonical_name": "Leviton Manufacturing Co., Inc.",
                "aliases": ["leviton", "leviton mfg", "leviton mfg co"],
                "brands": ["Leviton®"],
            },
            "Lutron Electronics Co., Inc.": {
                "canonical_name": "Lutron Electronics Co., Inc.",
                "aliases": ["lutron", "lutron electronics"],
                "brands": ["Lutron®"],
            },
            "Schneider Electric USA, Inc.": {
                "canonical_name": "Schneider Electric USA, Inc.",
                "aliases": ["square d", "square d con prod dv", "schneider electric"],
                "brands": ["Square D™"],
            },
            "Southwire Company, LLC": {
                "canonical_name": "Southwire Company, LLC",
                "aliases": ["southwire", "southwire/g turner", "woods wire"],
                "brands": ["Southwire®"],
            },
            "ABB Installation Products Inc.": {
                "canonical_name": "ABB Installation Products Inc.",
                "aliases": ["carlon", "thomas & betts"],
                "brands": ["Carlon®", "Thomas & Betts®"],
            },
            "Prime Wire & Cable, Inc.": {
                "canonical_name": "Prime Wire & Cable, Inc.",
                "aliases": ["prime wire", "prime wire & cable"],
                "brands": ["Prime®"],
            },
            "Hunter Fan Company": {
                "canonical_name": "Hunter Fan Company",
                "aliases": ["hunter", "hunter fan", "hunter fan co"],
                "brands": ["Hunter®"],
            },
            "Delta Faucet Company": {
                "canonical_name": "Delta Faucet Company",
                "aliases": ["delta", "delta faucet", "brizo", "peerless"],
                "brands": ["Delta®", "Brizo®", "Peerless®"],
            },
            "Moen Incorporated": {
                "canonical_name": "Moen Incorporated",
                "aliases": ["moen"],
                "brands": ["Moen®"],
            },
            "Kohler Co.": {
                "canonical_name": "Kohler Co.",
                "aliases": ["kohler", "sterling"],
                "brands": ["Kohler®", "Sterling®"],
            },
            "NIBCO INC.": {
                "canonical_name": "NIBCO INC.",
                "aliases": ["nibco", "nibco inc"],
                "brands": ["NIBCO®", "Chemtrol®", "Webstone®"],
            },
            "Charlotte Pipe and Foundry Company": {
                "canonical_name": "Charlotte Pipe and Foundry Company",
                "aliases": ["charlotte pipe", "charlotte pipe and foundry"],
                "brands": ["Charlotte Pipe®"],
            },
            "Mueller Industries, Inc.": {
                "canonical_name": "Mueller Industries, Inc.",
                "aliases": ["mueller", "mueller industries", "streamline"],
                "brands": ["Streamline®", "Mueller®"],
            },
            "Signify North America Corporation": {
                "canonical_name": "Signify North America Corporation",
                "aliases": ["philips", "phillips", "phillips lighting", "philips lighting", "signify"],
                "brands": ["Philips®", "Advance®", "Day-Brite®"],
            },
            "Kichler Lighting LLC": {
                "canonical_name": "Kichler Lighting LLC",
                "aliases": ["kichler", "kichler lighting", "kichler lighting llc", "kicli"],
                "brands": ["Kichler®"],
            },
            "Satco Products, Inc.": {
                "canonical_name": "Satco Products, Inc.",
                "aliases": ["satco", "satco prod", "satco prod inc", "nuvo"],
                "brands": ["Satco®", "Nuvo®"],
            },
            "Boise Cascade Company": {
                "canonical_name": "Boise Cascade Company",
                "aliases": ["boise cascade", "boise cascade building materials", "boica"],
                "brands": ["Boise Cascade®", "BCI®"],
            },
            "Appliance Dealers Cooperative": {
                "canonical_name": "Appliance Dealers Cooperative",
                "aliases": ["appliance dealers cooperative", "appde"],
                "brands": [],
            },
            "Parksite Inc.": {
                "canonical_name": "Parksite Inc.",
                "aliases": ["parksite", "parksite inc"],
                "brands": ["Parksite®"],
            },
            "U.S. LUMBER Group, LLC": {
                "canonical_name": "U.S. LUMBER Group, LLC",
                "aliases": ["u s lumber", "us lumber", "u.s. lumber"],
                "brands": ["U.S. Lumber®"],
            },
            "Wolf Peak International, Inc.": {
                "canonical_name": "Wolf Peak International, Inc.",
                "aliases": ["edge eyewear", "edge eyewear inc", "edgsa", "wolf peak"],
                "brands": ["Edge Eyewear®"],
            },
            "U.S. Tape Company": {
                "canonical_name": "U.S. Tape Company",
                "aliases": ["u s tape", "us tape", "u s tape company", "durawheel"],
                "brands": ["US Tape®", "DuraWheel®"],
            },
            "Palmer-Donavin Mfg. Co.": {
                "canonical_name": "Palmer-Donavin Mfg. Co.",
                "aliases": ["palmer donavin", "palmer donavin mfg company", "paldo"],
                "brands": ["Palmer-Donavin®"],
            },
            "Premier Metals LLC": {
                "canonical_name": "Premier Metals LLC",
                "aliases": ["premier metals", "premier metals llc", "preme"],
                "brands": ["Premier Metals®"],
            },
            "SawStop, LLC": {
                "canonical_name": "SawStop, LLC",
                "aliases": ["sawstop", "saw stop", "saw stop llc", "sawst"],
                "brands": ["SawStop®"],
            },
            "Bow Products": {
                "canonical_name": "Bow Products",
                "aliases": ["bow products", "bow products llc", "bowpr"],
                "brands": ["Bow Products®"],
            },
            "Woodpeckers, LLC": {
                "canonical_name": "Woodpeckers, LLC",
                "aliases": ["woodpeckers", "woodpeckers inc", "woodp"],
                "brands": ["Woodpeckers®"],
            },
            "Rees Cast Stone Company": {
                "canonical_name": "Rees Cast Stone Company",
                "aliases": ["rees cast stone", "rees cast stone company", "reeca"],
                "brands": ["Rees Cast Stone®"],
            },
            "United Window & Door Manufacturing": {
                "canonical_name": "United Window & Door Manufacturing",
                "aliases": ["united window & door", "united window & door manufacturing", "uniwi"],
                "brands": ["United Window & Door®"],
            },
            "Westwood Lumber Sales": {
                "canonical_name": "Westwood Lumber Sales",
                "aliases": ["westwood lumber", "westwood lumber sales", "weslu"],
                "brands": ["Westwood Lumber®"],
            },
            "VELUX America LLC": {
                "canonical_name": "VELUX America LLC",
                "aliases": ["velux", "velux america", "velux america inc", "velam"],
                "brands": ["VELUX®"],
            },
            "Fenton Bros. Electric, Inc.": {
                "canonical_name": "Fenton Bros. Electric, Inc.",
                "aliases": ["fenton bros", "fenton bros electric", "fenton bros electric inc", "fenbr"],
                "brands": ["Fenton Bros.®"],
            },
            "Whiteside Machine Company": {
                "canonical_name": "Whiteside Machine Company",
                "aliases": ["whiteside", "whiteside machine & repair co", "whima"],
                "brands": ["Whiteside®"],
            },
            "C.M.T. UTENSILI S.p.A.": {
                "canonical_name": "C.M.T. UTENSILI S.p.A.",
                "aliases": ["cmt", "cmt usa", "cmt usa inc", "cmtus", "cmt orange tools"],
                "brands": ["CMT Orange Tools®"],
            },
            "JPW Industries Inc.": {
                "canonical_name": "JPW Industries Inc.",
                "aliases": ["jpw industries", "jet", "powermatic", "jpwin"],
                "brands": ["JET®", "Powermatic®"],
            },
            "Oliver Machinery Company": {
                "canonical_name": "Oliver Machinery Company",
                "aliases": ["oliver machinery", "oliver machinery company", "olima"],
                "brands": ["Oliver®"],
            },
            "Custom LeatherCraft / Tech Gear": {
                "canonical_name": "Custom LeatherCraft / Tech Gear",
                "aliases": ["tech gear 5.7", "tech gear 5.7 inc", "tecge", "clc"],
                "brands": ["Tech Gear®", "CLC®"],
            },
            "Emseal Joint Systems Ltd": {
                "canonical_name": "Emseal Joint Systems Ltd",
                "aliases": ["emseal", "emseal joint systems", "emseal joint systems ltd", "emsjo"],
                "brands": ["Emseal®"],
            },
            "V & V Appliance Parts Inc": {
                "canonical_name": "V & V Appliance Parts Inc",
                "aliases": ["v & v appliance parts", "v & v appliance parts inc", "vvapp"],
                "brands": ["V&V Appliance Parts®"],
            },
        }

        # Canonical brand dictionary mapping brand name to details
        self.brands: Dict[str, Dict[str, Any]] = {}
        for mfr_name, data in self.manufacturers.items():
            for b in data["brands"]:
                # normalized key without trademark symbol
                clean_b = re.sub(r"[®™]", "", b).strip().upper()
                self.brands[clean_b] = {
                    "canonical_brand": b,
                    "canonical_manufacturer": mfr_name,
                }

    # -------------------------------------------------------------------------
    # 4. Taxonomy & LOV Standards
    # -------------------------------------------------------------------------
    def _init_taxonomy_and_lov(self) -> None:
        """Initialize authoritative taxonomy hierarchies and category LOVs."""
        self.taxonomies: List[Dict[str, Any]] = [
            {
                "dept": "Appliances",
                "class_": "Large Appliances",
                "fine": "Dishwashers",
                "classpath": "Appliances & Consumer Electronics>Kitchen Appliances>Built-In Dishwashers",
                "product_name": "Dishwasher",
                "keywords": ["dishwasher", "dishwashers", "wash cycle", "racks", "silverware basket"],
                "allowed_attributes": [
                    "Series", "Model", "Number of Wash Cycles", "Voltage Rating", "Amperage Rating",
                    "Mounting Type", "Plug Type", "Size", "Depth With Door Open", "Minimum Height",
                    "Maximum Height", "Sound Level", "Material", "Color", "Additional Information"
                ],
                "lov": {
                    "Mounting Type": ["Built-in", "Leg", "Undercounter", "Freestanding", "Portable"],
                    "Material": ["Stainless Steel", "Plastic", "Steel", "Composite"],
                    "Color": ["Stainless Steel", "Black", "White", "Black Stainless", "Custom Panel Ready"],
                    "Voltage Rating": ["120"],
                    "Amperage Rating": ["10", "15", "20"],
                }
            },
            {
                "dept": "Appliances",
                "class_": "Large Appliances",
                "fine": "Refrigerators & Freezers",
                "classpath": "Appliances & Consumer Electronics>Kitchen Appliances>Refrigerators",
                "product_name": "Refrigerator",
                "keywords": ["fridge", "refrigerator", "freezer", "beverage center", "upright freezer", "chest freezer"],
                "allowed_attributes": ["Series", "Capacity", "Door Style", "Voltage Rating", "Color", "Material", "Additional Information"],
                "lov": {
                    "Color": ["Stainless Steel", "Black", "White", "Slate", "Matte Black", "Matte White"],
                }
            },
            {
                "dept": "Appliances",
                "class_": "Large Appliances",
                "fine": "Washers & Dryers",
                "classpath": "Appliances & Consumer Electronics>Laundry Appliances>Washers & Dryers",
                "product_name": "Washer/Dryer",
                "keywords": ["washer", "dryer", "gas dryer", "elect dryer", "laundry center"],
                "allowed_attributes": ["Series", "Fuel Type", "Voltage Rating", "Capacity", "Color", "Mounting Type"],
                "lov": {
                    "Fuel Type": ["Electric", "Gas"],
                    "Color": ["White", "Black", "Dark Gray", "Stainless Steel"],
                }
            },
            {
                "dept": "Appliances",
                "class_": "Large Appliances",
                "fine": "Ranges & Ovens",
                "classpath": "Appliances & Consumer Electronics>Kitchen Appliances>Ranges & Ovens",
                "product_name": "Range/Oven",
                "keywords": ["range", "cooktop", "wall oven", "microwave", "otr microwave", "electric range", "gas range"],
                "allowed_attributes": ["Series", "Fuel Type", "Size", "Color", "Voltage Rating", "Number of Burners"],
                "lov": {
                    "Fuel Type": ["Electric", "Gas", "Induction", "Dual Fuel"],
                    "Color": ["Stainless Steel", "Black", "White", "Black Slate"],
                }
            },
            {
                "dept": "Appliances",
                "class_": "Small Appliances",
                "fine": "Coffee Makers & Toasters",
                "classpath": "Appliances & Consumer Electronics>Kitchen Appliances>Small Appliances",
                "product_name": "Small Appliance",
                "keywords": ["coffee maker", "espresso machine", "toaster", "toast oven", "drip coffee"],
                "allowed_attributes": ["Series", "Color", "Capacity", "Voltage Rating", "Material"],
                "lov": {
                    "Color": ["Matte Black", "Matte White", "Stainless Steel", "Black", "White"],
                }
            },
            {
                "dept": "Hardware & Tools",
                "class_": "Power Tool Accessories",
                "fine": "Abrasives & Cut-Off Wheels",
                "classpath": "Tools & Hardware>Abrasives>Abrasive Wheels & Discs",
                "product_name": "Cut-Off Disc / Sanding Abrasive",
                "keywords": ["cut-off disc", "cut off disc", "grinding wheel", "sanding belt", "sanding sponge", "abranet", "hiolit", "stikit film", "cubitron"],
                "allowed_attributes": ["Diameter", "Thickness", "Arbor Size", "Grit", "Abrasive Material", "Application", "Package Quantity"],
                "lov": {
                    "Application": ["Metal", "Masonry", "Stainless Steel", "Steel Demon", "Speed Demon", "General Purpose", "Dual Metal Cut and Grind"],
                    "Abrasive Material": ["Ceramic", "Aluminum Oxide", "Silicon Carbide", "Diamond"],
                }
            },
            {
                "dept": "Hardware & Tools",
                "class_": "Power Tool Accessories",
                "fine": "Saw Blades",
                "classpath": "Tools & Hardware>Power Tool Accessories>Saw Blades",
                "product_name": "Saw Blade",
                "keywords": ["saw blade", "circ saw blade", "circular saw blade", "jig saw blade", "sawzall blade", "diamond blade", "track saw blade", "planer blade"],
                "allowed_attributes": ["Diameter", "Number of Teeth", "Tooth Material", "Arbor Size", "Application", "Kerf"],
                "lov": {
                    "Application": ["Fine Finish", "Framing", "Cement Track Saw", "Laminate & Wood Flooring", "Diamond Tile", "Laminate Track Saw"],
                    "Tooth Material": ["Carbide", "High Speed Steel", "Diamond Segmented"],
                }
            },
            {
                "dept": "Hardware & Tools",
                "class_": "Power Tools",
                "fine": "Drills & Drivers",
                "classpath": "Tools & Hardware>Power Tools>Drills & Drivers",
                "product_name": "Drill / Impact Driver",
                "keywords": ["drill", "hammer drill", "drill driver", "impact driver", "impact wrench", "screwdriver", "ratchet"],
                "allowed_attributes": ["Series", "Voltage Rating", "Drive Size", "Chuck Size", "Torque Rating", "Bare Tool/Kit"],
                "lov": {
                    "Voltage Rating": ["12 V", "18 V", "20 V", "40 V", "60 V", "120 V"],
                    "Drive Size": ["1/4 in", "3/8 in", "1/2 in", "3/4 in", "Hex"],
                    "Bare Tool/Kit": ["Bare Tool", "Kit"],
                }
            },
            {
                "dept": "Hardware & Tools",
                "class_": "Power Tools",
                "fine": "Saws & Woodworking Machinery",
                "classpath": "Tools & Hardware>Power Tools>Saws",
                "product_name": "Power Saw",
                "keywords": ["circ saw", "circular saw", "miter saw", "bandsaw", "table saw", "jig saw", "recip saw", "track saw", "planer", "shaper", "jointer"],
                "allowed_attributes": ["Series", "Blade Diameter", "Voltage Rating", "Motor Power", "Bevel Capacity"],
                "lov": {
                    "Blade Diameter": ["4-1/2 in", "6-1/2 in", "7-1/4 in", "8-1/2 in", "10 in", "12 in", "14 in", "18 in"],
                }
            },
            {
                "dept": "Building Materials",
                "class_": "Decking & Railing",
                "fine": "Composite Decking & Fascia",
                "classpath": "Building Materials>Decking & Railing>Composite Decking",
                "product_name": "Decking / Fascia Board",
                "keywords": ["decking", "fascia", "lineage", "transcend", "enhance", "vintage azek", "landmark azek", "harvest azek", "sq edge", "grooved"],
                "allowed_attributes": ["Series", "Color", "Length", "Width", "Thickness", "Edge Profile", "Material"],
                "lov": {
                    "Edge Profile": ["Square Edge", "Grooved"],
                    "Material": ["Composite", "Capped Composite", "PVC", "Capped Polymer"],
                    "Length": ["12 ft", "16 ft", "20 ft"],
                    "Width": ["6 in", "8 in", "12 in"],
                }
            },
            {
                "dept": "Building Materials",
                "class_": "Decking & Railing",
                "fine": "Railing Systems & Components",
                "classpath": "Building Materials>Decking & Railing>Railing",
                "product_name": "Railing Kit / Post Sleeve",
                "keywords": ["rail kit", "t-rail", "rail panel", "post trim", "post sleeve", "post wrap", "gate", "baluster"],
                "allowed_attributes": ["Series", "Color", "Length", "Height", "Baluster Type", "Orientation", "Material"],
                "lov": {
                    "Color": ["White", "Black", "Clay"],
                    "Orientation": ["Horizontal", "Stair"],
                    "Baluster Type": ["Square Composite", "Round Aluminum", "Square Aluminum"],
                }
            },
            {
                "dept": "Plumbing",
                "class_": "Fittings",
                "fine": "Pipe & Tubing Fittings",
                "classpath": "Plumbing>Pipe, Tubing & Fittings>Fittings",
                "product_name": "Pipe Fitting",
                "keywords": ["fitting", "elbow", "tee", "coupling", "adapter", "bushing", "union", "flange", "nipple", "cross", "plug", "cap", "reducer"],
                "allowed_attributes": ["Fitting Type", "Fitting Size", "Connection Type", "Material", "Pressure Class", "Schedule", "Standard/Approvals"],
                "lov": {
                    "Fitting Type": ["90 deg Elbow", "45 deg Elbow", "Tee", "Coupling", "Adapter", "Reducer", "Bushing", "Union", "Cap", "Plug", "Flange", "Nipple"],
                    "Connection Type": ["NPT", "Threaded", "Socket Weld", "Butt Weld", "Soldered", "Press-to-Connect", "Push-Fit", "Flanged", "Compression"],
                    "Material": ["Brass", "Bronze", "Cast Iron", "Ductile Iron", "Carbon Steel", "Stainless Steel (304/316)", "Copper", "PVC", "CPVC", "PEX"],
                    "Pressure Class": ["Class 125", "Class 150", "Class 250", "Class 300", "Class 600", "Class 1500", "Class 3000", "Class 6000", "150 lb", "300 lb"],
                    "Schedule": ["Schedule 40", "Schedule 80", "Schedule 160", "Schedule 10"],
                    "Standard/Approvals": ["ASME B16.3", "ASME B16.9", "ASME B16.11", "ASTM A105", "ASTM A182", "ASTM A197", "ASTM B62", "NSF/ANSI 61", "NSF/ANSI 372", "UL Listed", "FM Approved"]
                }
            },
            {
                "dept": "Plumbing",
                "class_": "Faucets",
                "fine": "Kitchen & Bathroom Faucets",
                "classpath": "Plumbing>Faucets & Sinks>Faucets",
                "product_name": "Faucet",
                "keywords": ["faucet", "kitchen faucet", "bathroom faucet", "lavatory faucet", "pull-down faucet", "single-handle", "two-handle", "centerset", "widespread", "vessel faucet"],
                "allowed_attributes": ["Faucet Type", "Mounting Type", "Number of Handles", "Flow Rate", "Spout Reach", "Spout Height", "Finish/Color", "Valve Type", "Drain Assembly Included"],
                "lov": {
                    "Faucet Type": ["Kitchen Faucet", "Lavatory Faucet", "Bar Faucet", "Utility Faucet", "Vessel Faucet", "Commercial Faucet"],
                    "Mounting Type": ["Deck Mount", "Wall Mount", "Centerset (4 in)", "Widespread (8 in)", "Single Hole"],
                    "Number of Handles": ["1", "2", "Hands-Free / Touchless"],
                    "Flow Rate": ["0.5 gpm", "1.0 gpm", "1.2 gpm", "1.5 gpm", "1.8 gpm", "2.2 gpm"],
                    "Finish/Color": ["Chrome", "Brushed Nickel", "Matte Black", "Stainless Steel", "Oil Rubbed Bronze", "Polished Brass"],
                    "Valve Type": ["Ceramic Disc Cartridge", "Washerless Cartridge", "Compression"],
                    "Drain Assembly Included": ["Yes", "No"]
                }
            }
        ]


_loader_instance: Optional[ReferenceDataLoader] = None


def get_reference_loader() -> ReferenceDataLoader:
    """Singleton getter for reference data loader."""
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = ReferenceDataLoader()
    return _loader_instance
