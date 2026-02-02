"""
GS1 No-Separator Parser

Specialized parser for GS1 element strings that are ALWAYS missing separators.
Uses scoring-based beam search to handle ambiguity in variable-length AIs.

Based on:
- GS1 AI Reference: https://ref.gs1.org/ai/
- Healthcare barcode specs (SFDA)
- Real-world pharmaceutical packaging data

Key Innovation:
- Scoring system that deprioritizes internal AIs (90-99) when they could be
  part of (21) Serial or (10) Batch/Lot
- Detection of embedded fixed AIs inside variable fields (e.g., "17" inside "21")
- Deterministic best-parse selection with alternatives and confidence scoring
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any, Set
from enum import Enum
import heapq

from ..validators.validators import (
    calculate_check_digit_mod10,
    validate_date,
    ValidationResult,
)


class PriorityClass(str, Enum):
    """AI priority classification for no-separator parsing."""
    CORE = "core"          # 01, 17, 10, 21
    INTERNAL = "internal"  # 90-99
    OTHER = "other"        # Everything else


@dataclass
class AIDefinition:
    """Definition of a GS1 Application Identifier for no-separator parsing."""
    ai: str
    title: str
    fixed_length: Optional[int]  # None if variable
    min_length: int
    max_length: int
    data_type: str  # 'N' or 'X'
    regex_pattern: str
    priority_class: PriorityClass
    check_digit: bool = False
    date_format: Optional[str] = None


@dataclass
class ParsedElement:
    """A single parsed AI element."""
    ai: str
    raw_value: str
    normalized_value: Any
    valid: bool
    validation_errors: List[str] = field(default_factory=list)
    validation_meta: Dict[str, Any] = field(default_factory=dict)
    start_pos: int = 0
    end_pos: int = 0


@dataclass
class ParseCandidate:
    """A candidate parse path through the input string."""
    elements: List[ParsedElement]
    score: float
    position: int  # Current position in input string
    consumed_all: bool
    reasoning: List[str] = field(default_factory=list)

    def __lt__(self, other):
        """For heap operations - higher scores are better."""
        return self.score > other.score


@dataclass
class NoSeparatorParseResult:
    """Result from no-separator parsing."""
    input_string: str
    best_parse: List[ParsedElement]
    best_score: float
    alternatives: List[Tuple[List[ParsedElement], float, List[str]]]  # (elements, score, reasoning)
    confidence: float  # 0.0 - 1.0
    flags: List[str]  # MISSING_SEPARATOR, AMBIGUOUS_PARSE, etc.
    warnings: List[str]


# AI Catalog for no-separator parsing
AI_CATALOG: Dict[str, AIDefinition] = {
    "01": AIDefinition(
        ai="01",
        title="GTIN",
        fixed_length=14,
        min_length=14,
        max_length=14,
        data_type="N",
        regex_pattern=r"^\d{14}$",
        priority_class=PriorityClass.CORE,
        check_digit=True,
    ),
    "17": AIDefinition(
        ai="17",
        title="USE BY or EXPIRY",
        fixed_length=6,
        min_length=6,
        max_length=6,
        data_type="N",
        regex_pattern=r"^\d{6}$",
        priority_class=PriorityClass.CORE,
        date_format="YYMMDD",
    ),
    "10": AIDefinition(
        ai="10",
        title="BATCH/LOT",
        fixed_length=None,
        min_length=1,
        max_length=20,
        data_type="X",
        regex_pattern=r"^[A-Z0-9\-/]+$",  # GS1 allows alphanumeric + some symbols
        priority_class=PriorityClass.CORE,
    ),
    "21": AIDefinition(
        ai="21",
        title="SERIAL",
        fixed_length=None,
        min_length=1,
        max_length=20,
        data_type="X",
        regex_pattern=r"^[A-Z0-9\-/]+$",  # GS1 charset
        priority_class=PriorityClass.CORE,
    ),
}

# Add internal AIs (90-99)
for i in range(90, 100):
    ai_code = str(i)
    AI_CATALOG[ai_code] = AIDefinition(
        ai=ai_code,
        title=f"INTERNAL {ai_code}",
        fixed_length=None,
        min_length=1,
        max_length=30,
        data_type="X",
        regex_pattern=r"^.+$",
        priority_class=PriorityClass.INTERNAL,
    )


class NoSeparatorParser:
    """
    GS1 Parser for strings with NO separators.

    Uses beam search with scoring to find the best parse.
    """

    def __init__(
        self,
        beam_width: int = 200,
        max_alternatives: int = 5,
        vendor_whitelist_internal_ais: Set[str] = None,
    ):
        self.beam_width = beam_width
        self.max_alternatives = max_alternatives
        self.vendor_whitelist = vendor_whitelist_internal_ais or set()

        # Precompile regex patterns
        self._patterns = {
            ai: re.compile(defn.regex_pattern, re.IGNORECASE)
            for ai, defn in AI_CATALOG.items()
        }

    def parse(self, input_string: str) -> NoSeparatorParseResult:
        """
        Parse a GS1 element string with no separators.

        Args:
            input_string: Raw barcode data (no separators)

        Returns:
            NoSeparatorParseResult with best parse and alternatives
        """
        # Beam search to find candidate parses
        candidates = self._beam_search(input_string)

        if not candidates:
            return NoSeparatorParseResult(
                input_string=input_string,
                best_parse=[],
                best_score=-float('inf'),
                alternatives=[],
                confidence=0.0,
                flags=["NO_VALID_PARSE"],
                warnings=["No valid parse found"],
            )

        # Sort by score (descending)
        candidates.sort(key=lambda c: c.score, reverse=True)

        best = candidates[0]

        # Calculate confidence
        if not best.elements:
            # Empty parse = no confidence
            confidence = 0.0
        elif len(candidates) > 1:
            score_diff = best.score - candidates[1].score
            # Softmax-like confidence
            confidence = min(1.0, max(0.5, 1.0 / (1.0 + 50.0 / (score_diff + 1))))
        else:
            confidence = 0.95

        # Determine flags
        flags = ["MISSING_SEPARATOR"]  # Always true in this scenario

        # Check if parse is empty or invalid
        if not best.elements:
            flags.append("NO_VALID_PARSE")

        if len(candidates) > 1 and (best.score - candidates[1].score) < 40:
            flags.append("AMBIGUOUS_PARSE")

        # Collect alternatives
        alternatives = [
            (c.elements, c.score, c.reasoning)
            for c in candidates[1:self.max_alternatives + 1]
        ]

        return NoSeparatorParseResult(
            input_string=input_string,
            best_parse=best.elements,
            best_score=best.score,
            alternatives=alternatives,
            confidence=confidence,
            flags=flags,
            warnings=[],
        )

    def _beam_search(self, input_string: str) -> List[ParseCandidate]:
        """
        Beam search to enumerate candidate parses.

        Returns:
            List of complete ParseCandidate objects that consumed entire input
        """
        # Initial state
        initial = ParseCandidate(
            elements=[],
            score=0.0,
            position=0,
            consumed_all=False,
            reasoning=[],
        )

        beam = [initial]
        complete_parses = []

        # Iterative beam search
        max_iterations = 20  # Safety limit
        iteration = 0

        while beam and iteration < max_iterations:
            iteration += 1
            new_beam = []

            for candidate in beam:
                if candidate.position >= len(input_string):
                    # Complete parse
                    candidate.consumed_all = True
                    complete_parses.append(candidate)
                    continue

                # Try to extend this candidate
                extensions = self._get_extensions(input_string, candidate)
                new_beam.extend(extensions)

            # Keep top beam_width candidates
            new_beam.sort(key=lambda c: c.score, reverse=True)
            beam = new_beam[:self.beam_width]

        # Return only complete parses
        complete = [c for c in complete_parses if c.consumed_all]
        return complete

    def _get_extensions(
        self,
        input_string: str,
        candidate: ParseCandidate
    ) -> List[ParseCandidate]:
        """
        Get all possible extensions of a candidate parse from current position.
        """
        extensions = []
        pos = candidate.position
        remaining = input_string[pos:]

        # Try each AI
        for ai_code, ai_def in AI_CATALOG.items():
            # Check if AI matches at current position
            if not remaining.startswith(ai_code):
                continue

            data_start = pos + len(ai_code)

            # Fixed-length AI
            if ai_def.fixed_length is not None:
                data_end = data_start + ai_def.fixed_length
                if data_end > len(input_string):
                    continue  # Not enough data

                value = input_string[data_start:data_end]

                # Validate and create element
                element, valid = self._validate_element(ai_def, value, pos, data_end)

                if not valid and ai_def.check_digit:
                    # Invalid check digit = invalid parse
                    continue

                # Create new candidate
                new_candidate = ParseCandidate(
                    elements=candidate.elements + [element],
                    score=candidate.score,
                    position=data_end,
                    consumed_all=False,
                    reasoning=candidate.reasoning.copy(),
                )

                # Score this extension
                self._score_extension(new_candidate, element, input_string)

                extensions.append(new_candidate)

            # Variable-length AI
            else:
                # Try multiple lengths
                lengths_to_try = self._get_variable_lengths_to_try(
                    input_string, data_start, ai_def, candidate
                )

                for data_len in lengths_to_try:
                    data_end = data_start + data_len
                    if data_end > len(input_string):
                        continue

                    value = input_string[data_start:data_end]

                    # Validate
                    element, valid = self._validate_element(ai_def, value, pos, data_end)

                    # Create new candidate
                    new_candidate = ParseCandidate(
                        elements=candidate.elements + [element],
                        score=candidate.score,
                        position=data_end,
                        consumed_all=False,
                        reasoning=candidate.reasoning.copy(),
                    )

                    # Score this extension
                    self._score_extension(new_candidate, element, input_string)

                    extensions.append(new_candidate)

        return extensions

    def _get_variable_lengths_to_try(
        self,
        input_string: str,
        data_start: int,
        ai_def: AIDefinition,
        candidate: ParseCandidate
    ) -> List[int]:
        """
        Determine which lengths to try for a variable-length AI.

        Uses pruning to avoid explosion:
        - Look for known AI prefixes in remaining text
        - Prioritize lengths that lead to valid continuations
        """
        max_len = min(ai_def.max_length, len(input_string) - data_start)
        min_len = ai_def.min_length

        if max_len < min_len:
            return []

        # For internal AIs (90-99), try fewer lengths
        if ai_def.priority_class == PriorityClass.INTERNAL:
            # Only try a few strategic lengths
            return list(range(min_len, min(max_len + 1, min_len + 10)))

        # For core AIs (10, 21), be more thorough
        lengths = []

        # Strategy: look for AI prefixes in the remainder
        known_ai_prefixes = ["01", "10", "17", "21", "90", "91", "92", "93", "94", "95", "96", "97", "98", "99"]

        for length in range(min_len, max_len + 1):
            next_pos = data_start + length
            if next_pos >= len(input_string):
                # End of string - always try this
                lengths.append(length)
                continue

            # Check if next position could start a known AI
            remaining_after = input_string[next_pos:]
            could_be_ai = any(remaining_after.startswith(ai) for ai in known_ai_prefixes)

            if could_be_ai:
                lengths.append(length)
            elif length == max_len:
                # Always try max length
                lengths.append(length)

        # If we didn't find any good splits, try all lengths
        if not lengths:
            lengths = list(range(min_len, max_len + 1))

        return lengths

    def _validate_element(
        self,
        ai_def: AIDefinition,
        value: str,
        start_pos: int,
        end_pos: int
    ) -> Tuple[ParsedElement, bool]:
        """
        Validate an element and return (ParsedElement, is_valid).
        """
        errors = []
        meta = {}
        normalized = value
        valid = True

        # Regex validation
        if not self._patterns[ai_def.ai].match(value):
            errors.append(f"Value does not match pattern for AI({ai_def.ai})")
            valid = False

        # Check digit validation (GTIN)
        if ai_def.check_digit:
            if len(value) == ai_def.fixed_length and value.isdigit():
                try:
                    data_part = value[:-1]
                    check_digit = int(value[-1])
                    calculated = calculate_check_digit_mod10(data_part)
                    if check_digit != calculated:
                        errors.append(f"Check digit mismatch: expected {calculated}, got {check_digit}")
                        valid = False
                    else:
                        meta['check_digit_valid'] = True
                except Exception as e:
                    errors.append(f"Check digit validation error: {e}")
                    valid = False
            else:
                errors.append("Invalid format for check digit validation")
                valid = False

        # Date validation
        if ai_def.date_format == "YYMMDD":
            # Check for DD=00 (unknown day) - use YYMMD0 format
            if value[4:6] == "00":
                # Legacy "unknown day" format
                result = validate_date(value, "YYMMD0")
                if result.valid:
                    meta.update(result.meta)
                    meta['unknown_day'] = True
                    # Format as YYYY-MM-XX to indicate unknown day
                    year = result.meta.get('year', '????')
                    month = result.meta.get('month', '??')
                    normalized = f"{year:04d}-{month:02d}-XX" if isinstance(year, int) else f"{year}-{month}-XX"
                else:
                    errors.extend(result.errors)
                    valid = False
            else:
                # Normal date with specific day
                result = validate_date(value, "YYMMDD")
                if result.valid:
                    meta.update(result.meta)
                    if 'iso_date' in result.meta:
                        normalized = result.meta['iso_date']
                else:
                    errors.extend(result.errors)
                    valid = False

        element = ParsedElement(
            ai=ai_def.ai,
            raw_value=value,
            normalized_value=normalized,
            valid=valid,
            validation_errors=errors,
            validation_meta=meta,
            start_pos=start_pos,
            end_pos=end_pos,
        )

        return element, valid

    def _score_extension(
        self,
        candidate: ParseCandidate,
        new_element: ParsedElement,
        full_input: str
    ):
        """
        Score the addition of new_element to candidate.

        Implements the comprehensive scoring rules from requirements.
        """
        ai = new_element.ai

        # A) Strong positive signals

        # +1000: GTIN(01) mod10 passes
        if ai == "01" and new_element.valid and new_element.validation_meta.get('check_digit_valid'):
            candidate.score += 1000
            candidate.reasoning.append("+1000: Valid GTIN with correct check digit")
        elif ai == "01" and not new_element.valid:
            # Invalid GTIN = invalid parse
            candidate.score = -float('inf')
            candidate.reasoning.append("-inf: Invalid GTIN check digit")
            return

        # +250: Date(17) is valid calendar date with DD != 00
        if ai == "17" and new_element.valid:
            if not new_element.validation_meta.get('unknown_day', False):
                candidate.score += 250
                candidate.reasoning.append("+250: Valid expiry date")
            else:
                # DD=00 case: -60 penalty later
                candidate.score += 250 - 60
                candidate.reasoning.append("+190: Valid expiry date but DD=00 (legacy unknown day)")

        # +120: Pattern match: (17) -> (10) -> (21)
        if len(candidate.elements) >= 3:
            last_three = [e.ai for e in candidate.elements[-3:]]
            if last_three == ["17", "10", "21"]:
                candidate.score += 120
                candidate.reasoning.append("+120: Pattern (17)->(10)->(21) detected")

        # +120: Pattern match: (21) -> (17) -> (10) [for case C]
        if len(candidate.elements) >= 3:
            last_three = [e.ai for e in candidate.elements[-3:]]
            if last_three == ["21", "17", "10"]:
                candidate.score += 120
                candidate.reasoning.append("+120: Pattern (21)->(17)->(10) detected")

        # +90: Embedded "17" inside variable field
        # This applies when we have a (21) that could contain "17YYMMDD10" pattern
        if ai == "21":
            value = new_element.raw_value
            # Look for "17" followed by 6 digits followed by "10"
            pattern = re.search(r'17(\d{6})10', value)
            if pattern:
                # Check if the 6 digits form a valid date
                date_str = pattern.group(1)
                date_result = validate_date(date_str, "YYMMDD")
                if date_result.valid:
                    candidate.score += 90
                    candidate.reasoning.append("+90: Embedded (17) detected inside (21) - should consider splitting")

        # B) Moderate positive signals

        # +30: Prefer standard pharma order
        if len(candidate.elements) >= 2:
            ai_sequence = [e.ai for e in candidate.elements]
            # Check for common patterns
            if ai_sequence == ["01", "17"]:
                candidate.score += 15
                candidate.reasoning.append("+15: Standard start (01)->(17)")
            if len(ai_sequence) >= 4:
                if ai_sequence[-4:] == ["01", "17", "10", "21"]:
                    candidate.score += 30
                    candidate.reasoning.append("+30: Standard pharma order (01)(17)(10)(21)")
                elif ai_sequence[-4:] == ["01", "21", "17", "10"]:
                    candidate.score += 30
                    candidate.reasoning.append("+30: Alternative pharma order (01)(21)(17)(10)")

        # +20: Lot(10) length in [2..10]
        if ai == "10":
            lot_len = len(new_element.raw_value)
            if 2 <= lot_len <= 10:
                candidate.score += 20
                candidate.reasoning.append(f"+20: Lot length {lot_len} in common range [2-10]")

        # +15: Serial(21) length in [6..20]
        if ai == "21":
            serial_len = len(new_element.raw_value)
            if 6 <= serial_len <= 20:
                candidate.score += 15
                candidate.reasoning.append(f"+15: Serial length {serial_len} in common range [6-20]")

        # C) Negative signals (penalties)

        # -200: Using AI 90-99 when tail could be absorbed into (21) or (10)
        if ai in [str(i) for i in range(90, 100)]:
            # Check if this AI is whitelisted
            if ai not in self.vendor_whitelist:
                # Check if we could have absorbed this into previous (21) or (10)
                if len(candidate.elements) >= 2:
                    prev = candidate.elements[-2]
                    if prev.ai in ["10", "21"]:
                        # Could we have extended the previous element?
                        combined_len = len(prev.raw_value) + len(ai) + len(new_element.raw_value)
                        max_allowed = AI_CATALOG[prev.ai].max_length
                        if combined_len <= max_allowed:
                            candidate.score -= 200
                            candidate.reasoning.append(f"-200: Using internal AI({ai}) when could extend AI({prev.ai})")

        # -150: Repeated AI(10)
        ai_list = [e.ai for e in candidate.elements]
        if ai == "10" and ai_list.count("10") > 1:
            candidate.score -= 150
            candidate.reasoning.append("-150: Repeated AI(10)")

        # -120: Repeated AI(21)
        if ai == "21" and ai_list.count("21") > 1:
            candidate.score -= 120
            candidate.reasoning.append("-120: Repeated AI(21)")

        # -80: Splitting rare AI when valid (10)+(21) exists
        if ai in [str(i) for i in range(90, 100)]:
            # Check if we have both (10) and (21)
            has_10 = "10" in ai_list
            has_21 = "21" in ai_list
            if has_10 and has_21:
                candidate.score -= 80
                candidate.reasoning.append(f"-80: Using rare AI({ai}) when both (10) and (21) present")

        # -50: Extremely long lot > 12
        if ai == "10" and len(new_element.raw_value) > 12:
            candidate.score -= 50
            candidate.reasoning.append(f"-50: Long lot length {len(new_element.raw_value)} > 12")

        # -50: Extremely short serial < 4
        if ai == "21" and len(new_element.raw_value) < 4:
            candidate.score -= 50
            candidate.reasoning.append(f"-50: Short serial length {len(new_element.raw_value)} < 4")

        # +10: Fewer total elements (prefer simpler parses)
        # Applied at end, based on total elements
        if candidate.position >= len(full_input):
            # Complete parse
            num_elements = len(candidate.elements)
            if num_elements <= 4:
                candidate.score += 10
                candidate.reasoning.append(f"+10: Concise parse with {num_elements} elements")


def parse_gs1_no_separator(
    input_string: str,
    beam_width: int = 200,
    max_alternatives: int = 5,
    vendor_whitelist_internal_ais: Set[str] = None
) -> NoSeparatorParseResult:
    """
    Parse a GS1 element string with NO separators.

    This is the main entry point for no-separator parsing.

    Args:
        input_string: Raw barcode data (no separators)
        beam_width: Beam search width (higher = more thorough, slower)
        max_alternatives: Maximum alternative parses to return
        vendor_whitelist_internal_ais: Set of internal AIs (90-99) that are
                                       allowed to be split out (vendor-specific)

    Returns:
        NoSeparatorParseResult with best parse, alternatives, confidence, etc.

    Example:
        >>> result = parse_gs1_no_separator("01062867400002491728043010GB2C2171490437969853")
        >>> for elem in result.best_parse:
        ...     print(f"({elem.ai}){elem.raw_value}")
        (01)06286740000249
        (17)280430
        (10)GB2C
        (21)71490437969853
    """
    parser = NoSeparatorParser(
        beam_width=beam_width,
        max_alternatives=max_alternatives,
        vendor_whitelist_internal_ais=vendor_whitelist_internal_ais,
    )
    return parser.parse(input_string)
