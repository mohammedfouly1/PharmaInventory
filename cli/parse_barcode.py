#!/usr/bin/env python3
"""
Simple CLI for parsing GS1 barcodes without separators.

Usage:
    python parse_barcode.py "01062867400002491728043010GB2C2171490437969853"

Output:
    Clean JSON with human-readable field names
"""

import sys
import json
from pathlib import Path

# Add parent directory to path to import gs1_parser
sys.path.insert(0, str(Path(__file__).parent.parent))

from gs1_parser import parse_gs1_to_json


def main():
    """Main CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python parse_barcode.py <barcode_data>")
        print("\nExample:")
        print('  python parse_barcode.py "01062867400002491728043010GB2C2171490437969853"')
        sys.exit(1)

    barcode_data = sys.argv[1]

    try:
        # Parse and output JSON
        json_output = parse_gs1_to_json(barcode_data)
        print(json_output)

    except Exception as e:
        # Output error as JSON for consistency
        error_output = {
            "error": str(e),
            "input": barcode_data
        }
        print(json.dumps(error_output, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
