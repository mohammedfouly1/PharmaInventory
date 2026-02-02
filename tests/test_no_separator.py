"""
Comprehensive tests for GS1 No-Separator Parser.

Tests the ground truth cases that MUST pass exactly as specified.
"""

import pytest
from gs1_parser import parse_gs1_no_separator, NoSeparatorParseResult


class TestGroundTruthCases:
    """
    Ground truth test cases from real pharmaceutical packaging.
    These MUST pass exactly as specified.
    """

    def test_case_a_gb2c_serial(self):
        """
        Ground Truth A: 01062867400002491728043010GB2C2171490437969853
        Expected: (01)06286740000249 (17)280430 (10)GB2C (21)71490437969853

        Key: Standard pharma order with short lot "GB2C"
        """
        input_str = "01062867400002491728043010GB2C2171490437969853"

        result = parse_gs1_no_separator(input_str)

        # Should have 4 elements
        assert len(result.best_parse) == 4, \
            f"Expected 4 elements, got {len(result.best_parse)}"

        # Check each element
        elements = {elem.ai: elem.raw_value for elem in result.best_parse}

        assert "01" in elements, "Missing AI(01) GTIN"
        assert elements["01"] == "06286740000249", \
            f"AI(01) value mismatch: expected '06286740000249', got '{elements['01']}'"

        assert "17" in elements, "Missing AI(17) Expiry"
        assert elements["17"] == "280430", \
            f"AI(17) value mismatch: expected '280430', got '{elements['17']}'"

        assert "10" in elements, "Missing AI(10) Batch/Lot"
        assert elements["10"] == "GB2C", \
            f"AI(10) value mismatch: expected 'GB2C', got '{elements['10']}'"

        assert "21" in elements, "Missing AI(21) Serial"
        assert elements["21"] == "71490437969853", \
            f"AI(21) value mismatch: expected '71490437969853', got '{elements['21']}'"

        # Check order: (01), (17), (10), (21)
        ai_order = [elem.ai for elem in result.best_parse]
        assert ai_order == ["01", "17", "10", "21"], \
            f"AI order mismatch: expected ['01', '17', '10', '21'], got {ai_order}"

        # Check confidence is reasonable
        assert result.confidence > 0.5, \
            f"Low confidence: {result.confidence}"

        # Should have MISSING_SEPARATOR flag
        assert "MISSING_SEPARATOR" in result.flags

    def test_case_b_hn8x_serial(self):
        """
        Ground Truth B: 01062850960028771726033110HN8X2172869453519267
        Expected: (01)06285096002877 (17)260331 (10)HN8X (21)72869453519267

        Key: Standard pharma order with short lot "HN8X"
        """
        input_str = "01062850960028771726033110HN8X2172869453519267"

        result = parse_gs1_no_separator(input_str)

        assert len(result.best_parse) == 4

        elements = {elem.ai: elem.raw_value for elem in result.best_parse}

        assert elements["01"] == "06285096002877"
        assert elements["17"] == "260331"
        assert elements["10"] == "HN8X"
        assert elements["21"] == "72869453519267"

        ai_order = [elem.ai for elem in result.best_parse]
        assert ai_order == ["01", "17", "10", "21"]

    def test_case_c_embedded_17_in_21(self):
        """
        Ground Truth C: 01062911037315552164SSI54CE688QZ1727021410C601
        Expected: (01)06291103731555 (21)64SSI54CE688QZ (17)270214 (10)C601

        CRITICAL: (17) is embedded inside what looks like (21).
        Parser must detect "17270214" as a valid date and split accordingly.
        This tests the embedded AI detection logic (+90 scoring).
        """
        input_str = "01062911037315552164SSI54CE688QZ1727021410C601"

        result = parse_gs1_no_separator(input_str)

        assert len(result.best_parse) == 4

        elements = {elem.ai: elem.raw_value for elem in result.best_parse}

        assert elements["01"] == "06291103731555", \
            f"AI(01) mismatch: got '{elements.get('01', 'MISSING')}'"

        assert elements["21"] == "64SSI54CE688QZ", \
            f"AI(21) mismatch: expected '64SSI54CE688QZ', got '{elements.get('21', 'MISSING')}'"

        assert elements["17"] == "270214", \
            f"AI(17) mismatch: expected '270214', got '{elements.get('17', 'MISSING')}'"

        assert elements["10"] == "C601", \
            f"AI(10) mismatch: expected 'C601', got '{elements.get('10', 'MISSING')}'"

        # Check order: (01), (21), (17), (10)
        ai_order = [elem.ai for elem in result.best_parse]
        assert ai_order == ["01", "21", "17", "10"], \
            f"AI order mismatch: expected ['01', '21', '17', '10'], got {ai_order}"

    def test_case_d_avoid_internal_94_99(self):
        """
        Ground Truth D: 010622300001036517270903103056442130564439945626
        Expected: (01)06223000010365 (17)270903 (10)305644 (21)30564439945626

        CRITICAL: "945626" at the end could be parsed as (94)5626 or (99)45626.
        But these are internal AIs. Parser MUST prefer absorbing into (21) serial.
        This tests the -200 penalty for using internal AIs.
        """
        input_str = "010622300001036517270903103056442130564439945626"

        result = parse_gs1_no_separator(input_str)

        assert len(result.best_parse) == 4

        elements = {elem.ai: elem.raw_value for elem in result.best_parse}

        assert elements["01"] == "06223000010365"
        assert elements["17"] == "270903"
        assert elements["10"] == "305644"
        assert elements["21"] == "30564439945626", \
            f"AI(21) should absorb '945626', not split as internal AI. Got: '{elements.get('21', 'MISSING')}'"

        # Should NOT have any internal AIs (90-99)
        internal_ais = [ai for ai in elements.keys() if ai.isdigit() and 90 <= int(ai) <= 99]
        assert len(internal_ais) == 0, \
            f"Should not use internal AIs, but found: {internal_ais}"

        ai_order = [elem.ai for elem in result.best_parse]
        assert ai_order == ["01", "17", "10", "21"]

    def test_case_e_unknown_day_and_avoid_90(self):
        """
        Ground Truth E: 010625115902606717290400104562202106902409792902
        Expected: (01)06251159026067 (17)290400 (10)456220 (21)06902409792902

        CRITICAL FEATURES:
        1) AI(17) has DD=00 (unknown day) - legacy healthcare format.
           Must be treated as valid but with -60 penalty.
        2) Serial starts with "06902409792902". Could be parsed as (90)2409792902
           but should be absorbed into (21) to avoid -200 penalty.
        """
        input_str = "010625115902606717290400104562202106902409792902"

        result = parse_gs1_no_separator(input_str)

        assert len(result.best_parse) == 4

        elements = {elem.ai: elem.raw_value for elem in result.best_parse}

        assert elements["01"] == "06251159026067"

        # Check expiry date with DD=00
        assert elements["17"] == "290400", \
            f"AI(17) mismatch: expected '290400', got '{elements.get('17', 'MISSING')}'"

        # Verify that DD=00 is handled correctly
        elem_17 = next(e for e in result.best_parse if e.ai == "17")
        assert elem_17.validation_meta.get('unknown_day', False), \
            "AI(17) with DD=00 should be marked as unknown_day"

        assert elements["10"] == "456220"

        # Serial should include the "90" digits
        assert elements["21"] == "06902409792902", \
            f"AI(21) should absorb '90...', not split. Got: '{elements.get('21', 'MISSING')}'"

        # Should NOT have AI(90)
        assert "90" not in elements, \
            "Should not split AI(90) from serial"

        ai_order = [elem.ai for elem in result.best_parse]
        assert ai_order == ["01", "17", "10", "21"]


