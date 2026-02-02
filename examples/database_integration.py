"""
Example Integration Script

Shows how to use the GS1 parser with GTIN lookup integration.

This script demonstrates:
1. Parsing barcode to extract GTIN and other fields
2. Preparing data structure for database lookup
3. Simulating lookup (you'll replace with real database query)
4. Returning complete medication information as JSON
"""

import json
from gs1_parser import prepare_for_lookup


# Simulated database (replace with real database query)
GTIN_DATABASE = {
    "06286740000249": {
        "Drug Trade Name": "Panadol Extra",
        "Scientific Name": "Paracetamol 500mg + Caffeine 65mg",
        "Pharmaceutical Form": "Film-Coated Tablet",
        "Number of Subunits": "24"
    },
    "06285096002877": {
        "Drug Trade Name": "Augmentin",
        "Scientific Name": "Amoxicillin 875mg + Clavulanic Acid 125mg",
        "Pharmaceutical Form": "Film-Coated Tablet",
        "Number of Subunits": "14"
    },
    "06291103731555": {
        "Drug Trade Name": "Lipitor",
        "Scientific Name": "Atorvastatin 20mg",
        "Pharmaceutical Form": "Film-Coated Tablet",
        "Number of Subunits": "30"
    },
    "06223000010365": {
        "Drug Trade Name": "Ventolin Inhaler",
        "Scientific Name": "Salbutamol 100mcg/dose",
        "Pharmaceutical Form": "Pressurized Inhalation",
        "Number of Subunits": "200 doses"
    },
    "06251159026067": {
        "Drug Trade Name": "Brufen",
        "Scientific Name": "Ibuprofen 400mg",
        "Pharmaceutical Form": "Film-Coated Tablet",
        "Number of Subunits": "20"
    },
}


def lookup_gtin(gtin_code: str) -> dict:
    """
    Lookup GTIN in database and return medication information.

    Replace this function with your actual database query.

    Args:
        gtin_code: 14-digit GTIN code

    Returns:
        Dictionary with drug information
    """
    if gtin_code in GTIN_DATABASE:
        return GTIN_DATABASE[gtin_code]
    else:
        return {
            "Drug Trade Name": "Unknown",
            "Scientific Name": "Not found in database",
            "Pharmaceutical Form": "Unknown",
            "Number of Subunits": "Unknown"
        }


def parse_and_lookup(barcode_data: str) -> str:
    """
    Complete workflow: Parse barcode + Lookup GTIN + Return full info.

    Args:
        barcode_data: Raw barcode string (no separators)

    Returns:
        JSON string with complete medication information
    """
    # Step 1: Parse barcode and prepare for lookup
    parsed_data = prepare_for_lookup(barcode_data)

    # Step 2: Extract GTIN for lookup
    gtin_code = parsed_data.get("GTIN Code")

    if gtin_code:
        # Step 3: Lookup GTIN in database
        drug_info = lookup_gtin(gtin_code)

        # Step 4: Merge parsed data with lookup results
        parsed_data.update(drug_info)

    # Step 5: Return as JSON
    return json.dumps(parsed_data, ensure_ascii=False, indent=2)


def main():
    """Demo: Parse all ground truth cases and show complete info."""
    print("=" * 80)
    print("  GS1 BARCODE PARSER + GTIN LOOKUP INTEGRATION")
    print("=" * 80)

    test_cases = [
        ("Case A", "01062867400002491728043010GB2C2171490437969853"),
        ("Case B", "01062850960028771726033110HN8X2172869453519267"),
        ("Case C", "01062911037315552164SSI54CE688QZ1727021410C601"),
        ("Case D", "010622300001036517270903103056442130564439945626"),
        ("Case E", "010625115902606717290400104562202106902409792902"),
    ]

    for case_name, barcode in test_cases:
        print(f"\n{case_name}:")
        print("-" * 80)
        print(f"Input: {barcode}")
        print("\nOutput:")
        result = parse_and_lookup(barcode)
        print(result)

    # Example: Unknown GTIN
    print("\n\nExample: Unknown GTIN (not in database):")
    print("-" * 80)
    unknown_barcode = "01099999999999917290131101234521SERIAL123"
    print(f"Input: {unknown_barcode}")
    print("\nOutput:")
    result = parse_and_lookup(unknown_barcode)
    print(result)


if __name__ == "__main__":
    main()
