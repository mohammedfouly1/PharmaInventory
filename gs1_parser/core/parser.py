"""
GS1 Barcode Element String Parser

Production-grade parser for GS1 element strings from GS1 DataMatrix,
GS1-128, and GS1 DataBar barcodes.

Features:
- O(n) fast-path parsing for well-formed strings
- DP-based solver for ambiguous cases (missing separators)
- Comprehensive validation per GS1 specifications
- Confidence scoring and alternative parse generation

Based on:
- GS1 General Specifications
- GS1 Barcode Syntax Dictionary
- GS1 Barcode Syntax Tests

Key GS1 Rules:
- Variable-length AIs SHALL be delimited by FNC1/GS unless they are the last element
- FNC1 is transmitted as <GS> (ASCII 29, 0x1D) by scanners
- Fixed-length AIs do not require separators
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Set
from enum import Enum

from .ai_dictionary_loader import (
    load_ai_dictionary,
    AIDictionary,
    AIEntry,
)
from ..validators.validators import (
    validate_check_digit,
    validate_date,
    validate_numeric,
    validate_alphanumeric,
    decode_decimal_value,
    validate_gtin,
    validate_sscc,
    validate_gln,
    ValidationResult,
    CSET82,
    NUMERIC,
)
from .no_separator_parser import parse_gs1_no_separator


class ErrorCode(str, Enum):
    """Error and warning codes."""
    MISSING_SEPARATOR = "MISSING_SEPARATOR"
    AMBIGUOUS_PARSE = "AMBIGUOUS_PARSE"
    UNKNOWN_AI = "UNKNOWN_AI"
    INVALID_LENGTH = "INVALID_LENGTH"
    INVALID_FORMAT = "INVALID_FORMAT"
    INVALID_CHECK_DIGIT = "INVALID_CHECK_DIGIT"
    INVALID_DATE = "INVALID_DATE"
    EXTRA_SEPARATOR = "EXTRA_SEPARATOR"
    INVALID_CHARACTERS = "INVALID_CHARACTERS"
    TRUNCATED_DATA = "TRUNCATED_DATA"


@dataclass
class ParseOptions:
    """
    Configuration options for parsing.
    
    Attributes:
        allow_ambiguous: Allow parsing when separators are missing (use solver)
        max_alternatives: Maximum alternative parses to return
        strict_mode: Fail on any validation error
        normalize_separators: Convert various separator chars to GS
        century_pivot: Year pivot for date century determination
        custom_dictionary: Optional custom AI dictionary
        gs_characters: Set of characters to treat as GS separators
    """
    allow_ambiguous: bool = True
    max_alternatives: int = 5
    strict_mode: bool = False
    normalize_separators: bool = True
    century_pivot: int = 51
    custom_dictionary: Optional[AIDictionary] = None
    gs_characters: Set[str] = field(default_factory=lambda: {
        '\x1d',      # ASCII 29 (standard GS)
        '<GS>',      # Text representation
        '\u001d',    # Unicode GS
        '~',         # Common replacement
        '|',         # Common replacement
        '^',         # Common replacement
    })


@dataclass
class ParseError:
    """Represents a parsing error or warning."""
    code: str
    message: str
    at_index: Optional[int] = None
    ai: Optional[str] = None
    alternatives: Optional[int] = None


@dataclass
class ElementData:
    """
    Represents a parsed GS1 element (AI + value).
    
    Attributes:
        ai: Application Identifier code
        name: Human-readable name/title
        raw_value: Raw extracted value
        value: Processed value (may be decoded)
        valid: Whether validation passed
        errors: List of validation errors
        warnings: List of warnings
        meta: Additional metadata (check digit, date parts, decimal value)
        start_index: Position in original string
        end_index: End position in original string
    """
    ai: str
    name: str
    raw_value: str
    value: Any
    valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)
    start_index: int = 0
    end_index: int = 0


@dataclass
class ParsePath:
    """
    Represents one possible parse path through the input.
    Used by the DP solver for ambiguous cases.
    """
    elements: List[ElementData]
    confidence: float
    notes: List[str] = field(default_factory=list)
    errors: List[ParseError] = field(default_factory=list)
    
    def score(self) -> float:
        """Calculate overall score for this parse path."""
        score = self.confidence
        
        # Penalize errors
        score -= len(self.errors) * 0.1
        
        # Reward valid elements
        valid_count = sum(1 for e in self.elements if e.valid)
        if self.elements:
            score += (valid_count / len(self.elements)) * 0.2
        
        return max(0.0, min(1.0, score))


@dataclass
class ParseResult:
    """
    Complete result of parsing a GS1 element string.
    
    Attributes:
        raw: Original input string
        normalized: Normalized input (separators, whitespace)
        symbology_removed: True if symbology prefix was stripped
        symbology_identifier: The stripped symbology identifier (if any)
        gs_seen: True if GS separators were found
        elements: List of parsed elements
        errors: List of parsing errors
        warnings: List of warnings
        alternatives: Alternative parse results (if ambiguous)
        confidence: Confidence score (0.0 - 1.0)
    """
    raw: str
    normalized: str
    symbology_removed: bool = False
    symbology_identifier: Optional[str] = None
    gs_seen: bool = False
    elements: List[ElementData] = field(default_factory=list)
    errors: List[ParseError] = field(default_factory=list)
    warnings: List[ParseError] = field(default_factory=list)
    alternatives: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'raw': self.raw,
            'normalized': self.normalized,
            'symbology_removed': self.symbology_removed,
            'symbology_identifier': self.symbology_identifier,
            'gs_seen': self.gs_seen,
            'elements': [
                {
                    'ai': e.ai,
                    'name': e.name,
                    'raw_value': e.raw_value,
                    'value': e.value,
                    'valid': e.valid,
                    'errors': e.errors,
                    'warnings': e.warnings,
                    'meta': e.meta,
                }
                for e in self.elements
            ],
            'errors': [
                {
                    'code': e.code,
                    'message': e.message,
                    'at_index': e.at_index,
                    'ai': e.ai,
                    'alternatives': e.alternatives,
                }
                for e in self.errors
            ],
            'warnings': [
                {
                    'code': w.code,
                    'message': w.message,
                    'at_index': w.at_index,
                }
                for w in self.warnings
            ],
            'alternatives': self.alternatives,
            'confidence': self.confidence,
        }


# Symbology identifier patterns (ISO/IEC 15424)
SYMBOLOGY_PATTERNS = [
    (r'^\]d2', 'GS1 DataMatrix'),        # ]d2
    (r'^\]C1', 'GS1-128'),               # ]C1
    (r'^\]e0', 'GS1 DataBar'),           # ]e0
    (r'^\]e1', 'GS1 DataBar Limited'),   # ]e1
    (r'^\]e2', 'GS1 DataBar Expanded'),  # ]e2
    (r'^\]Q3', 'GS1 QR Code'),           # ]Q3
]

# Precompile symbology patterns
SYMBOLOGY_REGEX = [(re.compile(p), name) for p, name in SYMBOLOGY_PATTERNS]


class GS1Parser:
    """
    Main GS1 parser class.
    
    Implements:
    - Fast-path O(n) parsing for well-formed strings
    - DP solver for ambiguous cases
    - Comprehensive validation
    """
    
    def __init__(self, options: Optional[ParseOptions] = None):
        self.options = options or ParseOptions()
        self.dictionary = (
            self.options.custom_dictionary or load_ai_dictionary()
        )
        # Precompile GS pattern for normalization
        self._gs_pattern = self._build_gs_pattern()
    
    def _build_gs_pattern(self) -> re.Pattern:
        """Build regex pattern for GS separator detection/normalization."""
        # Escape special regex chars and build alternation
        escaped = []
        for gs in self.options.gs_characters:
            if gs == '<GS>':
                escaped.append(re.escape(gs))
            else:
                escaped.append(re.escape(gs))
        return re.compile('|'.join(escaped))
    
    def _strip_symbology(self, text: str) -> Tuple[str, bool, Optional[str]]:
        """
        Strip symbology identifier prefix if present.
        
        Returns:
            (stripped_text, was_removed, identifier_name)
        """
        for pattern, name in SYMBOLOGY_REGEX:
            match = pattern.match(text)
            if match:
                return text[match.end():], True, name
        return text, False, None
    
    def _normalize(self, text: str) -> Tuple[str, bool]:
        """
        Normalize input string.
        
        - Converts various GS representations to standard \x1d
        - Trims whitespace
        
        Returns:
            (normalized_text, gs_found)
        """
        # Check if any GS characters present
        gs_found = bool(self._gs_pattern.search(text))
        
        if self.options.normalize_separators:
            # Replace all GS variants with standard ASCII 29
            text = self._gs_pattern.sub('\x1d', text)
        
        # Trim whitespace
        text = text.strip()
        
        return text, gs_found
    
    def _validate_element(
        self,
        ai_entry: AIEntry,
        value: str
    ) -> Tuple[Any, ValidationResult]:
        """
        Validate an element value according to AI specifications.
        
        Returns:
            (processed_value, validation_result)
        """
        result = ValidationResult(valid=True)
        processed_value = value
        
        # Length validation
        if ai_entry.fixed_length:
            if len(value) != ai_entry.fixed_length:
                result.valid = False
                result.errors.append(
                    f"Length must be {ai_entry.fixed_length}, got {len(value)}"
                )
        else:
            if len(value) < ai_entry.min_length:
                result.valid = False
                result.errors.append(
                    f"Length {len(value)} below minimum {ai_entry.min_length}"
                )
            if len(value) > ai_entry.max_length:
                result.valid = False
                result.errors.append(
                    f"Length {len(value)} exceeds maximum {ai_entry.max_length}"
                )
        
        # Data type validation
        if ai_entry.data_type == 'N':
            if not value.isdigit():
                result.valid = False
                result.errors.append("Value must be numeric")
        else:
            # Alphanumeric - check character set
            invalid = set(value) - CSET82
            if invalid:
                result.valid = False
                result.errors.append(f"Invalid characters: {invalid}")
        
        # Check digit validation (GTIN, SSCC, GLN, etc.)
        if ai_entry.check_digit and value.isdigit() and len(value) >= 2:
            check_result = validate_check_digit(value, ai_entry.ai)
            if not check_result.valid:
                result.valid = False
                result.errors.extend(check_result.errors)
            result.meta.update(check_result.meta)
        
        # Date validation
        if ai_entry.date_format:
            date_result = validate_date(
                value,
                ai_entry.date_format,
                self.options.century_pivot
            )
            if not date_result.valid:
                result.valid = False
                result.errors.extend(date_result.errors)
            result.meta.update(date_result.meta)
            if date_result.valid and 'date_ddmmyyyy' in date_result.meta:
                processed_value = date_result.meta['date_ddmmyyyy']
        
        # Decimal position handling
        if ai_entry.decimal_positions is not None and value.isdigit():
            try:
                float_val, formatted = decode_decimal_value(
                    value, ai_entry.decimal_positions
                )
                result.meta['decimal_value'] = float_val
                result.meta['decimal_formatted'] = formatted
                result.meta['decimal_positions'] = ai_entry.decimal_positions
                processed_value = float_val
            except ValueError as e:
                result.errors.append(f"Decimal decode error: {e}")
        
        # Regex validation (if provided and not already failing)
        if ai_entry.regex and result.valid:
            try:
                if not re.match(ai_entry.regex, value):
                    result.valid = False
                    result.errors.append("Value does not match expected format")
            except re.error:
                pass  # Skip invalid regex
        
        return processed_value, result
    
    def _parse_fast_path(
        self,
        text: str,
        start_index: int = 0,
        gs_seen: bool = False
    ) -> Tuple[List[ElementData], List[ParseError], bool]:
        """
        Fast-path parsing for well-formed strings.
        
        Uses trie for longest-match AI lookup.
        Handles fixed and variable-length AIs.
        
        Returns:
            (elements, errors, needs_solver)
        """
        elements = []
        errors = []
        needs_solver = False
        pos = start_index
        
        while pos < len(text):
            # Skip GS separators
            if text[pos] == '\x1d':
                # Check if this is superfluous (after fixed-length)
                if elements and not elements[-1].meta.get('_separator_required', True):
                    # Tolerate GS after fixed-length if another valid AI follows
                    next_pos = pos + 1
                    next_entry = None
                    if next_pos < len(text):
                        next_entry, _ = self.dictionary.find_longest_match(text, next_pos)
                    if next_pos >= len(text) or not next_entry:
                        errors.append(ParseError(
                            code=ErrorCode.EXTRA_SEPARATOR,
                            message="Superfluous GS after fixed-length AI",
                            at_index=pos
                        ))
                pos += 1
                continue
            
            # Find longest matching AI
            ai_entry, ai_len = self.dictionary.find_longest_match(text, pos)
            
            if not ai_entry:
                # Unknown AI - try to recover or fail
                errors.append(ParseError(
                    code=ErrorCode.UNKNOWN_AI,
                    message=f"Unknown AI at position {pos}: {text[pos:pos+4]}",
                    at_index=pos
                ))
                # Skip to next GS or end
                next_gs = text.find('\x1d', pos)
                pos = next_gs + 1 if next_gs != -1 else len(text)
                continue
            
            ai_start = pos
            pos += ai_len  # Move past AI
            
            # Determine data length
            if ai_entry.fixed_length:
                # Fixed length - take exact number of characters
                data_len = ai_entry.fixed_length
                if pos + data_len > len(text):
                    errors.append(ParseError(
                        code=ErrorCode.TRUNCATED_DATA,
                        message=f"Truncated data for AI {ai_entry.ai}",
                        at_index=pos,
                        ai=ai_entry.ai
                    ))
                    data_len = len(text) - pos
                
                value = text[pos:pos + data_len]
                pos += data_len
                
            else:
                # Variable length - find end
                # Look for GS separator or end of string
                next_gs = text.find('\x1d', pos)
                
                if next_gs != -1:
                    # GS found - take until GS
                    value = text[pos:next_gs]
                    pos = next_gs + 1
                else:
                    # No GS - this should be the last element
                    # Or we have a missing separator issue
                    remaining = text[pos:]

                    # Check if there's another valid AI hiding in the remaining data.
                    # This indicates possible ambiguity even when within max length.
                    found_next_ai = False
                    max_check = min(ai_entry.max_length, len(remaining))
                    for check_len in range(ai_entry.min_length, max_check):
                        potential_next = remaining[check_len:]
                        if len(potential_next) >= 2:
                            next_entry, _ = self.dictionary.find_longest_match(potential_next, 0)
                            if next_entry:
                                # Potential ambiguity - need solver
                                needs_solver = True
                                found_next_ai = True
                                break
                    
                    if found_next_ai:
                        if gs_seen:
                            errors.append(ParseError(
                                code=ErrorCode.MISSING_SEPARATOR,
                                message=f"AI({ai_entry.ai}) variable-length followed by another AI without GS",
                                at_index=pos,
                                ai=ai_entry.ai
                            ))
                        # Take up to max length for now
                        value = remaining[:ai_entry.max_length]
                        pos += ai_entry.max_length
                    else:
                        # Seems to be last element
                        value = remaining
                        pos = len(text)
            
            # Validate the element
            processed_value, validation = self._validate_element(ai_entry, value)
            
            element = ElementData(
                ai=ai_entry.ai,
                name=ai_entry.title,
                raw_value=value,
                value=processed_value,
                valid=validation.valid,
                errors=validation.errors,
                warnings=[],
                meta=validation.meta,
                start_index=ai_start,
                end_index=pos
            )
            
            # Store separator requirement for next iteration
            element.meta['_separator_required'] = ai_entry.separator_required
            
            elements.append(element)
        
        return elements, errors, needs_solver
    
    def _solve_ambiguous(
        self,
        text: str,
        start_index: int = 0,
        gs_seen: bool = False
    ) -> List[ParsePath]:
        """
        DP solver for ambiguous cases (missing separators).
        
        Uses dynamic programming with aggressive pruning:
        - Regex validation
        - Data type checking
        - Date validation
        - Check digit validation
        
        Returns:
            List of possible parse paths, sorted by confidence
        """
        # Memoization cache: position -> list of (ParsePath, remaining_text)
        memo: Dict[int, List[ParsePath]] = {}
        
        def solve(pos: int, depth: int = 0) -> List[ParsePath]:
            """Recursively find all valid parse paths from position."""
            if pos >= len(text):
                return [ParsePath(elements=[], confidence=1.0)]
            
            if pos in memo:
                return memo[pos]
            
            # Limit recursion depth
            if depth > 50:
                return []
            
            paths = []
            
            # Skip GS if present
            if text[pos] == '\x1d':
                sub_paths = solve(pos + 1, depth)
                for sp in sub_paths:
                    # Bonus for having proper separator
                    sp.confidence = min(1.0, sp.confidence + 0.05)
                paths.extend(sub_paths)
            
            # Try all matching AIs
            ai_entry, ai_len = self.dictionary.find_longest_match(text, pos)
            if not ai_entry:
                memo[pos] = paths
                return paths
            
            # Also try shorter AI matches (for ambiguity)
            ai_matches = [(ai_entry, ai_len)]
            
            # Check for shorter matches (3-digit AI when 4-digit matched, etc.)
            if ai_len > 2:
                for shorter_len in range(ai_len - 1, 1, -1):
                    shorter_ai = text[pos:pos + shorter_len]
                    shorter_entry = self.dictionary.get(shorter_ai)
                    if shorter_entry:
                        ai_matches.append((shorter_entry, shorter_len))
            
            def value_has_possible_ai(value: str, min_len: int) -> bool:
                for check_len in range(min_len, len(value) - 1):
                    potential_next = value[check_len:]
                    next_entry, _ = self.dictionary.find_longest_match(potential_next, 0)
                    if next_entry:
                        return True
                return False

            for ai_entry, ai_len in ai_matches:
                data_start = pos + ai_len
                
                if ai_entry.fixed_length:
                    # Fixed length - deterministic
                    lengths = [ai_entry.fixed_length]
                else:
                    # Variable length - try all valid lengths
                    max_remain = len(text) - data_start
                    max_len = min(ai_entry.max_length, max_remain)
                    min_len = max(ai_entry.min_length, 1)
                    if gs_seen:
                        lengths = range(min_len, max_len + 1)
                    else:
                        lengths = range(max_len, min_len - 1, -1)
                
                for data_len in lengths:
                    if data_start + data_len > len(text):
                        continue
                    
                    value = text[data_start:data_start + data_len]
                    end_pos = data_start + data_len
                    
                    # Quick validation - prune invalid branches
                    if ai_entry.data_type == 'N' and not value.isdigit():
                        continue
                    
                    # Validate the element
                    processed_value, validation = self._validate_element(ai_entry, value)
                    
                    # Skip paths with critical validation failures
                    if not validation.valid and self.options.strict_mode:
                        continue
                    
                    # Check if next position could start a valid AI
                    # (or is GS or end of string)
                    if end_pos < len(text) and text[end_pos] != '\x1d':
                        next_ai, _ = self.dictionary.find_longest_match(text, end_pos)
                        if not next_ai:
                            # No valid AI at next position - this length doesn't work
                            continue
                    
                    # Calculate confidence for this element
                    elem_confidence = 1.0 if validation.valid else 0.7
                    
                    # Variable-length without separator: prefer longer valid data
                    if (ai_entry.separator_required and
                        end_pos < len(text) and
                        text[end_pos] != '\x1d'):
                        max_len = max(ai_entry.max_length, 1)
                        length_ratio = min(1.0, data_len / max_len)
                        elem_confidence *= (0.8 + 0.2 * length_ratio)
                    
                    # Penalty if variable-length consumes trailing data that could be another AI
                    if (not ai_entry.fixed_length and end_pos == len(text) and
                            value_has_possible_ai(value, ai_entry.min_length)):
                        elem_confidence *= 0.7
                    
                    element = ElementData(
                        ai=ai_entry.ai,
                        name=ai_entry.title,
                        raw_value=value,
                        value=processed_value,
                        valid=validation.valid,
                        errors=validation.errors,
                        warnings=[],
                        meta=validation.meta,
                        start_index=pos,
                        end_index=end_pos
                    )
                    
                    # Recurse for remaining text
                    sub_paths = solve(end_pos, depth + 1)
                    
                    for sp in sub_paths:
                        new_path = ParsePath(
                            elements=[element] + sp.elements,
                            confidence=elem_confidence * sp.confidence,
                            notes=sp.notes.copy(),
                            errors=sp.errors.copy()
                        )
                        
                        # Note missing separator
                        if (ai_entry.separator_required and
                            end_pos < len(text) and
                            text[end_pos] != '\x1d'):
                            new_path.notes.append(
                                f"Guessed boundary for AI({ai_entry.ai})"
                            )
                        
                        paths.append(new_path)
            
            # Limit paths to prevent explosion
            paths.sort(key=lambda p: p.score(), reverse=True)
            paths = paths[:self.options.max_alternatives * 2]
            
            memo[pos] = paths
            return paths
        
        all_paths = solve(start_index)
        
        # Sort by score and return top N
        all_paths.sort(key=lambda p: p.score(), reverse=True)
        return all_paths[:self.options.max_alternatives + 1]
    
    def parse(self, text: str) -> ParseResult:
        """
        Parse a GS1 element string.
        
        Args:
            text: Raw barcode data
        
        Returns:
            ParseResult with all parsed elements and validation
        """
        # Strip symbology identifier
        stripped, symbology_removed, symbology_id = self._strip_symbology(text)
        
        # Normalize
        normalized, gs_seen = self._normalize(stripped)
        
        result = ParseResult(
            raw=text,
            normalized=normalized,
            symbology_removed=symbology_removed,
            symbology_identifier=symbology_id,
            gs_seen=gs_seen
        )
        
        if not normalized:
            result.errors.append(ParseError(
                code=ErrorCode.INVALID_FORMAT,
                message="Empty input after normalization"
            ))
            result.confidence = 0.0
            return result
        
        # Try fast path first
        elements, errors, needs_solver = self._parse_fast_path(
            normalized, gs_seen=gs_seen
        )
        
        if not needs_solver:
            # Fast path succeeded
            result.elements = elements
            result.errors = errors
            
            # Calculate confidence
            if errors:
                result.confidence = 0.9 - (len(errors) * 0.05)
            valid_count = sum(1 for e in elements if e.valid)
            if elements:
                result.confidence *= (0.8 + 0.2 * (valid_count / len(elements)))
            
        elif self.options.allow_ambiguous:
            # Need to use solver
            paths = self._solve_ambiguous(normalized, gs_seen=gs_seen)
            
            if paths:
                best_path = paths[0]
                result.elements = best_path.elements
                result.confidence = best_path.score()
                
                # Add notes about guessed boundaries
                report_ambiguity = len(paths) > 1
                report_notes = gs_seen or report_ambiguity
                if report_notes:
                    for note in best_path.notes:
                        result.warnings.append(ParseError(
                            code=ErrorCode.MISSING_SEPARATOR,
                            message=note
                        ))
                
                # Add alternatives if multiple valid parses
                if len(paths) > 1:
                    result.errors.append(ParseError(
                        code=ErrorCode.AMBIGUOUS_PARSE,
                        message="Multiple valid parses found; returning best with alternatives",
                        alternatives=len(paths) - 1
                    ))
                    
                    for alt_path in paths[1:self.options.max_alternatives + 1]:
                        result.alternatives.append({
                            'confidence': alt_path.score(),
                            'elements': [
                                {
                                    'ai': e.ai,
                                    'name': e.name,
                                    'raw_value': e.raw_value,
                                    'value': e.value,
                                    'valid': e.valid,
                                }
                                for e in alt_path.elements
                            ],
                            'notes': alt_path.notes
                        })
            else:
                # No valid parse found
                result.errors = errors
                result.errors.append(ParseError(
                    code=ErrorCode.INVALID_FORMAT,
                    message="No valid parse found"
                ))
                result.confidence = 0.0
        else:
            # Ambiguous but solver disabled
            result.elements = elements
            result.errors = errors
            result.confidence = 0.5
        
        return result


def parse_gs1(
    input_text: str,
    *,
    options: Optional[ParseOptions] = None
) -> ParseResult:
    """
    Parse a GS1 element string from a barcode.
    
    Main entry point for the parser.
    
    Args:
        input_text: Raw barcode data string
        options: Optional parsing configuration
    
    Returns:
        ParseResult containing all parsed elements and validation info
    
    Examples:
        >>> result = parse_gs1("0106285096000842172901310HP3P217897906672")
        >>> print(result.elements[0].ai)  # "01"
        >>> print(result.elements[0].value)  # "06285096000842"
    """
    parser = GS1Parser(options)

    # Detect separators before choosing parsing strategy
    stripped, symbology_removed, symbology_id = parser._strip_symbology(input_text)
    normalized, gs_seen = parser._normalize(stripped)

    if not gs_seen:
        ns_result = parse_gs1_no_separator(
            normalized,
            max_alternatives=parser.options.max_alternatives,
        )
        return _convert_no_separator_result(
            ns_result,
            parser=parser,
            raw=input_text,
            normalized=normalized,
            symbology_removed=symbology_removed,
            symbology_id=symbology_id,
            gs_seen=gs_seen,
        )

    return parser.parse(input_text)


def _convert_no_separator_result(
    ns_result,
    *,
    parser: GS1Parser,
    raw: str,
    normalized: str,
    symbology_removed: bool,
    symbology_id: Optional[str],
    gs_seen: bool,
) -> ParseResult:
    """Convert NoSeparatorParseResult into ParseResult for unified CLI/API output."""
    result = ParseResult(
        raw=raw,
        normalized=normalized,
        symbology_removed=symbology_removed,
        symbology_identifier=symbology_id,
        gs_seen=gs_seen,
    )

    # Elements
    for elem in ns_result.best_parse:
        ai_entry = parser.dictionary.get(elem.ai)
        name = ai_entry.title if ai_entry else f"AI {elem.ai}"

        result.elements.append(
            ElementData(
                ai=elem.ai,
                name=name,
                raw_value=elem.raw_value,
                value=elem.normalized_value,
                valid=elem.valid,
                errors=elem.validation_errors,
                warnings=[],
                meta=elem.validation_meta,
                start_index=elem.start_pos,
                end_index=elem.end_pos,
            )
        )

    # Warnings / Errors
    if "MISSING_SEPARATOR" in ns_result.flags:
        result.warnings.append(ParseError(
            code=ErrorCode.MISSING_SEPARATOR,
            message="Input has no separators; parsed with no-separator solver",
        ))

    if "AMBIGUOUS_PARSE" in ns_result.flags:
        result.errors.append(ParseError(
            code=ErrorCode.AMBIGUOUS_PARSE,
            message="Multiple valid parses found; returning best with alternatives",
            alternatives=len(ns_result.alternatives),
        ))

    if "NO_VALID_PARSE" in ns_result.flags:
        result.errors.append(ParseError(
            code=ErrorCode.INVALID_FORMAT,
            message="No valid parse found",
        ))

    # Alternatives
    best_score = ns_result.best_score if ns_result.best_score > 0 else None
    for alt_elements, alt_score, reasoning in ns_result.alternatives:
        confidence = 0.0
        if best_score:
            confidence = max(0.0, min(1.0, alt_score / best_score))

        result.alternatives.append({
            "confidence": confidence,
            "elements": [
                {
                    "ai": e.ai,
                    "name": (parser.dictionary.get(e.ai).title if parser.dictionary.get(e.ai) else f"AI {e.ai}"),
                    "raw_value": e.raw_value,
                    "value": e.normalized_value,
                    "valid": e.valid,
                }
                for e in alt_elements
            ],
            "notes": reasoning,
        })

    result.confidence = ns_result.confidence
    return result