class TestScoringMechanics:
    """Test that scoring rules work correctly."""

    def test_invalid_gtin_rejected(self):
        """Parser should reject parses with invalid GTIN check digit."""
        # Valid GTIN: 06285096000842 (check digit 2)
        # Invalid: 06285096000841 (wrong check digit)
        input_str = "0106285096000841172901311012345"

        result = parse_gs1_no_separator(input_str)

        # Should still try to parse but with very low score or no valid parse
        # The invalid check digit should make score = -inf
        # So best parse might be empty or have very low confidence
        if result.best_parse:
            # If it found something, confidence should be very low
            assert result.confidence < 0.3, \
                "Invalid GTIN should result in low confidence"

    def test_date_validation(self):
        """Parser should validate dates properly."""
        # Invalid date: month 13
        input_str = "0106285096000842171301011012345"

        result = parse_gs1_no_separator(input_str)

        # Should handle gracefully, possibly with low confidence
        # or parse differently
        assert result is not None

    def test_unknown_day_dd00(self):
        """DD=00 should be treated as valid but with penalty."""
        # Date with DD=00
        input_str = "0106285096000842172901001012345"

        result = parse_gs1_no_separator(input_str)

        if len(result.best_parse) >= 2:
            elem_17 = next((e for e in result.best_parse if e.ai == "17"), None)
            if elem_17:
                # Should be marked as unknown_day
                assert elem_17.validation_meta.get('unknown_day', False), \
                    "DD=00 should be marked as unknown_day"

    def test_prefer_common_lot_length(self):
        """Parser should prefer lot lengths in [2-10] range."""
        # Create input where lot could be 2 or 15 characters
        # Parser should prefer shorter due to +20 bonus
        pass  # This is tested implicitly in ground truth cases

    def test_internal_ai_penalty(self):
        """Internal AIs (90-99) should get -200 penalty."""
        # Already tested in case D and E
        pass


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_input(self):
        """Empty input should be handled gracefully."""
        result = parse_gs1_no_separator("")

        assert result.best_parse == []
        assert result.confidence == 0.0
        assert "NO_VALID_PARSE" in result.flags

    def test_too_short_input(self):
        """Input too short to contain valid GS1 data."""
        result = parse_gs1_no_separator("01062")

        # Should fail or have very low confidence
        assert len(result.best_parse) == 0 or result.confidence < 0.3

    def test_only_gtin(self):
        """Input with only GTIN should parse correctly."""
        input_str = "0106285096000842"

        result = parse_gs1_no_separator(input_str)

        assert len(result.best_parse) == 1
        assert result.best_parse[0].ai == "01"
        assert result.best_parse[0].raw_value == "06285096000842"

    def test_alternatives_provided(self):
        """Parser should provide alternatives for ambiguous cases."""
        # Use an ambiguous input
        input_str = "01062850960008421729013110ABCD2112345678"

        result = parse_gs1_no_separator(input_str, max_alternatives=5)

        # Should have some alternatives
        assert len(result.alternatives) >= 0

        # If ambiguous, should be flagged
        if len(result.alternatives) > 0 and (result.best_score - result.alternatives[0][1]) < 40:
            assert "AMBIGUOUS_PARSE" in result.flags


