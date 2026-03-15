#!/usr/bin/env python3
"""
Tests for location targeting parsing and validation.

Covers the three supported formats:
  1. Location ID (numeric Criteria ID)
  2. Location name (human-readable place name)
  3. Proximity target (radius:lat:lon)

Run:
    python -m pytest scripts/test_location_targeting.py -v
    # or simply:
    python scripts/test_location_targeting.py
"""

import sys
import os
import tempfile
import textwrap

# Add parent directory so we can import sibling modules
sys.path.insert(0, os.path.dirname(__file__))

from generate_csv import resolve_location
from validate_rsa import validate_location_entry, validate_location_targeting, validate_markdown_file


# ==========================================================================
# Tests for resolve_location() in generate_csv.py
# ==========================================================================

class TestResolveLocation:
    """Tests for the resolve_location function."""

    # --- Single entry tests ---

    def test_empty_string(self):
        """Empty input should produce no results."""
        assert resolve_location("") == []

    def test_whitespace_only(self):
        """Whitespace-only input should produce no results."""
        assert resolve_location("   ") == []

    def test_single_location_id(self):
        """A single numeric ID should be classified as Location ID."""
        result = resolve_location("1012421")
        assert result == [("1012421", None)]

    def test_single_location_name(self):
        """A single place name should be classified as Location (name)."""
        result = resolve_location("Kungsor, Vastmanland County, Sweden")
        assert result == [(None, "Kungsor, Vastmanland County, Sweden")]

    def test_single_proximity_target(self):
        """A proximity target should be classified as Location (proximity)."""
        result = resolve_location("(15km:58.767077:11.631213)")
        assert result == [(None, "(15km:58.767077:11.631213)")]

    # --- Multiple entries (semicolon-separated) ---

    def test_multiple_location_ids(self):
        """Multiple IDs separated by semicolons."""
        result = resolve_location("1012421; 1012422; 1012424")
        assert result == [
            ("1012421", None),
            ("1012422", None),
            ("1012424", None),
        ]

    def test_multiple_location_names(self):
        """Multiple names separated by semicolons."""
        result = resolve_location(
            "Kungsor, Vastmanland County, Sweden; Aneby, Jonkoping County, Sweden"
        )
        assert result == [
            (None, "Kungsor, Vastmanland County, Sweden"),
            (None, "Aneby, Jonkoping County, Sweden"),
        ]

    def test_multiple_proximity_targets(self):
        """Multiple proximity targets separated by semicolons."""
        result = resolve_location(
            "(10km:57.809148:14.210866); (15km:58.767077:11.631213)"
        )
        assert result == [
            (None, "(10km:57.809148:14.210866)"),
            (None, "(15km:58.767077:11.631213)"),
        ]

    # --- Mixed formats ---

    def test_mixed_all_three_formats(self):
        """All three formats mixed together."""
        text = (
            "(10km:57.809148:14.210866); (15km:58.767077:11.631213); "
            "1012421; 1012422; "
            "Kungsor, Vastmanland County, Sweden; "
            "Aneby, Jonkoping County, Sweden"
        )
        result = resolve_location(text)
        assert result == [
            (None, "(10km:57.809148:14.210866)"),
            (None, "(15km:58.767077:11.631213)"),
            ("1012421", None),
            ("1012422", None),
            (None, "Kungsor, Vastmanland County, Sweden"),
            (None, "Aneby, Jonkoping County, Sweden"),
        ]

    def test_real_world_large_example(self):
        """A realistic large location targeting string from the user's example."""
        text = (
            "(10km:57.809148:14.210866); (10km:58.984368:11.270728); "
            "(15km:58.767077:11.631213); 1012314; 1012318; "
            "Aneby, Jonkoping County, Sweden; Halland County, Sweden"
        )
        result = resolve_location(text)
        assert len(result) == 7
        # Check proximity targets
        assert result[0] == (None, "(10km:57.809148:14.210866)")
        assert result[1] == (None, "(10km:58.984368:11.270728)")
        assert result[2] == (None, "(15km:58.767077:11.631213)")
        # Check IDs
        assert result[3] == ("1012314", None)
        assert result[4] == ("1012318", None)
        # Check names
        assert result[5] == (None, "Aneby, Jonkoping County, Sweden")
        assert result[6] == (None, "Halland County, Sweden")

    # --- Edge cases ---

    def test_extra_semicolons(self):
        """Extra semicolons should be ignored."""
        result = resolve_location(";;1012421;; ; ;1012422;;")
        assert result == [("1012421", None), ("1012422", None)]

    def test_newline_separator(self):
        """Newlines should also work as separators."""
        result = resolve_location("1012421\n1012422\n(15km:58.767077:11.631213)")
        assert result == [
            ("1012421", None),
            ("1012422", None),
            (None, "(15km:58.767077:11.631213)"),
        ]

    def test_proximity_with_integer_radius(self):
        """Proximity with integer-only radius like (20km:...)."""
        result = resolve_location("(20km:58.407475:15.612223)")
        assert result == [(None, "(20km:58.407475:15.612223)")]

    def test_proximity_with_negative_coordinates(self):
        """Proximity target with negative latitude or longitude."""
        result = resolve_location("(30km:-33.868820:151.209290)")
        assert result == [(None, "(30km:-33.868820:151.209290)")]

    def test_large_location_id(self):
        """Large numeric IDs (e.g. 9-digit) should still be recognized."""
        result = resolve_location("9222746")
        assert result == [("9222746", None)]

    def test_location_name_with_commas(self):
        """Location names may contain commas – semicolons delimit entries."""
        result = resolve_location(
            "Jonkoping, Jonkoping County, Sweden; Orebro, Orebro County, Sweden"
        )
        assert result == [
            (None, "Jonkoping, Jonkoping County, Sweden"),
            (None, "Orebro, Orebro County, Sweden"),
        ]

    def test_county_level_name(self):
        """County-level names (no city) should work as location names."""
        result = resolve_location("Halland County, Sweden")
        assert result == [(None, "Halland County, Sweden")]

    def test_five_digit_id(self):
        """Five-digit IDs like 21000 (Stockholm County) should work."""
        result = resolve_location("21000")
        assert result == [("21000", None)]


