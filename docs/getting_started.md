# Quick Start: GS1 No-Separator Parser

## Installation

No additional dependencies needed. The parser uses only Python standard library plus the existing GS1 parser modules.

```python
from gs1_parser import parse_gs1_no_separator
```

## Simplest Example

```python
from gs1_parser import parse_gs1_no_separator

# Your barcode data (no separators)
barcode = "01062867400002491728043010GB2C2171490437969853"

# Parse it
result = parse_gs1_no_separator(barcode)

# Print results
for elem in result.best_parse:
    print(f"AI({elem.ai}): {elem.raw_value}")

# Output:
# AI(01): 06286740000249
# AI(17): 280430
# AI(10): GB2C
# AI(21): 71490437969853
```

## Check Validation

```python
for elem in result.best_parse:
    if elem.ai == "01":
        # Check GTIN validity
        if elem.valid:
            print(f"GTIN valid: {elem.raw_value}")
            print(f"Check digit OK: {elem.validation_meta['check_digit_valid']}")
        else:
            print(f"GTIN invalid: {elem.validation_errors}")

    elif elem.ai == "17":
        # Check expiry date
        if elem.valid:
            print(f"Expiry: {elem.normalized_value}")  # ISO format: YYYY-MM-DD

            if elem.validation_meta.get('unknown_day'):
                print("  (Unknown day - legacy format)")
```

## Check Confidence

```python
if result.confidence > 0.8:
    print(f"High confidence: {result.confidence:.1%}")
elif result.confidence > 0.5:
    print(f"Medium confidence: {result.confidence:.1%}")
    print(f"Consider checking alternatives")
else:
    print(f"Low confidence: {result.confidence:.1%}")
    print("Parse may be incorrect")
```

## Handle Ambiguity

```python
# Get up to 5 alternatives
result = parse_gs1_no_separator(barcode, max_alternatives=5)

if "AMBIGUOUS_PARSE" in result.flags:
    print(f"Warning: Multiple valid parses found")
    print(f"Best parse score: {result.best_score}")

    for i, (elements, score, reasoning) in enumerate(result.alternatives, 1):
        print(f"\nAlternative {i} (score: {score}):")
        for elem in elements:
            print(f"  ({elem.ai}){elem.raw_value}")
```

## Real-World Example: Medication Barcode

```python
# Typical pharmaceutical barcode
medication_barcode = "01062850960028771726033110HN8X2172869453519267"

result = parse_gs1_no_separator(medication_barcode)

# Extract specific fields
gtin = next((e.raw_value for e in result.best_parse if e.ai == "01"), None)
expiry = next((e.raw_value for e in result.best_parse if e.ai == "17"), None)
lot = next((e.raw_value for e in result.best_parse if e.ai == "10"), None)
serial = next((e.raw_value for e in result.best_parse if e.ai == "21"), None)

print(f"GTIN:   {gtin}")    # 06285096002877
print(f"Expiry: {expiry}")  # 260331 (Mar 31, 2026)
print(f"Lot:    {lot}")     # HN8X
print(f"Serial: {serial}")  # 72869453519267
```

## Performance Tuning

```python
# For faster parsing (slight accuracy trade-off)
result = parse_gs1_no_separator(
    barcode,
    beam_width=100  # Default: 200
)

# For vendor-specific internal AIs
result = parse_gs1_no_separator(
    barcode,
    vendor_whitelist_internal_ais={"94", "98"}
)
```

## Error Handling

```python
try:
    result = parse_gs1_no_separator(barcode)

    if not result.best_parse:
        print("No valid parse found")
        print(f"Flags: {result.flags}")

    elif "NO_VALID_PARSE" in result.flags:
        print("Input appears invalid")

    else:
        # Process results
        for elem in result.best_parse:
            print(f"({elem.ai}){elem.raw_value}")

except Exception as e:
    print(f"Parse error: {e}")
```

## Complete Example with All Features

```python
from gs1_parser import parse_gs1_no_separator

def parse_medication_barcode(barcode_data: str):
    """
    Parse a medication barcode and extract all relevant fields.

    Returns dict with GTIN, expiry, lot, serial, and metadata.
    """
    result = parse_gs1_no_separator(
        barcode_data,
        max_alternatives=3
    )

    # Extract fields
    parsed_data = {
        'gtin': None,
        'expiry_date': None,
        'lot_number': None,
        'serial_number': None,
        'confidence': result.confidence,
        'is_ambiguous': "AMBIGUOUS_PARSE" in result.flags,
        'warnings': []
    }

    for elem in result.best_parse:
        if elem.ai == "01":
            parsed_data['gtin'] = elem.raw_value
            if not elem.valid:
                parsed_data['warnings'].append("Invalid GTIN check digit")

        elif elem.ai == "17":
            parsed_data['expiry_date'] = elem.normalized_value
            if elem.validation_meta.get('unknown_day'):
                parsed_data['warnings'].append("Expiry day unknown (DD=00)")

        elif elem.ai == "10":
            parsed_data['lot_number'] = elem.raw_value

        elif elem.ai == "21":
            parsed_data['serial_number'] = elem.raw_value

    # Check if parse is acceptable
    if result.confidence < 0.7:
        parsed_data['warnings'].append(f"Low confidence: {result.confidence:.1%}")

    return parsed_data

# Usage
barcode = "01062867400002491728043010GB2C2171490437969853"
data = parse_medication_barcode(barcode)

print(f"GTIN:       {data['gtin']}")
print(f"Expiry:     {data['expiry_date']}")
print(f"Lot:        {data['lot_number']}")
print(f"Serial:     {data['serial_number']}")
print(f"Confidence: {data['confidence']:.1%}")

if data['warnings']:
    print("\nWarnings:")
    for warning in data['warnings']:
        print(f"  - {warning}")
```

## Testing Your Implementation

```bash
# Run the test suite
pytest tests/test_no_separator.py -v

# Run the demo
python demo_no_separator.py

# Run specific ground truth case
pytest tests/test_no_separator.py::TestGroundTruthCases::test_case_a_gb2c_serial -v
```

## Common Patterns

### Pattern 1: Standard Pharmaceutical Order
```
(01) GTIN → (17) Expiry → (10) Lot → (21) Serial
```

### Pattern 2: Alternative Order (Case C)
```
(01) GTIN → (21) Serial → (17) Expiry → (10) Lot
```

### Pattern 3: GTIN + Expiry Only
```
(01) GTIN → (17) Expiry
```

## Troubleshooting

### Low Confidence (<50%)
- Input may be malformed
- Multiple equally valid parses exist
- Check alternatives to see other options

### Wrong Parse
- Verify input has no separators (ASCII 29, etc.)
- Check if vendor uses non-standard internal AIs (use whitelist)
- Report issue with input string and expected output

### Performance Issues
- Reduce beam_width for faster parsing
- Ensure input is reasonable length (< 100 chars typical)
- Cache parser instance if parsing many barcodes

## Next Steps

1. Read `README_NO_SEPARATOR.md` for detailed scoring rules
2. Review `IMPLEMENTATION_SUMMARY.md` for technical details
3. Check ground truth cases in `tests/test_no_separator.py`
4. Run `demo_no_separator.py` to see examples

## Support

For issues or questions, refer to:
- Ground truth test cases in `tests/test_no_separator.py`
- Full documentation in `README_NO_SEPARATOR.md`
- GS1 AI reference: https://ref.gs1.org/ai/
