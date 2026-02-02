"""
GS1 Barcode Element String Parser

A production-grade, high-performance Python module for parsing GS1 element strings
from barcodes (GS1 DataMatrix, GS1-128, GS1 DataBar).

Based on GS1 General Specifications and the GS1 Barcode Syntax Dictionary.
"""

from .core.parser import parse_gs1, ParseOptions, ParseResult
from .core.ai_dictionary_loader import load_ai_dictionary, AIEntry, AIDictionary
from .core.no_separator_parser import (
    parse_gs1_no_separator,
    NoSeparatorParseResult,
    ParsedElement,
)
from .validators.validators import (
    validate_check_digit,
    validate_date,
    validate_numeric,
    validate_alphanumeric,
)
from .formatters.json_formatter import (
    parse_gs1_to_json,
    parse_gs1_to_dict,
    prepare_for_lookup,
)
from .lookup import lookup_gtin

__version__ = "1.0.0"
__all__ = [
    "parse_gs1",
    "ParseOptions",
    "ParseResult",
    "load_ai_dictionary",
    "AIEntry",
    "AIDictionary",
    "validate_check_digit",
    "validate_date",
    "validate_numeric",
    "validate_alphanumeric",
    "parse_gs1_no_separator",
    "NoSeparatorParseResult",
    "ParsedElement",
    "parse_gs1_to_json",
    "parse_gs1_to_dict",
    "prepare_for_lookup",
    "lookup_gtin",
]
