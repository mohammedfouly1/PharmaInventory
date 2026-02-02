"""
Tests for JSON formatter output.

Ensures clean JSON output with:
- Human-readable field names
- Proper date formatting (dd/mm/yyyy)
- No warnings or errors
- Ready for GTIN lookup integration
"""

import pytest
import json
from gs1_parser import (
    parse_gs1_to_json,
    parse_gs1_to_dict,
    prepare_for_lookup,
)


class TestJSONOutput:
    """Test JSON output formatting."""

    def test_basic_json_output(self):
        """Test basic JSON output format."""
        barcode = "01062867400002491728043010GB2C2171490437969853"

        json_output = parse_gs1_to_json(barcode)

        # Should be valid JSON
        data = json.loads(json_output)

        # Check field names are human-readable
        assert "GTIN Code" in data
        assert "Expiry Date" in data
        assert "Batch/Lot Number" in data
        assert "Serial Number" in data

        # Check values
        assert data["GTIN Code"] == "06286740000249"
        assert data["Expiry Date"] == "30/04/2028"
        assert data["Batch/Lot Number"] == "GB2C"
        assert data["Serial Number"] == "71490437969853"

        # Should NOT contain AI codes like "01", "17", etc.
        assert "01" not in data
        assert "17" not in data
        assert "10" not in data
        assert "21" not in data

    def test_date_formatting_ddmmyyyy(self):
        """Test date is formatted as dd/mm/yyyy."""
        barcode = "010628509600084217290131"

        data = parse_gs1_to_dict(barcode)

        # Date should be in dd/mm/yyyy format
        expiry = data["Expiry Date"]
        assert expiry == "31/01/2029"

        # Verify format
        parts = expiry.split("/")
        assert len(parts) == 3
        assert len(parts[0]) == 2  # DD
        assert len(parts[1]) == 2  # MM
        assert len(parts[2]) == 4  # YYYY

    def test_unknown_day_dd00(self):
        """Test DD=00 is formatted as XX/mm/yyyy."""
        barcode = "010625115902606717290400104562202106902409792902"

        data = parse_gs1_to_dict(barcode)

        # Date with DD=00 should show XX
        expiry = data["Expiry Date"]
        assert expiry.startswith("XX/")
        assert "/2029" in expiry

    def test_no_warnings_in_output(self):
        """Test output contains no warnings or errors."""
        barcode = "01062867400002491728043010GB2C2171490437969853"

        json_output = parse_gs1_to_json(barcode)
        data = json.loads(json_output)

        # Should NOT contain any of these keys
        assert "warnings" not in data
        assert "errors" not in data
        assert "flags" not in data
        assert "alternatives" not in data

        # Should NOT contain underscore-prefixed keys (except _confidence if requested)
        non_confidence_keys = [k for k in data.keys() if k.startswith("_") and k != "_confidence"]
        assert len(non_confidence_keys) == 0

    def test_dict_output(self):
        """Test dictionary output (not JSON string)."""
        barcode = "01062850960028771726033110HN8X2172869453519267"

        data = parse_gs1_to_dict(barcode)

        # Should be a dict
        assert isinstance(data, dict)

        # Check values
        assert data["GTIN Code"] == "06285096002877"
        assert data["Expiry Date"] == "31/03/2026"
        assert data["Batch/Lot Number"] == "HN8X"
        assert data["Serial Number"] == "72869453519267"

    def test_prepare_for_lookup(self):
        """Test prepare_for_lookup includes placeholder fields."""
        barcode = "01062867400002491728043010GB2C2171490437969853"

        data = prepare_for_lookup(barcode)

        # Should have parsed fields
        assert "GTIN Code" in data
        assert "Expiry Date" in data
        assert "Batch/Lot Number" in data
        assert "Serial Number" in data

        # Should have placeholder fields for lookup
        assert "Drug Trade Name" in data
        assert "Scientific Name" in data
        assert "Pharmaceutical Form" in data
        assert "Number of Subunits" in data

        # Placeholders should be None
        assert data["Drug Trade Name"] is None
        assert data["Scientific Name"] is None
        assert data["Pharmaceutical Form"] is None
        assert data["Number of Subunits"] is None

        # Parsed fields should have values
        assert data["GTIN Code"] == "06286740000249"

    def test_confidence_optional(self):
        """Test confidence can be included optionally."""
        barcode = "01062867400002491728043010GB2C2171490437969853"

        # Without confidence
        data = parse_gs1_to_dict(barcode, include_confidence=False)
        assert "_confidence" not in data

        # With confidence
        data = parse_gs1_to_dict(barcode, include_confidence=True)
        assert "_confidence" in data
        assert isinstance(data["_confidence"], (int, float))
        assert 0 <= data["_confidence"] <= 100


