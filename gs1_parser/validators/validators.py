"""
GS1 Validation Functions

Implements comprehensive validation for GS1 element strings:
- Check digit validation (Mod10 for GTIN, SSCC, GLN, etc.)
- Date validation (YYMMDD, YYMMD0, YYYYMMDD)
- Numeric and alphanumeric validation
- Decimal position handling for weight/measure AIs
- Character set validation (CSET82, CSET39)

Based on GS1 General Specifications and GS1 Barcode Syntax Tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, Tuple, List, Dict, Any
from calendar import monthrange


@dataclass
class ValidationResult:
    """Result of a validation operation."""
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)


# GS1 Character Sets
CSET82 = frozenset(
    '!"#$%&\'()*+,-./0123456789:;<=>?@'
    'ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`'
    'abcdefghijklmnopqrstuvwxyz{|}'
)

CSET39 = frozenset('#-/0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ')

NUMERIC = frozenset('0123456789')


def calculate_check_digit_mod10(digits: str) -> int:
    """
    Calculate GS1 Mod10 check digit.
    
    Algorithm (GS1 General Specifications):
    1. From right to left, alternate multipliers 3 and 1
    2. Sum all products
    3. Check digit = (10 - (sum mod 10)) mod 10
    
    Args:
        digits: Numeric string without check digit
    
    Returns:
        Calculated check digit (0-9)
    """
    if not digits or not digits.isdigit():
        raise ValueError("Input must be a non-empty numeric string")
    
    total = 0
    for i, digit in enumerate(reversed(digits)):
        multiplier = 3 if i % 2 == 0 else 1
        total += int(digit) * multiplier
    
    return (10 - (total % 10)) % 10


def validate_check_digit(
    value: str,
    ai_code: str = ""
) -> ValidationResult:
    """
    Validate GS1 check digit for GTIN, SSCC, GLN, etc.
    
    Supports:
    - GTIN-8, GTIN-12, GTIN-13, GTIN-14 (AI 01, 02)
    - SSCC-18 (AI 00)
    - GLN-13 (AI 410-417)
    - GSIN-17 (AI 402)
    - GDTI, GRAI, etc.
    
    Args:
        value: The complete value including check digit
        ai_code: Optional AI code for context
    
    Returns:
        ValidationResult with check digit status
    """
    result = ValidationResult(valid=True)
    
    if not value or not value.isdigit():
        result.valid = False
        result.errors.append("Value must be numeric for check digit validation")
        return result
    
    if len(value) < 2:
        result.valid = False
        result.errors.append("Value too short for check digit validation")
        return result
    
    # Extract digits without check digit and the check digit
    data_digits = value[:-1]
    provided_check = int(value[-1])
    calculated_check = calculate_check_digit_mod10(data_digits)
    
    result.meta['calculated_check_digit'] = calculated_check
    result.meta['provided_check_digit'] = provided_check
    result.meta['check_digit_valid'] = (provided_check == calculated_check)
    
    if provided_check != calculated_check:
        result.valid = False
        result.errors.append(
            f"Check digit mismatch: expected {calculated_check}, got {provided_check}"
        )
    
    return result


def validate_date(
    value: str,
    format_type: str = "YYMMDD",
    century_pivot: int = 51
) -> ValidationResult:
    """
    Validate GS1 date formats.
    
    Formats:
    - YYMMDD: Standard date (e.g., 290131 = Jan 31, 2029)
    - YYMMD0: Date with day=00 allowed (e.g., 290100 = Jan 2029)
    - YYYYMMDD: Full year date
    - YYMMDDHH: Date with hour
    
    Century pivot (default 51):
    - YY >= 51: 19YY (1951-1999)
    - YY < 51: 20YY (2000-2050)
    
    Args:
        value: Date string
        format_type: One of YYMMDD, YYMMD0, YYYYMMDD, YYMMDDHH
        century_pivot: Year pivot for century determination
    
    Returns:
        ValidationResult with parsed date in meta
    """
    result = ValidationResult(valid=True)
    
    if not value or not value.isdigit():
        result.valid = False
        result.errors.append("Date must be numeric")
        return result
    
    try:
        if format_type == "YYMMDD":
            if len(value) != 6:
                result.valid = False
                result.errors.append(f"YYMMDD date must be 6 digits, got {len(value)}")
                return result
            
            yy = int(value[0:2])
            mm = int(value[2:4])
            dd = int(value[4:6])
            
            # Century determination
            year = 1900 + yy if yy >= century_pivot else 2000 + yy
            
            # Validate month
            if mm < 1 or mm > 12:
                result.valid = False
                result.errors.append(f"Invalid month: {mm}")
                return result
            
            # Validate day
            if dd < 1 or dd > 31:
                result.valid = False
                result.errors.append(f"Invalid day: {dd}")
                return result
            
            # Check calendar-valid day for month
            max_day = monthrange(year, mm)[1]
            if dd > max_day:
                result.valid = False
                result.errors.append(f"Day {dd} invalid for month {mm} in year {year}")
                return result
            
            result.meta['year'] = year
            result.meta['month'] = mm
            result.meta['day'] = dd
            result.meta['iso_date'] = f"{year:04d}-{mm:02d}-{dd:02d}"
            result.meta['date_ddmmyyyy'] = f"{dd:02d}/{mm:02d}/{year:04d}"
            
        elif format_type == "YYMMD0":
            if len(value) != 6:
                result.valid = False
                result.errors.append(f"YYMMD0 date must be 6 digits, got {len(value)}")
                return result
            
            yy = int(value[0:2])
            mm = int(value[2:4])
            dd = int(value[4:6])
            
            year = 1900 + yy if yy >= century_pivot else 2000 + yy
            
            if mm < 1 or mm > 12:
                result.valid = False
                result.errors.append(f"Invalid month: {mm}")
                return result
            
            # Day can be 00 (meaning end of month or unspecified)
            if dd == 0:
                result.meta['day_unspecified'] = True
                dd = monthrange(year, mm)[1]  # Last day of month
            elif dd < 1 or dd > 31:
                result.valid = False
                result.errors.append(f"Invalid day: {dd}")
                return result
            else:
                max_day = monthrange(year, mm)[1]
                if dd > max_day:
                    result.valid = False
                    result.errors.append(f"Day {dd} invalid for month {mm}")
                    return result
            
            result.meta['year'] = year
            result.meta['month'] = mm
            result.meta['day'] = dd
            result.meta['iso_date'] = f"{year:04d}-{mm:02d}-{dd:02d}"
            result.meta['date_ddmmyyyy'] = f"{dd:02d}/{mm:02d}/{year:04d}"
            
        elif format_type == "YYYYMMDD":
            if len(value) != 8:
                result.valid = False
                result.errors.append(f"YYYYMMDD date must be 8 digits, got {len(value)}")
                return result
            
            year = int(value[0:4])
            mm = int(value[4:6])
            dd = int(value[6:8])
            
            if mm < 1 or mm > 12:
                result.valid = False
                result.errors.append(f"Invalid month: {mm}")
                return result
            
            if dd < 1 or dd > 31:
                result.valid = False
                result.errors.append(f"Invalid day: {dd}")
                return result
            
            max_day = monthrange(year, mm)[1]
            if dd > max_day:
                result.valid = False
                result.errors.append(f"Day {dd} invalid for month {mm}")
                return result
            
            result.meta['year'] = year
            result.meta['month'] = mm
            result.meta['day'] = dd
            result.meta['iso_date'] = f"{year:04d}-{mm:02d}-{dd:02d}"
            result.meta['date_ddmmyyyy'] = f"{dd:02d}/{mm:02d}/{year:04d}"
            
        elif format_type == "YYMMDDHH":
            if len(value) < 8:
                result.valid = False
                result.errors.append(f"YYMMDDHH date must be at least 8 digits")
                return result
            
            yy = int(value[0:2])
            mm = int(value[2:4])
            dd = int(value[4:6])
            hh = int(value[6:8])
            
            year = 1900 + yy if yy >= century_pivot else 2000 + yy
            
            if mm < 1 or mm > 12:
                result.valid = False
                result.errors.append(f"Invalid month: {mm}")
                return result
            
            if dd < 1 or dd > 31:
                result.valid = False
                result.errors.append(f"Invalid day: {dd}")
                return result
            
            if hh < 0 or hh > 23:
                result.valid = False
                result.errors.append(f"Invalid hour: {hh}")
                return result
            
            result.meta['year'] = year
            result.meta['month'] = mm
            result.meta['day'] = dd
            result.meta['hour'] = hh
            result.meta['iso_datetime'] = f"{year:04d}-{mm:02d}-{dd:02d}T{hh:02d}:00:00"
            result.meta['date_ddmmyyyy'] = f"{dd:02d}/{mm:02d}/{year:04d}"
        
        else:
            result.valid = False
            result.errors.append(f"Unknown date format: {format_type}")
            
    except ValueError as e:
        result.valid = False
        result.errors.append(f"Date parsing error: {str(e)}")
    
    return result


def validate_numeric(
    value: str,
    min_length: int = 0,
    max_length: int = 0,
    fixed_length: Optional[int] = None
) -> ValidationResult:
    """
    Validate numeric field.
    
    Args:
        value: Value to validate
        min_length: Minimum length
        max_length: Maximum length
        fixed_length: If set, exact length required
    
    Returns:
        ValidationResult
    """
    result = ValidationResult(valid=True)
    
    if not value:
        if min_length > 0:
            result.valid = False
            result.errors.append("Value is empty but minimum length required")
        return result
    
    # Check numeric
    if not all(c in NUMERIC for c in value):
        result.valid = False
        result.errors.append("Value contains non-numeric characters")
        return result
    
    # Check length
    if fixed_length is not None:
        if len(value) != fixed_length:
            result.valid = False
            result.errors.append(f"Length must be exactly {fixed_length}, got {len(value)}")
    else:
        if min_length and len(value) < min_length:
            result.valid = False
            result.errors.append(f"Length {len(value)} below minimum {min_length}")
        if max_length and len(value) > max_length:
            result.valid = False
            result.errors.append(f"Length {len(value)} exceeds maximum {max_length}")
    
    return result


def validate_alphanumeric(
    value: str,
    min_length: int = 0,
    max_length: int = 0,
    fixed_length: Optional[int] = None,
    charset: str = "cset82"
) -> ValidationResult:
    """
    Validate alphanumeric field against GS1 character sets.
    
    Args:
        value: Value to validate
        min_length: Minimum length
        max_length: Maximum length
        fixed_length: If set, exact length required
        charset: 'cset82' or 'cset39'
    
    Returns:
        ValidationResult
    """
    result = ValidationResult(valid=True)
    
    if not value:
        if min_length > 0:
            result.valid = False
            result.errors.append("Value is empty but minimum length required")
        return result
    
    # Select character set
    allowed = CSET82 if charset == "cset82" else CSET39
    
    # Check characters
    invalid_chars = set(value) - allowed
    if invalid_chars:
        result.valid = False
        result.errors.append(f"Invalid characters: {invalid_chars}")
    
    # Check length
    if fixed_length is not None:
        if len(value) != fixed_length:
            result.valid = False
            result.errors.append(f"Length must be exactly {fixed_length}, got {len(value)}")
    else:
        if min_length and len(value) < min_length:
            result.valid = False
            result.errors.append(f"Length {len(value)} below minimum {min_length}")
        if max_length and len(value) > max_length:
            result.valid = False
            result.errors.append(f"Length {len(value)} exceeds maximum {max_length}")
    
    return result


def decode_decimal_value(
    value: str,
    decimal_positions: int
) -> Tuple[float, str]:
    """
    Decode a numeric value with implied decimal positions.
    
    Used for weight/measure AIs like 310x, 320x, 392x, etc.
    where the last digit of the AI indicates decimal places.
    
    Example: AI 3102, value "001234" -> 12.34
    
    Args:
        value: Numeric string value
        decimal_positions: Number of decimal places (0-9)
    
    Returns:
        (float_value, formatted_string)
    """
    if not value.isdigit():
        raise ValueError("Value must be numeric")
    
    if decimal_positions == 0:
        return float(value), value
    
    # Insert decimal point
    if len(value) <= decimal_positions:
        # Pad with leading zeros if needed
        value = value.zfill(decimal_positions + 1)
    
    int_part = value[:-decimal_positions] or "0"
    dec_part = value[-decimal_positions:]
    
    float_val = float(f"{int_part}.{dec_part}")
    formatted = f"{int_part}.{dec_part}"
    
    return float_val, formatted


def validate_gtin(value: str) -> ValidationResult:
    """
    Validate GTIN (AI 01, 02).
    
    GTIN-14 format: N14 with check digit in position 14.
    """
    result = validate_numeric(value, fixed_length=14)
    
    if result.valid:
        check_result = validate_check_digit(value, "01")
        result.valid = check_result.valid
        result.errors.extend(check_result.errors)
        result.meta.update(check_result.meta)
    
    return result


def validate_sscc(value: str) -> ValidationResult:
    """
    Validate SSCC (AI 00).
    
    SSCC-18 format: N18 with check digit in position 18.
    """
    result = validate_numeric(value, fixed_length=18)
    
    if result.valid:
        check_result = validate_check_digit(value, "00")
        result.valid = check_result.valid
        result.errors.extend(check_result.errors)
        result.meta.update(check_result.meta)
    
    return result


def validate_gln(value: str) -> ValidationResult:
    """
    Validate GLN (AI 410-417).
    
    GLN-13 format: N13 with check digit in position 13.
    """
    result = validate_numeric(value, fixed_length=13)
    
    if result.valid:
        check_result = validate_check_digit(value, "410")
        result.valid = check_result.valid
        result.errors.extend(check_result.errors)
        result.meta.update(check_result.meta)
    
    return result


def validate_regex(value: str, pattern: str) -> ValidationResult:
    """
    Validate value against a regex pattern.
    
    Args:
        value: Value to validate
        pattern: Regex pattern
    
    Returns:
        ValidationResult
    """
    result = ValidationResult(valid=True)
    
    try:
        compiled = re.compile(pattern)
        if not compiled.match(value):
            result.valid = False
            result.errors.append(f"Value does not match pattern: {pattern}")
    except re.error as e:
        result.valid = False
        result.errors.append(f"Invalid regex pattern: {str(e)}")
    
    return result


# Precompiled regex patterns for common validations
PATTERNS = {
    'numeric': re.compile(r'^\d+$'),
    'alphanumeric': re.compile(r'^[!-z]+$'),
    'gtin14': re.compile(r'^\d{14}$'),
    'sscc18': re.compile(r'^\d{18}$'),
    'gln13': re.compile(r'^\d{13}$'),
    'date_yymmdd': re.compile(r'^\d{6}$'),
    'date_yyyymmdd': re.compile(r'^\d{8}$'),
    'iso3166': re.compile(r'^\d{3}$'),
    'iso3166alpha2': re.compile(r'^[A-Z]{2}$'),
}