# ==========================================================================
# Tests for validate_location_entry() in validate_rsa.py
# ==========================================================================

class TestValidateLocationEntry:
    """Tests for individual location entry validation."""

    def test_valid_id(self):
        assert validate_location_entry("1012421") is None

    def test_valid_name(self):
        assert validate_location_entry("Kungsor, Vastmanland County, Sweden") is None

    def test_valid_proximity(self):
        assert validate_location_entry("(15km:58.767077:11.631213)") is None

    def test_valid_proximity_negative_coords(self):
        assert validate_location_entry("(30km:-33.868820:151.209290)") is None

    def test_empty_entry(self):
        """Empty string should fail validation."""
        assert validate_location_entry("") is not None


# ==========================================================================
# Tests for validate_location_targeting() in validate_rsa.py
# ==========================================================================

class TestValidateLocationTargeting:
    """Tests for full location targeting line validation."""

    def test_empty_value_is_valid(self):
        """Empty location targeting (no geo restriction) is valid."""
        violations = validate_location_targeting("", "test.md", 4)
        assert violations == []

    def test_single_id_valid(self):
        violations = validate_location_targeting("1012421", "test.md", 4)
        assert violations == []

    def test_mixed_valid(self):
        text = (
            "(10km:57.809148:14.210866); 1012421; "
            "Kungsor, Vastmanland County, Sweden"
        )
        violations = validate_location_targeting(text, "test.md", 4)
        assert violations == []

    def test_full_user_example_valid(self):
        """The full example from the user's request should be valid."""
        text = (
            "(10km:57.809148:14.210866); (10km:58.984368:11.270728); "
            "(15km:58.767077:11.631213); (15km:58.865969:11.190619); "
            "(20km:58.407475:15.612223); (20km:58.456362:15.031779); "
            "(20km:58.579716:16.172526); (20km:59.193299:15.276813); "
            "(25km:57.483643:12.030731); (25km:57.620690:12.566314); "
            "(25km:57.834917:12.356309); (25km:57.871337:11.729522); "
            "(25km:58.153712:12.289476); (25km:58.244781:11.647125); "
            "(25km:58.557071:11.345001); (30km:58.587169:12.184192); "
            "(30km:59.001292:12.238661); (45km:55.626833:13.380409); "
            "(50km:59.288435:18.059823); "
            "1012314; 1012318; 1012321; 1012322; 1012323; 1012324; "
            "1012325; 1012335; 1012345; 1012421; "
            "Aneby, Jonkoping County, Sweden; "
            "Arboga, Vastmanland County, Sweden; "
            "Halland County, Sweden; "
            "Stockholm County, Sweden"
        )
        violations = validate_location_targeting(text, "test.md", 4)
        assert violations == []


