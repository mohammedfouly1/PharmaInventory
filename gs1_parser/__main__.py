"""
CLI interface for GS1 Parser.

Usage:
    python -m gs1_parser "<barcode text>" [options]
    
Options:
    --show-alternatives    Show alternative parse results
    --strict              Fail on validation errors
    --json                Output as JSON
    --no-normalize        Don't normalize separators
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from .parser import parse_gs1, ParseOptions, ParseResult
from .lookup import lookup_gtin


def format_element(element: dict, indent: int = 2) -> str:
    """Format a single element for display."""
    prefix = " " * indent
    lines = [
        f"{prefix}AI({element['ai']}): {element['name']}",
        f"{prefix}  Value: {element['raw_value']!r}",
        f"{prefix}  Valid: {element['valid']}",
    ]
    
    if element.get('errors'):
        lines.append(f"{prefix}  Errors: {', '.join(element['errors'])}")
    
    if element.get('meta'):
        meta = element['meta']
        if 'check_digit_valid' in meta:
            lines.append(f"{prefix}  Check Digit Valid: {meta['check_digit_valid']}")
        if 'iso_date' in meta:
            lines.append(f"{prefix}  Date: {meta['iso_date']}")
        if 'decimal_value' in meta:
            lines.append(f"{prefix}  Decimal Value: {meta['decimal_value']}")
    
    return '\n'.join(lines)


def format_result(result: ParseResult, show_alternatives: bool = False) -> str:
    """Format parse result for display."""
    lines = [
        "=" * 60,
        "GS1 Parse Result",
        "=" * 60,
        f"Raw Input: {result.raw!r}",
        f"Normalized: {result.normalized!r}",
        f"Symbology Removed: {result.symbology_removed}",
    ]
    
    if result.symbology_identifier:
        lines.append(f"Symbology: {result.symbology_identifier}")
    
    lines.extend([
        f"GS Separators Found: {result.gs_seen}",
        f"Confidence: {result.confidence:.2%}",
        "",
        "Elements:",
        "-" * 40,
    ])
    
    for element in result.elements:
        elem_dict = {
            'ai': element.ai,
            'name': element.name,
            'raw_value': element.raw_value,
            'valid': element.valid,
            'errors': element.errors,
            'meta': element.meta,
        }
        lines.append(format_element(elem_dict))
        lines.append("")
    
    if result.errors:
        lines.extend([
            "Errors:",
            "-" * 40,
        ])
        for error in result.errors:
            lines.append(f"  [{error.code}] {error.message}")
            if error.at_index is not None:
                lines.append(f"    at index: {error.at_index}")
        lines.append("")
    
    if result.warnings:
        lines.extend([
            "Warnings:",
            "-" * 40,
        ])
        for warning in result.warnings:
            lines.append(f"  [{warning.code}] {warning.message}")
        lines.append("")
    
    if show_alternatives and result.alternatives:
        lines.extend([
            "Alternative Parses:",
            "-" * 40,
        ])
        for i, alt in enumerate(result.alternatives, 1):
            lines.append(f"  Alternative {i} (confidence: {alt['confidence']:.2%}):")
            for elem in alt['elements']:
                lines.append(f"    AI({elem['ai']}): {elem['raw_value']!r}")
            if alt.get('notes'):
                lines.append(f"    Notes: {', '.join(alt['notes'])}")
            lines.append("")
    
    return '\n'.join(lines)


def build_simple_json(result: ParseResult) -> dict:
    """Build a simple name->value dict for JSON output."""
    output: dict = {}
    for element in result.elements:
        if element.ai == "17":
            key = "Expiry Date"
        else:
            key = element.name if element.name else f"AI {element.ai}"

        value = element.raw_value
        if element.ai == "17":
            if element.meta.get("date_ddmmyyyy"):
                value = element.meta["date_ddmmyyyy"]
            elif element.meta.get("iso_date"):
                iso = element.meta["iso_date"]
                if len(iso) == 10 and iso[4] == "-" and iso[7] == "-":
                    value = f"{iso[8:10]}/{iso[5:7]}/{iso[0:4]}"
            elif len(element.raw_value) == 6 and element.raw_value.isdigit():
                yy = int(element.raw_value[0:2])
                mm = int(element.raw_value[2:4])
                dd = int(element.raw_value[4:6])
                year = 1900 + yy if yy >= 51 else 2000 + yy
                value = f"{dd:02d}/{mm:02d}/{year:04d}"
        if key in output:
            raise ValueError(f"Duplicate AI field in output: {key}")
        output[key] = value
    return output


def main(argv: Optional[list] = None) -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog='gs1_parser',
        description='Parse GS1 element strings from barcodes'
    )
    
    parser.add_argument(
        'barcode',
        help='Barcode data to parse'
    )
    
    parser.add_argument(
        '--show-alternatives',
        action='store_true',
        help='Show alternative parse results for ambiguous cases'
    )
    
    parser.add_argument(
        '--strict',
        action='store_true',
        help='Enable strict validation mode'
    )
    
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output result as JSON'
    )

    parser.add_argument(
        '--lookup',
        action='store_true',
        help='Lookup GTIN in local database and merge results (JSON only)'
    )

    parser.add_argument(
        '--lookup-db',
        default=None,
        help='Path to gtin_database.json (defaults to package data file)'
    )
    
    parser.add_argument(
        '--no-normalize',
        action='store_true',
        help='Disable separator normalization'
    )
    
    parser.add_argument(
        '--max-alternatives',
        type=int,
        default=5,
        help='Maximum number of alternative parses to return'
    )
    
    args = parser.parse_args(argv)
    
    # Configure options
    options = ParseOptions(
        strict_mode=args.strict,
        normalize_separators=not args.no_normalize,
        max_alternatives=args.max_alternatives,
    )
    
    # Parse input
    result = parse_gs1(args.barcode, options=options)
    
    # Output result
    if args.json:
        output = build_simple_json(result)

        if args.lookup:
            gtin_value = output.get("GTIN") or output.get("GTIN Code")
            db_path = Path(args.lookup_db) if args.lookup_db else None

            if not gtin_value:
                output["_lookup_error"] = "GTIN not found in parsed result"
            else:
                record = lookup_gtin(gtin_value, db_path=db_path)
                if record:
                    for k, v in record.items():
                        if k == "GTIN Code":
                            continue
                        output[k] = v
                else:
                    output["_lookup_error"] = f"GTIN not found in database: {gtin_value}"

        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(format_result(result, show_alternatives=args.show_alternatives))
    
    # Return exit code based on parse success
    return 0 if result.confidence > 0.5 else 1


if __name__ == '__main__':
    sys.exit(main())
