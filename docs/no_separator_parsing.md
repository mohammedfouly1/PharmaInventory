# GS1 No-Separator Parser

## Overview

This module provides specialized parsing for GS1 element strings that **always lack separators** (no FNC1, no ASCII 29/GS characters). This is a common real-world scenario in pharmaceutical and healthcare barcodes where scanner output or legacy systems strip separators.

## The Problem

GS1 element strings contain multiple Application Identifiers (AIs) concatenated together. Fixed-length AIs (like GTIN) are unambiguous, but variable-length AIs (like Batch/Lot and Serial Number) create ambiguity without separators:

```
Input: 010628509600084210BATCH2112345678
Could be:
  (01)06285096000842 (10)BATCH (21)12345678   ✓ Correct
  (01)06285096000842 (10)BATCH2 (11)2345678   ✗ Wrong
  (01)06285096000842 (10)BATCH21 (12)345678   ✗ Wrong
```

Without separators, the parser must intelligently determine where variable-length values end.

## Solution: Scoring-Based Beam Search

### Algorithm

1. **Beam Search**: Explores multiple parse paths simultaneously, keeping the top N candidates
2. **Scoring System**: Each parse path gets a score based on validation and heuristics
3. **Best Parse Selection**: Returns the highest-scoring complete parse
4. **Alternatives**: Provides top-K alternative parses with confidence metrics

### Key Innovation: Internal AI Deprioritization

A critical insight from real pharmaceutical data: **Internal AIs (90-99) appearing in the tail of a barcode are almost always part of the Serial Number (21), not separate fields.**

Example:
```
...2106902409792902
   ├─ (21)06902409792902  ✓ Correct (absorb "90" into serial)
   └─ (21)069024 (90)2409792902  ✗ Wrong (incorrectly split internal AI)
```

**Rule**: Penalize using AI 90-99 by **-200 points** when the data could be absorbed into a valid (21) or (10) field.

## Scoring Rules

### Strong Positive Signals (+)

| Score | Rule | Rationale |
|-------|------|-----------|
| +1000 | GTIN (01) mod10 check digit passes | Hard constraint - invalid GTIN = invalid parse |
| +250 | Date (17) is valid calendar date (DD ≠ 00) | Strong validation signal |
| +120 | Pattern: (17)→(10)→(21) detected | Standard pharmaceutical order |
| +120 | Pattern: (21)→(17)→(10) detected | Alternative valid order |
| +90 | Embedded (17) detected inside (21) | Indicates need to split variable field |

### Moderate Positive Signals (+)

| Score | Rule | Rationale |
|-------|------|-----------|
| +30 | Standard pharma order: (01)(17)(10)(21) | Common industry pattern |
| +20 | Lot (10) length ∈ [2, 10] | Common lot length range |
| +15 | Serial (21) length ∈ [6, 20] | Common serial length range |
| +10 | Fewer total elements | Prefer simpler parses |

### Negative Signals (Penalties) (-)

| Score | Rule | Rationale |
|-------|------|-----------|
| -200 | Using AI 90-99 when could extend (21)/(10) | **Critical rule** - avoid false internal AI splits |
| -150 | Repeated AI(10) | Invalid - lot should appear once |
| -120 | Repeated AI(21) | Invalid - serial should appear once |
| -80 | Rare AI when (10)+(21) exists | Prefer core AIs over uncommon ones |
| -60 | Date (17) with DD=00 | Legacy "unknown day" format - valid but lower confidence |
| -50 | Lot (10) length > 12 | Unusually long lot |
| -50 | Serial (21) length < 4 | Unusually short serial |

### Tie-Breaking (Deterministic)

1. Higher score wins
2. If within 10 points: prefer (01)(17)(10)(21) or (01)(21)(17)(10) patterns
3. If still tied: prefer fewer internal AIs (90-99)
4. If still tied: prefer shorter (10) when (21) exists
5. If still tied: lexicographic ordering (deterministic)

## Validation Rules

### AI(01) GTIN
- **Length**: Exactly 14 digits
- **Check Digit**: Mod-10 must pass (hard constraint)
- **Invalid GTIN**: Score = -∞ (parse rejected)

### AI(17) Expiry Date
- **Format**: YYMMDD (6 digits)
- **Validation**:
  - MM: 01-12
  - DD: 01-31 (calendar-valid for month/year)
  - **DD=00**: Allowed as legacy "unknown day" (penalty: -60)
- **Invalid Date**: Parse rejected

### AI(10) Batch/Lot
- **Length**: 1-20 characters
- **Charset**: GS1 alphanumeric (A-Z, 0-9, hyphen, slash)

### AI(21) Serial Number
- **Length**: 1-20 characters
- **Charset**: GS1 alphanumeric (A-Z, 0-9, hyphen, slash)

### AI(90-99) Internal/Company-Specific
- **Length**: 1-30 characters
- **Priority**: Very low - only used when no better parse exists
- **Whitelist**: Can be configured per vendor if known to use specific internal AIs

## Usage

### Basic Usage