class TestGroundTruthJSONOutput:
    """Test JSON output for all ground truth cases."""

    def test_case_a_json(self):
        """Case A: Standard pharma order."""
        barcode = "01062867400002491728043010GB2C2171490437969853"

        data = parse_gs1_to_dict(barcode)

        assert data["GTIN Code"] == "06286740000249"
        assert data["Expiry Date"] == "30/04/2028"
        assert data["Batch/Lot Number"] == "GB2C"
        assert data["Serial Number"] == "71490437969853"

    def test_case_b_json(self):
        """Case B: Short lot code."""
        barcode = "01062850960028771726033110HN8X2172869453519267"

        data = parse_gs1_to_dict(barcode)

        assert data["GTIN Code"] == "06285096002877"
        assert data["Expiry Date"] == "31/03/2026"
        assert data["Batch/Lot Number"] == "HN8X"
        assert data["Serial Number"] == "72869453519267"

    def test_case_c_json(self):
        """Case C: Embedded date in serial."""
        barcode = "01062911037315552164SSI54CE688QZ1727021410C601"

        data = parse_gs1_to_dict(barcode)

        assert data["GTIN Code"] == "06291103731555"
        assert data["Expiry Date"] == "14/02/2027"
        assert data["Batch/Lot Number"] == "C601"
        assert data["Serial Number"] == "64SSI54CE688QZ"

    def test_case_d_json(self):
        """Case D: Avoid internal AI split."""
        barcode = "010622300001036517270903103056442130564439945626"

        data = parse_gs1_to_dict(barcode)

        assert data["GTIN Code"] == "06223000010365"
        assert data["Expiry Date"] == "03/09/2027"
        assert data["Batch/Lot Number"] == "305644"
        assert data["Serial Number"] == "30564439945626"

    def test_case_e_json(self):
        """Case E: Unknown day + internal AI absorption."""
        barcode = "010625115902606717290400104562202106902409792902"

        data = parse_gs1_to_dict(barcode)

        assert data["GTIN Code"] == "06251159026067"
        assert data["Expiry Date"].startswith("XX/")  # Unknown day
        assert data["Batch/Lot Number"] == "456220"
        assert data["Serial Number"] == "06902409792902"


class TestProductionReadiness:
    """Test that output is production-ready."""

    def test_json_is_valid(self):
        """Test output is always valid JSON."""
        test_barcodes = [
            "01062867400002491728043010GB2C2171490437969853",
            "01062850960028771726033110HN8X2172869453519267",
            "01062911037315552164SSI54CE688QZ1727021410C601",
        ]

        for barcode in test_barcodes:
            json_output = parse_gs1_to_json(barcode)

            # Should not raise exception
            data = json.loads(json_output)

            # Should be a dict
            assert isinstance(data, dict)

    def test_output_is_clean(self):
        """Test output contains only data fields."""
        barcode = "01062867400002491728043010GB2C2171490437969853"

        data = parse_gs1_to_dict(barcode)

        # All keys should be human-readable (no AI codes)
        for key in data.keys():
            if not key.startswith("_"):  # Allow _confidence if present
                assert not key.isdigit()  # Not "01", "17", etc.
                assert "(" not in key  # Not "AI(01)"

    def test_gtin_ready_for_lookup(self):
        """Test GTIN is in correct format for database lookup."""
        barcode = "01062867400002491728043010GB2C2171490437969853"

        data = parse_gs1_to_dict(barcode)

        gtin = data["GTIN Code"]

        # Should be 14 digits
        assert len(gtin) == 14
        assert gtin.isdigit()

        # Should be ready to use as lookup key
        assert gtin == "06286740000249"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