# ==========================================================================
# Tests for validate_markdown_file() with location targeting
# ==========================================================================

class TestValidateMarkdownWithLocation:
    """Integration tests: validate_markdown_file processes Location targeting."""

    def _write_temp_md(self, content: str) -> str:
        """Write content to a temp .md file and return the path."""
        fd, path = tempfile.mkstemp(suffix=".md")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(textwrap.dedent(content))
        return path

    def test_valid_location_no_violations(self):
        md = self._write_temp_md("""\
            Campaign: Test
            Ad group: Test_group
            Keywords: "test keyword"
            Location targeting: (15km:58.767077:11.631213); 1012421; Kungsor, Vastmanland County, Sweden
            Final URL: https://example.com
            Display path – level 1: test
            Display path – level 2: page
            Headline 1 (any position): Test Headline Here
            Description 1 (any position): Test description for the ad group.
        """)
        try:
            violations = validate_markdown_file(md)
            assert violations == []
        finally:
            os.unlink(md)

    def test_empty_location_no_violations(self):
        md = self._write_temp_md("""\
            Campaign: Test
            Ad group: Test_group
            Keywords: "test keyword"
            Location targeting:
            Final URL: https://example.com
            Display path – level 1: test
            Display path – level 2: page
            Headline 1 (any position): Test Headline Here
            Description 1 (any position): Test description for the ad group.
        """)
        try:
            violations = validate_markdown_file(md)
            assert violations == []
        finally:
            os.unlink(md)

    def test_ids_only_location(self):
        md = self._write_temp_md("""\
            Campaign: Test
            Ad group: Test_group
            Keywords: "test keyword"
            Location targeting: 1012421; 1012422; 21000
            Final URL: https://example.com
            Display path – level 1: test
            Display path – level 2: page
            Headline 1 (any position): Test Headline Here
            Description 1 (any position): Test description for the ad group.
        """)
        try:
            violations = validate_markdown_file(md)
            assert violations == []
        finally:
            os.unlink(md)


# ==========================================================================
# End-to-end test: generate_csv with location targeting
# ==========================================================================

