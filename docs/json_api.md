# GS1 JSON API Guide

## Clean JSON Output for Production Integration

This guide shows how to use the GS1 parser to get **clean JSON output** ready for integration with GTIN lookup systems.

---

## ✨ Features

✅ **Human-readable field names** (e.g., "GTIN Code" not "01")
✅ **Date format: dd/mm/yyyy** (e.g., "30/04/2028")
✅ **Best parse only** (no warnings, errors, or alternatives)
✅ **Strict JSON output**
✅ **Ready for GTIN database lookup**
✅ **Placeholder fields for drug information**

---

## 🚀 Quick Start

### 1. Simple JSON Output

```python
from gs1_parser import parse_gs1_to_json

barcode = "01062867400002491728043010GB2C2171490437969853"
json_output = parse_gs1_to_json(barcode)
print(json_output)
```

**Output:**
```json
{
  "GTIN Code": "06286740000249",
  "Expiry Date": "30/04/2028",
  "Batch/Lot Number": "GB2C",
  "Serial Number": "71490437969853"
}
```

### 2. Dictionary Output

```python
from gs1_parser import parse_gs1_to_dict

barcode = "01062867400002491728043010GB2C2171490437969853"
data = parse_gs1_to_dict(barcode)

print(data["GTIN Code"])       # 06286740000249
print(data["Expiry Date"])     # 30/04/2028
print(data["Batch/Lot Number"]) # GB2C
print(data["Serial Number"])   # 71490437969853
```

### 3. Prepare for GTIN Lookup

```python
from gs1_parser import prepare_for_lookup

barcode = "01062867400002491728043010GB2C2171490437969853"
data = prepare_for_lookup(barcode)

# Includes parsed fields + placeholder fields for lookup
print(data)
```

**Output:**
```json
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
```

---

## 📋 Field Name Mapping

| AI Code | Human-Readable Name | Example Value |
|---------|-------------------|---------------|
| 01 | GTIN Code | "06286740000249" |
| 17 | Expiry Date | "30/04/2028" |
| 10 | Batch/Lot Number | "GB2C" |
| 21 | Serial Number | "71490437969853" |
| 11 | Production Date | "15/01/2028" |
| 13 | Packaging Date | "20/01/2028" |
| 15 | Best Before Date | "30/06/2028" |

---

## 📅 Date Formatting

All dates are formatted as **dd/mm/yyyy**:

- Normal dates: `"30/04/2028"` (30th April 2028)
- Unknown day (DD=00): `"XX/04/2029"` (April 2029, day unknown - legacy format)

**Example with DD=00:**

```python
barcode = "010625115902606717290400104562202106902409792902"
data = parse_gs1_to_dict(barcode)

print(data["Expiry Date"])  # "XX/04/2029"
```

---

## 🔌 Integration with GTIN Lookup

### Complete Workflow

```python
from gs1_parser import prepare_for_lookup
import json

def parse_and_lookup(barcode_data: str) -> dict:
    """Parse barcode and lookup drug information."""

    # Step 1: Parse barcode
    parsed_data = prepare_for_lookup(barcode_data)

    # Step 2: Extract GTIN
    gtin_code = parsed_data["GTIN Code"]

    # Step 3: Lookup in your database
    drug_info = lookup_gtin_in_database(gtin_code)

    # Step 4: Merge data
    parsed_data.update(drug_info)

    return parsed_data

# Usage
barcode = "01062867400002491728043010GB2C2171490437969853"
result = parse_and_lookup(barcode)

print(json.dumps(result, ensure_ascii=False, indent=2))
```

**Output:**
```json
{
  "GTIN Code": "06286740000249",
  "Expiry Date": "30/04/2028",
  "Batch/Lot Number": "GB2C",
  "Serial Number": "71490437969853",
  "Drug Trade Name": "Panadol Extra",
  "Scientific Name": "Paracetamol 500mg + Caffeine 65mg",
  "Pharmaceutical Form": "Film-Coated Tablet",
  "Number of Subunits": "24"
}
```

---

## 💻 Command Line Usage

### Simple CLI

```bash
python parse_barcode.py "01062867400002491728043010GB2C2171490437969853"
```

**Output:**
```json
{
  "GTIN Code": "06286740000249",
  "Expiry Date": "30/04/2028",
  "Batch/Lot Number": "GB2C",
  "Serial Number": "71490437969853"
}
```

### Integration with Shell Scripts

```bash
#!/bin/bash
BARCODE="01062867400002491728043010GB2C2171490437969853"
RESULT=$(python parse_barcode.py "$BARCODE")

# Extract GTIN for lookup
GTIN=$(echo "$RESULT" | jq -r '."GTIN Code"')
echo "GTIN: $GTIN"

# Lookup in database (example)
# curl "https://api.example.com/drugs/$GTIN"
```

---

## 📊 Complete Examples

### Example 1: Standard Pharmaceutical Barcode

```python
from gs1_parser import parse_gs1_to_dict

barcode = "01062867400002491728043010GB2C2171490437969853"
data = parse_gs1_to_dict(barcode)
```

**Output:**
```json
{
  "GTIN Code": "06286740000249",
  "Expiry Date": "30/04/2028",
  "Batch/Lot Number": "GB2C",
  "Serial Number": "71490437969853"
}
```

### Example 2: With Unknown Day (DD=00)

```python
barcode = "010625115902606717290400104562202106902409792902"
data = parse_gs1_to_dict(barcode)
```

**Output:**
```json
{
  "GTIN Code": "06251159026067",
  "Expiry Date": "XX/04/2029",
  "Batch/Lot Number": "456220",
  "Serial Number": "06902409792902"
}
```