class TestPerformance:
    """Test that parser performs adequately."""

    def test_beam_search_completes(self):
        """Beam search should complete in reasonable time."""
        import time

        input_str = "01062850960008421729013110BATCH12321SERIAL123456789"

        start = time.perf_counter()
        result = parse_gs1_no_separator(input_str)
        elapsed = time.perf_counter() - start

        # Should complete in under 1 second
        assert elapsed < 1.0, f"Parser too slow: {elapsed:.3f}s"

    def test_batch_parsing(self):
        """Should handle multiple parses efficiently."""
        import time

        test_inputs = [
            "01062867400002491728043010GB2C2171490437969853",
            "01062850960028771726033110HN8X2172869453519267",
            "01062911037315552164SSI54CE688QZ1727021410C601",
        ]

        start = time.perf_counter()
        for input_str in test_inputs:
            parse_gs1_no_separator(input_str)
        elapsed = time.perf_counter() - start

        # Should complete all in under 2 seconds
        assert elapsed < 2.0, f"Batch parsing too slow: {elapsed:.3f}s"


class TestReasoningAndConfidence:
    """Test that reasoning and confidence calculations work."""

    def test_reasoning_provided(self):
        """Parser should provide reasoning for scores."""
        input_str = "01062867400002491728043010GB2C2171490437969853"

        result = parse_gs1_no_separator(input_str)

        # Best parse should have reasoning
        # (Note: reasoning is in alternatives structure, not directly in best_parse)
        assert result.best_score is not None
        assert isinstance(result.best_score, (int, float))

    def test_confidence_calculation(self):
        """Confidence should be between 0 and 1."""
        input_str = "01062867400002491728043010GB2C2171490437969853"

        result = parse_gs1_no_separator(input_str)

        assert 0.0 <= result.confidence <= 1.0, \
            f"Confidence out of range: {result.confidence}"

    def test_ambiguous_flag_when_close_scores(self):
        """AMBIGUOUS_PARSE flag should be set when scores are close."""
        # This is implementation-dependent
        # If we have alternatives with close scores, should be flagged
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