```python
from gs1_parser import parse_gs1_no_separator

# Parse a no-separator barcode
input_string = "01062867400002491728043010GB2C2171490437969853"
result = parse_gs1_no_separator(input_string)

# Print best parse
for elem in result.best_parse:
    print(f"({elem.ai}){elem.raw_value}")

# Output:
# (01)06286740000249
# (17)280430
# (10)GB2C
# (21)71490437969853

# Check confidence
print(f"Confidence: {result.confidence:.2%}")
print(f"Flags: {result.flags}")
```

### With Alternatives

```python
result = parse_gs1_no_separator(
    input_string,
    max_alternatives=5  # Get up to 5 alternative parses
)

# Check for ambiguity
if "AMBIGUOUS_PARSE" in result.flags:
    print(f"Warning: Multiple valid parses found")
    print(f"Best score: {result.best_score}")

    for i, (elements, score, reasoning) in enumerate(result.alternatives, 1):
        print(f"\nAlternative {i} (score: {score}):")
        for elem in elements:
            print(f"  ({elem.ai}){elem.raw_value}")
```

### Vendor-Specific Internal AIs

If a vendor is known to use specific internal AIs (e.g., AI(94) for lot tracking):

```python
result = parse_gs1_no_separator(
    input_string,
    vendor_whitelist_internal_ais={"94", "98"}  # Allow these internal AIs
)
```

## Ground Truth Test Cases

The parser has been validated against real pharmaceutical packaging data:

### Case A: Standard Pharma Order
```
Input:  01062867400002491728043010GB2C2171490437969853
Output: (01)06286740000249 (17)280430 (10)GB2C (21)71490437969853
```

### Case B: Short Lot Code
```
Input:  01062850960028771726033110HN8X2172869453519267
Output: (01)06285096002877 (17)260331 (10)HN8X (21)72869453519267
```

### Case C: Embedded Date in Serial
```
Input:  01062911037315552164SSI54CE688QZ1727021410C601
Output: (01)06291103731555 (21)64SSI54CE688QZ (17)270214 (10)C601
Note:   (17) embedded after (21) - detected via pattern matching
```

### Case D: Avoid False Internal AI Split
```
Input:  010622300001036517270903103056442130564439945626
Output: (01)06223000010365 (17)270903 (10)305644 (21)30564439945626
Note:   "945626" absorbed into (21), not split as (94) or (99)
```

### Case E: Unknown Day (DD=00) and Internal AI Absorption
```
Input:  010625115902606717290400104562202106902409792902
Output: (01)06251159026067 (17)290400 (10)456220 (21)06902409792902
Note:   DD=00 treated as valid legacy format; "90" absorbed into (21)
```

## Performance

- **Beam Width**: Default 200 (configurable)
- **Typical Parse Time**: < 50ms for standard pharmaceutical barcodes
- **Worst Case**: < 500ms for highly ambiguous inputs
- **Memory**: O(beam_width × input_length)

### Optimization Tips

1. **Reduce Beam Width**: For faster parsing with slight accuracy trade-off
2. **Vendor Whitelist**: If vendor uses known internal AIs, whitelist them to reduce search space
3. **Batch Processing**: Parser can be reused for multiple inputs

## Comparison with Standard Parser

| Feature | Standard Parser | No-Separator Parser |
|---------|----------------|---------------------|
| Input | With separators (ASCII 29) | No separators |
| Algorithm | Fast-path O(n) | Beam search O(n × beam_width) |
| Ambiguity Handling | Minimal | Comprehensive scoring |
| Alternatives | Limited | Top-K with confidence |
| Performance | ~1ms | ~50ms |
| Use Case | Well-formed GS1 data | Real-world stripped data |

## Limitations

1. **Not 100% Accurate**: Without separators, some inputs are genuinely ambiguous
2. **Heuristic-Based**: Scoring rules are based on common pharmaceutical patterns
3. **Performance Trade-off**: Slower than separator-based parsing
4. **Limited AIs**: Currently supports core pharmaceutical AIs (extensible)

## Future Enhancements

- [ ] Machine learning-based scoring (train on labeled pharmaceutical data)
- [ ] Support for more AI types (healthcare-specific, logistics, etc.)
- [ ] Vendor-specific scoring profiles
- [ ] Parallel beam search for better performance
- [ ] Incremental parsing for streaming data

## References

- [GS1 AI Reference](https://ref.gs1.org/ai/)
- [GS1 AI(21) Serial Specification](https://ref.gs1.org/ai/21)
- [GS1 Processing Data from Symbology](https://www.gs1.org/sites/default/files/docs/barcodes/WR14-221_GSCN_Software%20Version_1Jun2015.pdf)
- [GS1 Check Digit Calculator](https://www.gs1.org/services/check-digit-calculator)
- [SFDA Drug Barcoding Specifications](https://sfda.gov.sa/sites/default/files/2021-03/DrugBarcodingSpecificationsEN.pdf)

## Contributing

When adding new test cases or scoring rules:

1. Provide real-world ground truth data
2. Document the rationale for scoring adjustments
3. Run full test suite to ensure no regressions
4. Update this README with new patterns discovered

## License

Same as parent GS1 Parser module.