### Example 3: Alternative Field Order

```python
barcode = "01062911037315552164SSI54CE688QZ1727021410C601"
data = parse_gs1_to_dict(barcode)
```

**Output:**
```json
{
  "GTIN Code": "06291103731555",
  "Serial Number": "64SSI54CE688QZ",
  "Expiry Date": "14/02/2027",
  "Batch/Lot Number": "C601"
}
```

---

## 🎯 API Reference

### `parse_gs1_to_json(barcode_data, include_confidence=False, include_raw_values=False)`

Parse barcode and return JSON string.

**Parameters:**
- `barcode_data` (str): Raw barcode string (no separators)
- `include_confidence` (bool): Include confidence score (default: False)
- `include_raw_values` (bool): Include raw values for dates (default: False)

**Returns:**
- JSON string

**Example:**
```python
json_output = parse_gs1_to_json(barcode)
print(json_output)
```

---

### `parse_gs1_to_dict(barcode_data, include_confidence=False)`

Parse barcode and return dictionary.

**Parameters:**
- `barcode_data` (str): Raw barcode string (no separators)
- `include_confidence` (bool): Include confidence score (default: False)

**Returns:**
- Dictionary

**Example:**
```python
data = parse_gs1_to_dict(barcode)
gtin = data["GTIN Code"]
```

---

### `prepare_for_lookup(barcode_data)`

Parse barcode and prepare for GTIN lookup integration.

Returns dictionary with:
- All parsed fields
- Placeholder fields for lookup results (Drug Trade Name, Scientific Name, etc.)

**Parameters:**
- `barcode_data` (str): Raw barcode string (no separators)

**Returns:**
- Dictionary with parsed fields + lookup placeholders

**Example:**
```python
data = prepare_for_lookup(barcode)
gtin = data["GTIN Code"]

# Lookup in database
drug_info = lookup_gtin(gtin)

# Merge results
data.update(drug_info)
```

---

## 🔍 Database Integration Pattern

### Recommended Workflow

```python
import json
from gs1_parser import prepare_for_lookup

def process_barcode(barcode_data: str, database_connection) -> str:
    """
    Complete workflow for barcode processing with database lookup.

    Args:
        barcode_data: Raw barcode string
        database_connection: Your database connection object

    Returns:
        JSON string with complete medication information
    """
    # Step 1: Parse barcode
    parsed_data = prepare_for_lookup(barcode_data)

    # Step 2: Extract GTIN for lookup
    gtin_code = parsed_data.get("GTIN Code")

    if gtin_code:
        # Step 3: Query database
        cursor = database_connection.cursor()
        cursor.execute(
            """
            SELECT
                trade_name,
                scientific_name,
                pharmaceutical_form,
                number_of_subunits
            FROM medications
            WHERE gtin = ?
            """,
            (gtin_code,)
        )

        row = cursor.fetchone()

        if row:
            # Step 4: Update parsed data with lookup results
            parsed_data["Drug Trade Name"] = row[0]
            parsed_data["Scientific Name"] = row[1]
            parsed_data["Pharmaceutical Form"] = row[2]
            parsed_data["Number of Subunits"] = row[3]
        else:
            # GTIN not found in database
            parsed_data["Drug Trade Name"] = "Unknown"
            parsed_data["Scientific Name"] = "Not found"
            parsed_data["Pharmaceutical Form"] = "Unknown"
            parsed_data["Number of Subunits"] = "Unknown"

    # Step 5: Return as JSON
    return json.dumps(parsed_data, ensure_ascii=False, indent=2)
```

---

## 🧪 Testing

### Run Tests

```bash
# Test JSON output
pytest tests/test_json_output.py -v

# Test all functionality
pytest tests/test_no_separator.py tests/test_json_output.py -v
```

### Verify Output Format

```python
from gs1_parser import parse_gs1_to_dict
import json

barcode = "01062867400002491728043010GB2C2171490437969853"
data = parse_gs1_to_dict(barcode)

# Verify field names
assert "GTIN Code" in data
assert "Expiry Date" in data
assert "Batch/Lot Number" in data
assert "Serial Number" in data

# Verify no AI codes in output
assert "01" not in data
assert "17" not in data

# Verify date format
expiry = data["Expiry Date"]
assert len(expiry.split("/")) == 3  # dd/mm/yyyy

print("✓ All checks passed")
```

---

## 📝 Notes

### Clean Output
- **No warnings or errors** in output
- **No alternatives** (only best parse)
- **No confidence scores** (unless explicitly requested)
- **No AI codes** (only human-readable names)

### Date Handling
- All dates formatted as **dd/mm/yyyy**
- DD=00 shown as **XX/mm/yyyy** (legacy unknown day format)
- Dates validated for calendar correctness

### GTIN Format
- Always **14 digits**
- Check digit **validated**
- Ready for **database lookup**

---

## 🔗 Related Files

- `parse_barcode.py` - Simple CLI script
- `example_integration.py` - Complete integration example
- `tests/test_json_output.py` - JSON output tests
- `README_NO_SEPARATOR.md` - Technical details

---

## 📞 Next Steps

1. **Test the parser**: Run `python parse_barcode.py "YOUR_BARCODE"`
2. **Review examples**: Check `example_integration.py`
3. **Integrate with database**: Use `prepare_for_lookup()` function
4. **Deploy**: The parser is production-ready

---

**Ready for production integration!** The JSON output is clean, consistent, and ready to connect with your GTIN lookup database.
