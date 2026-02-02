"""
JSON Formatter for GS1 No-Separator Parser

Provides clean, production-ready JSON output with:
- Human-readable field names
- Date formatting (dd/mm/yyyy)
- Only best parse result (no warnings/errors)
- Ready for GTIN lookup integration
"""

from __future__ import annotations

import json
from typing import Dict, Any, Optional
from datetime import datetime

from .no_separator_parser import (
    NoSeparatorParseResult,
    ParsedElement,
)


# AI Code to Human-Readable Name Mapping
AI_FIELD_NAMES = {
    "01": "GTIN Code",
    "17": "Expiry Date",
    "10": "Batch/Lot Number",
    "21": "Serial Number",
    "00": "SSCC",
    "11": "Production Date",
    "13": "Packaging Date",
    "15": "Best Before Date",
    "16": "Sell By Date",
    "20": "Variant",
    "22": "Consumer Product Variant",
    "235": "Third Party Controlled",
    "240": "Additional Product Identification",
    "241": "Customer Part Number",
    "242": "Made-to-Order Variation Number",
    "243": "Packaging Component Number",
    "250": "Secondary Serial Number",
    "251": "Reference to Source Entity",
    "253": "Global Document Type Identifier",
    "254": "GLN Extension Component",
    "255": "Global Coupon Number",
    "30": "Variable Count",
    "37": "Count of Trade Items",
    "90": "Internal Company Code 1",
    "91": "Internal Company Code 2",
    "92": "Internal Company Code 3",
    "93": "Internal Company Code 4",
    "94": "Internal Company Code 5",
    "95": "Internal Company Code 6",
    "96": "Internal Company Code 7",
    "97": "Internal Company Code 8",
    "98": "Internal Company Code 9",
    "99": "Internal Company Code 10",
}


def format_date_ddmmyyyy(date_value: str, validation_meta: Dict[str, Any]) -> str:
    """
    Format date as dd/mm/yyyy.

    Handles:
    - Normal dates: YYMMDD -> dd/mm/yyyy
    - Unknown day (DD=00): -> XX/mm/yyyy
    """
    if validation_meta.get('unknown_day', False):
        # Unknown day - format as XX/mm/yyyy
        year = validation_meta.get('year', '????')
        month = validation_meta.get('month', '??')
        return f"XX/{month:02d}/{year:04d}" if isinstance(month, int) else f"XX/{month}/{year}"

    # Normal date
    if 'date_ddmmyyyy' in validation_meta:
        return validation_meta['date_ddmmyyyy']

    # Fallback: parse from raw value (YYMMDD)
    if len(date_value) == 6:
        yy = int(date_value[0:2])
        mm = int(date_value[2:4])
        dd = int(date_value[4:6])

        # Century determination (51+ = 19xx, <51 = 20xx)
        year = 1900 + yy if yy >= 51 else 2000 + yy

        return f"{dd:02d}/{mm:02d}/{year:04d}"

    return date_value


def format_gs1_result_json(
    result: NoSeparatorParseResult,
    include_confidence: bool = False,
    include_raw_values: bool = False
) -> str:
    """
    Format GS1 parse result as clean JSON.

    Args:
        result: Parse result from parse_gs1_no_separator()
        include_confidence: Include confidence score in output (default: False)
        include_raw_values: Include raw values alongside formatted (default: False)

    Returns:
        JSON string with clean, production-ready output
    """
    output: Dict[str, Any] = {}

    # Process each parsed element
    for elem in result.best_parse:
        field_name = AI_FIELD_NAMES.get(elem.ai, f"AI({elem.ai})")

        # Format value based on AI type
        if elem.ai == "17":  # Expiry Date
            formatted_value = format_date_ddmmyyyy(elem.raw_value, elem.validation_meta)
        elif elem.ai in ["11", "13", "15", "16"]:  # Other dates
            formatted_value = format_date_ddmmyyyy(elem.raw_value, elem.validation_meta)
        else:
            # Use normalized value or raw value
            formatted_value = elem.normalized_value if elem.normalized_value != elem.raw_value else elem.raw_value

        # Add to output
        if include_raw_values and elem.ai in ["17", "11", "13", "15", "16"]:
            # For dates, include both formatted and raw
            output[field_name] = {
                "formatted": formatted_value,
                "raw": elem.raw_value
            }
        else:
            output[field_name] = formatted_value

    # Add confidence if requested
    if include_confidence:
        output["_confidence"] = round(result.confidence * 100, 2)

    return json.dumps(output, ensure_ascii=False, indent=2)


def parse_gs1_to_json(
    barcode_data: str,
    include_confidence: bool = False,
    include_raw_values: bool = False,
    **parse_options
) -> str:
    """
    Parse GS1 barcode and return clean JSON output.

    This is the main entry point for production use.

    Args:
        barcode_data: Raw barcode string (no separators)
        include_confidence: Include confidence score (default: False)
        include_raw_values: Include raw values (default: False)
        **parse_options: Additional options for parse_gs1_no_separator()

    Returns:
        JSON string with parsed fields

    Example:
        >>> json_output = parse_gs1_to_json("01062867400002491728043010GB2C2171490437969853")
        >>> print(json_output)
        {
          "GTIN Code": "06286740000249",
          "Expiry Date": "30/04/2028",
          "Batch/Lot Number": "GB2C",
          "Serial Number": "71490437969853"
        }
    """
    from .no_separator_parser import parse_gs1_no_separator

    result = parse_gs1_no_separator(barcode_data, **parse_options)

    return format_gs1_result_json(
        result,
        include_confidence=include_confidence,
        include_raw_values=include_raw_values
    )


def parse_gs1_to_dict(
    barcode_data: str,
    include_confidence: bool = False,
    **parse_options
) -> Dict[str, Any]:
    """
    Parse GS1 barcode and return dictionary.

    Args:
        barcode_data: Raw barcode string (no separators)
        include_confidence: Include confidence score (default: False)
        **parse_options: Additional options for parse_gs1_no_separator()

    Returns:
        Dictionary with parsed fields
    """
    json_str = parse_gs1_to_json(
        barcode_data,
        include_confidence=include_confidence,
        **parse_options
    )
    return json.loads(json_str)


def prepare_for_lookup(barcode_data: str) -> Dict[str, Any]:
    """
    Parse barcode and prepare for GTIN lookup integration.

    Returns dictionary with:
    - GTIN Code (for database lookup)
    - All other parsed fields
    - Placeholder fields for future lookup results

    Args:
        barcode_data: Raw barcode string (no separators)

    Returns:
        Dictionary ready for GTIN lookup integration

    Example:
        >>> result = prepare_for_lookup("01062867400002491728043010GB2C2171490437969853")
        >>> print(result)
        {
          "GTIN Code": "06286740000249",
          "Expiry Date": "30/04/2028",
          "Batch/Lot Number": "GB2C",
          "Serial Number": "71490437969853",
          "Drug Trade Name": null,
          "Scientific Name": null,
          "Pharmaceutical Form": null,
          "Number of Subunits": null
        }
    """
    parsed = parse_gs1_to_dict(barcode_data, include_confidence=False)

    # Add placeholder fields for lookup results
    lookup_fields = {
        "Drug Trade Name": None,
        "Scientific Name": None,
        "Pharmaceutical Form": None,
        "Number of Subunits": None
    }

    # Merge: parsed fields first, then lookup placeholders
    return {**parsed, **lookup_fields}
