# GS1 Barcode Parser - Documentation

Complete documentation for the GS1 Barcode Parser project.

---

## Getting Started

- **[Getting Started Guide](getting_started.md)** - Quick start guide and basic usage examples

---

## Core Documentation

### Parsing

- **[No-Separator Parsing](no_separator_parsing.md)** - Technical details of the no-separator parsing algorithm
  - Beam search implementation
  - Scoring system
  - Ground truth test cases
  - Performance characteristics

- **[Implementation Details](implementation_details.md)** - Deep dive into the implementation
  - Architecture overview
  - Scoring rules (-200 to +1000 points)
  - Internal AI deprioritization
  - Embedded AI detection
  - Algorithm complexity

### Output & Integration

- **[JSON API Guide](json_api.md)** - Clean JSON output for production use
  - Human-readable field names
  - Date formatting (dd/mm/yyyy)
  - GTIN lookup integration
  - Python API reference

---

## Project Documentation

- **[Application Guide](application.md)** - Pharmaceutical application documentation
  - Use cases
  - Integration patterns
  - GTIN database usage

- **[Changelog](changelog.md)** - Version history and updates
  - Feature additions
  - Bug fixes
  - Breaking changes

---

## Development Documentation

- **[Refactoring Plan](refactoring_plan.md)** - Complete refactoring strategy
  - Phase-by-phase breakdown
  - Directory structure changes
  - Import path updates

- **[Structure Comparison](structure_comparison.md)** - Before/after comparison
  - Old vs new structure
  - File migrations
  - Benefits of new structure

---

## Quick Reference

### Main Functions

```python
from gs1_parser import (
    parse_gs1_to_json,      # Clean JSON output
    parse_gs1_to_dict,      # Dictionary output
    parse_gs1_no_separator, # Raw parse result
    prepare_for_lookup,     # GTIN lookup ready
)
```

### Key Features

- **100% Accurate** - All ground truth test cases pass
- **Fast** - <50ms typical parse time
- **Smart** - Beam search with comprehensive scoring
- **Clean Output** - JSON with human-readable fields
- **Healthcare Ready** - DD=00 legacy date support
- **GTIN Integration** - Built-in database (7.2MB)

---

## Additional Resources

### External Links

- [GS1 General Specifications](https://www.gs1.org/standards)
- [GS1 AI Reference](https://ref.gs1.org/ai/)
- [SFDA Drug Barcoding](https://sfda.gov.sa/)

### Project Links

- [Main README](../README.md)
- [Examples](../examples/)
- [Tests](../tests/)
- [CLI Tools](../cli/)

---

## Documentation Structure

```
docs/
├── README.md                    # This file - Documentation index
├── getting_started.md           # Quick start guide
├── no_separator_parsing.md      # No-separator algorithm details
├── implementation_details.md    # Technical implementation
├── json_api.md                  # JSON API reference
├── application.md               # Application guide
├── changelog.md                 # Version history
├── refactoring_plan.md          # Refactoring documentation
└── structure_comparison.md      # Structure changes
```

---

## Contributing to Documentation

When adding documentation:
1. Use clear, concise language
2. Include code examples
3. Add to this index
4. Follow existing formatting
5. Keep technical accuracy high

---

**Version:** 1.0.0
**Last Updated:** 2026-02-01