class TestGenerateCsvWithLocations:
    """End-to-end: verify that CSV rows are generated correctly for locations."""

    def test_mixed_locations_produce_correct_csv_rows(self):
        """Mixed location types should produce correct Location ID / Location columns."""
        from generate_csv import generate_csv, make_row

        ad_groups = [{
            "campaign": "Test Campaign",
            "ad_group": "Test_AG",
            "keywords_raw": '"test keyword"',
            "location_targeting": "",
            "final_url": "https://example.com",
            "path1": "test",
            "path2": "page",
            "ads": [{
                "headlines": {1: {"text": "Test Headline", "position": ""}},
                "descriptions": {1: {"text": "Test description.", "position": ""}},
                "final_url": "https://example.com",
                "path1": "test",
                "path2": "page",
            }],
        }]

        locations = [
            ("1012421", None),                          # ID
            (None, "(15km:58.767077:11.631213)"),       # Proximity
            (None, "Kungsor, Vastmanland County, Sweden"),  # Name
        ]

        campaign_name, rows = generate_csv(
            ad_groups=ad_groups,
            negative_keywords=[],
            locations=locations,
        )

        # Find location rows (they have Location ID or Location set)
        loc_rows = [r for r in rows if r.get("Location ID") or r.get("Location")]
        assert len(loc_rows) == 3

        # First: Location ID
        assert loc_rows[0]["Location ID"] == "1012421"
        assert loc_rows[0]["Location"] == ""

        # Second: Proximity target in Location column
        assert loc_rows[1]["Location ID"] == ""
        assert loc_rows[1]["Location"] == "(15km:58.767077:11.631213)"

        # Third: Name in Location column
        assert loc_rows[2]["Location ID"] == ""
        assert loc_rows[2]["Location"] == "Kungsor, Vastmanland County, Sweden"

    def test_resolve_then_generate_roundtrip(self):
        """Parse a location string and feed to generate_csv – full roundtrip."""
        from generate_csv import resolve_location, generate_csv

        loc_text = "(10km:57.809148:14.210866); 1012421; Halland County, Sweden"
        locations = resolve_location(loc_text)

        ad_groups = [{
            "campaign": "Roundtrip",
            "ad_group": "Roundtrip_AG",
            "keywords_raw": '"test"',
            "location_targeting": loc_text,
            "final_url": "https://example.com",
            "path1": "t",
            "path2": "p",
            "ads": [{
                "headlines": {1: {"text": "Test", "position": ""}},
                "descriptions": {1: {"text": "Test desc.", "position": ""}},
                "final_url": "https://example.com",
                "path1": "t",
                "path2": "p",
            }],
        }]

        _, rows = generate_csv(
            ad_groups=ad_groups,
            negative_keywords=[],
            locations=locations,
        )

        loc_rows = [r for r in rows if r.get("Location ID") or r.get("Location")]
        assert len(loc_rows) == 3
        assert loc_rows[0]["Location"] == "(10km:57.809148:14.210866)"
        assert loc_rows[1]["Location ID"] == "1012421"
        assert loc_rows[2]["Location"] == "Halland County, Sweden"


# ==========================================================================
# Edge case: proximity with various radius formats
# ==========================================================================

class TestProximityEdgeCases:
    """Edge cases for proximity target parsing."""

    def test_proximity_single_digit_radius(self):
        """Single-digit radius like (5km:...)."""
        result = resolve_location("(5km:58.767077:11.631213)")
        assert result == [(None, "(5km:58.767077:11.631213)")]

    def test_proximity_large_radius(self):
        """Large radius like (100km:...)."""
        result = resolve_location("(100km:58.767077:11.631213)")
        assert result == [(None, "(100km:58.767077:11.631213)")]

    def test_proximity_integer_coordinates(self):
        """Coordinates without decimal part."""
        result = resolve_location("(10km:58:11)")
        assert result == [(None, "(10km:58:11)")]

    def test_proximity_high_precision_coordinates(self):
        """Coordinates with many decimal places."""
        result = resolve_location("(15km:58.76707700:11.63121300)")
        assert result == [(None, "(15km:58.76707700:11.63121300)")]

    def test_proximity_both_negative_coords(self):
        """Both latitude and longitude negative."""
        result = resolve_location("(20km:-33.868820:-151.209290)")
        assert result == [(None, "(20km:-33.868820:-151.209290)")]


# ==========================================================================
# Runner
# ==========================================================================

def run_all_tests():
    """Simple test runner that doesn't require pytest."""
    test_classes = [
        TestResolveLocation,
        TestValidateLocationEntry,
        TestValidateLocationTargeting,
        TestValidateMarkdownWithLocation,
        TestGenerateCsvWithLocations,
        TestProximityEdgeCases,
    ]

    total = 0
    passed = 0
    failed = 0
    errors = []

    for cls in test_classes:
        instance = cls()
        methods = [m for m in dir(instance) if m.startswith("test_")]
        for method_name in sorted(methods):
            total += 1
            method = getattr(instance, method_name)
            try:
                method()
                passed += 1
                print(f"  PASS  {cls.__name__}.{method_name}")
            except Exception as e:
                failed += 1
                errors.append((cls.__name__, method_name, e))
                print(f"  FAIL  {cls.__name__}.{method_name}: {e}")

    print(f"\n{'='*60}")
    if failed == 0:
        print(f"ALL {total} TESTS PASSED")
    else:
        print(f"{failed} of {total} tests FAILED")
        for cls_name, method_name, err in errors:
            print(f"\n  {cls_name}.{method_name}:")
            print(f"    {err}")
    print(f"{'='*60}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
