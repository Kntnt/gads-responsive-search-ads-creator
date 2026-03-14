#!/usr/bin/env python3
"""
Google Ads Editor CSV Generator

Reads a folder of Markdown files (one analysis file + multiple RSA files)
produced by gads-landing-page-analyzer and gads-responsive-search-ads-creator,
and generates a single CSV file ready for import into Google Ads Editor.

Usage:
    python generate_csv.py \
        --input-dir <folder> \
        --output-dir <folder> \
        [--budget <amount>] \
        [--tracking-template <template>] \
        [--final-url-suffix <suffix>] \
        [--language <code>] \
        [--location-id <id>] \
        [--location-name <name>]
"""

import argparse
import csv
import io
import os
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path




# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    """Convert text to a URL/filename-friendly slug."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[-\s]+", "-", text).strip("-")
    return text


def detect_language(keywords: list[str]) -> str:
    """Simple heuristic: if keywords contain Swedish characters, assume Swedish."""
    swedish_chars = set("åäöÅÄÖ")
    swedish_words = {"och", "för", "med", "som", "eller", "från", "till", "att"}
    all_text = " ".join(keywords).lower()
    if any(c in all_text for c in swedish_chars):
        return "sv"
    words = set(all_text.split())
    if words & swedish_words:
        return "sv"
    return "en"


def resolve_location(location_text: str) -> list[tuple[str | None, str | None]]:
    """
    Parse a location string that may contain multiple locations separated by
    commas, semicolons, or newlines. Returns a list of (location_id, location_name)
    tuples – one per location. Google Ads Editor needs one row per location.

    The function does not attempt to translate or look up location names. It
    simply checks whether each value is numeric (→ Location ID column) or
    text (→ Location column). The responsibility for providing correct
    Location IDs lies with the earlier steps in the toolchain.
    """
    parts = re.split(r"[,;\n]+", location_text)
    results = []
    for part in parts:
        value = part.strip()
        if not value:
            continue
        if value.isdigit():
            results.append((value, None))   # -> Location ID
        else:
            results.append((None, value))   # -> Location (free text)
    return results


def parse_position(pos_text: str) -> str:
    """Extract numeric position from parenthetical text, or empty string."""
    pos_text = pos_text.strip().lower()
    if "any" in pos_text:
        return ""
    m = re.search(r"position\s*(\d+)", pos_text)
    if m:
        return m.group(1)
    return ""


def parse_keywords(kw_string: str) -> list[tuple[str, str]]:
    """
    Parse a comma-separated keyword string into (keyword, match_type) pairs.

    Match types:
    - "keyword" -> Phrase
    - [keyword] -> Exact
    - keyword   -> Broad
    """
    results = []
    # Normalize Unicode curly quotes to ASCII straight quotes before parsing.
    # RSA files should use straight quotes, but copy-paste from Word or macOS
    # may introduce curly quotes (\u201c \u201d) which must be treated identically.
    kw_string = kw_string.replace("\u201c", '"').replace("\u201d", '"')
    # Split on commas that are outside quotes/brackets
    # Simple approach: use regex to find individual keyword tokens
    tokens = re.findall(r'"[^"]*"|\[[^\]]*\]|[^,]+', kw_string)
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        if token.startswith('"') and token.endswith('"'):
            kw = token[1:-1].strip()
            match_type = "Phrase"
        elif token.startswith('[') and token.endswith(']'):
            kw = token[1:-1].strip()
            match_type = "Exact"
        else:
            kw = token.strip().strip('"').strip("'")
            match_type = "Broad"
        if kw:
            results.append((kw, match_type))
    return results


# ---------------------------------------------------------------------------
# RSA file parsing
# ---------------------------------------------------------------------------

# Key aliases: normalize English keys to internal names
KEY_ALIASES = {
    "campaign": "campaign",
    "ad group": "ad_group",
    "keywords": "keywords",
    "location targeting": "location_targeting",
    "final url": "final_url",
    "display path – level 1": "path1",
    "display path – level 2": "path2",
    "display path - level 1": "path1",
    "display path - level 2": "path2",
}


def normalize_key(key: str) -> str:
    """Normalize an English key to internal name."""
    k = key.strip().lower()
    return KEY_ALIASES.get(k, k)


def parse_headline_or_desc(key: str) -> tuple[str, int, str] | None:
    """
    Parse a headline/description key like 'Headline 3 (position 2)'.
    Returns (type, number, position_csv_value) or None.
    """
    m = re.match(r"headline\s+(\d+)\s*\(([^)]+)\)", key, re.IGNORECASE)
    if m:
        return ("headline", int(m.group(1)), parse_position(m.group(2)))
    m = re.match(r"description\s+(\d+)\s*\(([^)]+)\)", key, re.IGNORECASE)
    if m:
        return ("description", int(m.group(1)), parse_position(m.group(2)))
    return None


def parse_rsa_file(filepath: Path) -> dict:
    """
    Parse an RSA Markdown file. Returns a list of ad group dicts.
    Each file normally produces one dict, but files with multiple ads
    (separated by ---) produce one dict with multiple ads.
    """
    content = filepath.read_text(encoding="utf-8")

    # Split into ads by --- separator
    ad_sections = re.split(r"\n---+\n", content)

    # The first section contains the header (campaign, ad group, keywords, etc.)
    # plus the first ad's headlines/descriptions.
    # Subsequent sections contain only headlines/descriptions for additional ads.

    header_info = {}
    ads = []

    for i, section in enumerate(ad_sections):
        ad_data = {"headlines": {}, "descriptions": {}}
        for line in section.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Find key: value
            colon_pos = line.find(": ")
            if colon_pos == -1:
                continue
            raw_key = line[:colon_pos].strip()
            value = line[colon_pos + 2:].strip()

            # Try headline/description
            hd = parse_headline_or_desc(raw_key)
            if hd:
                hd_type, num, pos = hd
                if hd_type == "headline":
                    ad_data["headlines"][num] = {"text": value, "position": pos}
                else:
                    ad_data["descriptions"][num] = {"text": value, "position": pos}
                continue

            # Try known keys (only from first section for header fields)
            norm = normalize_key(raw_key)
            if norm in ("campaign", "ad_group", "keywords", "location_targeting",
                        "final_url", "path1", "path2"):
                if i == 0:
                    header_info[norm] = value
                # For subsequent ads, allow final_url and paths to override
                if i > 0 and norm in ("final_url", "path1", "path2"):
                    ad_data[norm] = value

        ads.append(ad_data)

    # Build result: one entry per ad group, with multiple ads
    result = {
        "campaign": header_info.get("campaign", ""),
        "ad_group": header_info.get("ad_group", ""),
        "keywords_raw": header_info.get("keywords", ""),
        "location_targeting": header_info.get("location_targeting", ""),
        "final_url": header_info.get("final_url", ""),
        "path1": header_info.get("path1", ""),
        "path2": header_info.get("path2", ""),
        "ads": [],
    }

    for i, ad in enumerate(ads):
        ad_entry = {
            "headlines": ad["headlines"],
            "descriptions": ad["descriptions"],
            "final_url": ad.get("final_url", result["final_url"]),
            "path1": ad.get("path1", result["path1"]),
            "path2": ad.get("path2", result["path2"]),
        }
        result["ads"].append(ad_entry)

    return result


def parse_analysis_file(filepath: Path) -> list[str]:
    """
    Parse the analysis Markdown file to extract negative keywords.
    Looks for a section titled 'Negative keywords'.
    Returns a list of keyword strings.
    """
    content = filepath.read_text(encoding="utf-8")
    lines = content.splitlines()

    negatives = []
    in_negatives = False

    for line in lines:
        stripped = line.strip()
        # Detect section header
        if re.match(r"^#{1,3}\s+Negative keywords", stripped, re.IGNORECASE):
            in_negatives = True
            continue
        # Stop at next section header
        if in_negatives and re.match(r"^#{1,3}\s+", stripped):
            break
        # Collect list items
        if in_negatives:
            m = re.match(r"^[-*]\s+(.+)", stripped)
            if m:
                kw = m.group(1).strip()
                if kw:
                    negatives.append(kw)

    return negatives


# ---------------------------------------------------------------------------
# File classification
# ---------------------------------------------------------------------------

def classify_files(input_dir: Path) -> tuple[Path | None, list[Path]]:
    """
    Classify Markdown files in a directory as either the analysis file
    or RSA files. Returns (analysis_path, [rsa_paths]).
    """
    md_files = sorted(input_dir.glob("*.md"))
    analysis = None
    rsa_files = []

    for f in md_files:
        content = f.read_text(encoding="utf-8", errors="replace")
        first_lines = content[:500].lower()

        # Analysis files contain "Negative keywords" section
        if "negative keywords" in content.lower():
            # Also check it's not an RSA file that mentions it
            if "campaign:" not in first_lines:
                analysis = f
                continue

        # RSA files start with "Campaign:"
        first_content_line = ""
        for line in content.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                first_content_line = stripped.lower()
                break

        if first_content_line.startswith("campaign:"):
            rsa_files.append(f)

    return analysis, rsa_files


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_ads(ad_groups: list[dict]) -> list[str]:
    """Validate character limits. Returns a list of warning strings."""
    warnings = []
    for ag in ad_groups:
        ag_name = ag["ad_group"]
        # Validate display paths
        if len(ag["path1"]) > 15:
            warnings.append(f"  {ag_name}: Path 1 '{ag['path1']}' is {len(ag['path1'])} chars (max 15)")
        if len(ag["path2"]) > 15:
            warnings.append(f"  {ag_name}: Path 2 '{ag['path2']}' is {len(ag['path2'])} chars (max 15)")

        for ad_idx, ad in enumerate(ag["ads"], 1):
            for num, hl in sorted(ad["headlines"].items()):
                text = hl["text"]
                if len(text) > 30:
                    warnings.append(
                        f"  {ag_name} RSA_{ad_idx}: Headline {num} '{text}' is {len(text)} chars (max 30)"
                    )
            for num, desc in sorted(ad["descriptions"].items()):
                text = desc["text"]
                if len(text) > 90:
                    warnings.append(
                        f"  {ag_name} RSA_{ad_idx}: Description {num} '{text[:40]}...' is {len(text)} chars (max 90)"
                    )
    return warnings


# ---------------------------------------------------------------------------
# CSV generation
# ---------------------------------------------------------------------------

# All columns in the order they appear in the CSV
ALL_COLUMNS = [
    "Campaign",
    "Campaign type",
    "Campaign daily budget",
    "Language",
    "Networks",
    "Bid strategy type",
    "Target CPA",
    "Campaign status",
    "EU Political Ads",
    "Tracking template",
    "Final URL suffix",
    "Location ID",
    "Location",
    "Ad Group",
    "Ad Group status",
    "Default max. CPC",
    "Max. CPM",
    "Target CPV",
    "Target CPM",
    "Keyword",
    "Criterion Type",
    "Ad Name",
    "Ad type",
    "Status",
    "Final URL",
    "Path 1",
    "Path 2",
    "Headline 1", "Headline 1 position",
    "Headline 2", "Headline 2 position",
    "Headline 3", "Headline 3 position",
    "Headline 4", "Headline 4 position",
    "Headline 5", "Headline 5 position",
    "Headline 6", "Headline 6 position",
    "Headline 7", "Headline 7 position",
    "Headline 8", "Headline 8 position",
    "Headline 9", "Headline 9 position",
    "Headline 10", "Headline 10 position",
    "Headline 11", "Headline 11 position",
    "Headline 12", "Headline 12 position",
    "Headline 13", "Headline 13 position",
    "Headline 14", "Headline 14 position",
    "Headline 15", "Headline 15 position",
    "Description 1", "Description 1 position",
    "Description 2", "Description 2 position",
    "Description 3", "Description 3 position",
    "Description 4", "Description 4 position",
]


def make_row(**kwargs) -> dict:
    """Create a row dict with all columns, filling in provided values."""
    row = {col: "" for col in ALL_COLUMNS}
    row.update(kwargs)
    return row


def generate_csv(
    ad_groups: list[dict],
    negative_keywords: list[str],
    budget: str = "",
    target_cpa: str = "",
    tracking_template: str = "",
    final_url_suffix: str = "",
    language: str = "sv",
    locations: list[tuple[str | None, str | None]] | None = None,
) -> tuple[str, list[dict]]:
    """
    Generate all CSV rows. Returns (campaign_name, rows).

    locations is a list of (location_id, location_name) tuples – one per
    target location. Each tuple produces its own row in the CSV, which is
    what Google Ads Editor expects.
    """
    if not ad_groups:
        raise ValueError("No ad groups found to generate CSV from.")

    campaign_name = ad_groups[0]["campaign"]
    rows = []

    # Determine whether to include nominal bid values on ad group rows.
    # When the bid strategy is "Maximize conversions" (with or without Target CPA),
    # Google Ads Editor may warn about missing bids at ad group level. Setting
    # these to 0.01 silences the warning without affecting actual bidding, because
    # the smart bid strategy overrides these values.
    use_nominal_bids = True  # Always true for now; all campaigns use Maximize conversions

    # 1. Campaign row
    campaign_row = make_row(
        Campaign=campaign_name,
        **{"Campaign type": "Search"},
        **{"Campaign daily budget": budget},
        Language=language,
        Networks="Google Search",
        **{"Bid strategy type": "Maximize conversions"},
        **{"Target CPA": target_cpa},
        **{"Campaign status": "Paused"},
        **{"EU Political Ads": "No"},
        **{"Tracking template": tracking_template},
        **{"Final URL suffix": final_url_suffix},
    )
    rows.append(campaign_row)

    # 2. Location targeting rows – one row per location
    if locations:
        for loc_id, loc_name in locations:
            if loc_id:
                loc_row = make_row(Campaign=campaign_name, **{"Location ID": loc_id})
            elif loc_name:
                loc_row = make_row(Campaign=campaign_name, Location=loc_name)
            else:
                continue
            rows.append(loc_row)

    # 3. Per ad group
    for ag in ad_groups:
        # Ad group row – include nominal bids to satisfy Google Ads Editor
        ag_row_data = {
            "Campaign": campaign_name,
            "Ad Group": ag["ad_group"],
            "Ad Group status": "Enabled",
        }
        if use_nominal_bids:
            ag_row_data["Default max. CPC"] = "0.01"
            ag_row_data["Max. CPM"] = "0.01"
            ag_row_data["Target CPV"] = "0.01"
            ag_row_data["Target CPM"] = "0.01"
        ag_row = make_row(**ag_row_data)
        rows.append(ag_row)

        # Keyword rows
        keywords = parse_keywords(ag["keywords_raw"])
        for kw, match_type in keywords:
            kw_row = make_row(
                Campaign=campaign_name,
                **{"Ad Group": ag["ad_group"]},
                Keyword=kw,
                **{"Criterion Type": match_type},
                Status="Enabled",
            )
            rows.append(kw_row)

        # Ad rows
        for ad_idx, ad in enumerate(ag["ads"], 1):
            ad_name = f"{ag['ad_group']}_RSA_{ad_idx}"
            ad_row_data = {
                "Campaign": campaign_name,
                "Ad Group": ag["ad_group"],
                "Ad Name": ad_name,
                "Ad type": "Responsive search ad",
                "Status": "Enabled",
                "Final URL": ad["final_url"],
                "Path 1": ad["path1"],
                "Path 2": ad["path2"],
            }
            # Headlines
            for num in range(1, 16):
                if num in ad["headlines"]:
                    hl = ad["headlines"][num]
                    ad_row_data[f"Headline {num}"] = hl["text"]
                    ad_row_data[f"Headline {num} position"] = hl["position"]
            # Descriptions
            for num in range(1, 5):
                if num in ad["descriptions"]:
                    desc = ad["descriptions"][num]
                    ad_row_data[f"Description {num}"] = desc["text"]
                    ad_row_data[f"Description {num} position"] = desc["position"]

            ad_row = make_row(**ad_row_data)
            rows.append(ad_row)

    # 4. Negative keywords (campaign level, phrase match)
    for neg_kw in negative_keywords:
        neg_row = make_row(
            Campaign=campaign_name,
            Keyword=f'"{neg_kw}"',
            **{"Criterion Type": "Campaign negative"},
        )
        rows.append(neg_row)

    return campaign_name, rows


def sanitize_field(value: str) -> str:
    """Remove tab and newline characters from a field value.

    Google Ads Editor TSV format cannot represent literal tabs or newlines
    inside field values (tabs are delimiters, newlines are row separators).
    This function replaces them with spaces to prevent CSV write errors.
    """
    return value.replace("\t", " ").replace("\n", " ").replace("\r", "")


def write_csv(rows: list[dict], output_path: Path) -> None:
    """Write rows as tab-separated values with UTF-16 LE BOM encoding.

    Google Ads Editor expects TSV (tab-separated) with UTF-16 LE encoding,
    which is also what it exports. Using comma-separated CSV causes parse
    failures when ad text contains commas, because Google Ads Editor does
    not respect CSV quoting rules.
    """
    # Sanitize all field values to remove tabs and newlines
    sanitized_rows = [
        {k: sanitize_field(v) for k, v in row.items()} for row in rows
    ]
    with open(output_path, "w", encoding="utf-16-le", newline="") as f:
        # Write UTF-16 LE BOM
        f.write("\ufeff")
        writer = csv.DictWriter(
            f,
            fieldnames=ALL_COLUMNS,
            delimiter="\t",
            quoting=csv.QUOTE_NONE,
            escapechar=None,
            quotechar=None,
        )
        writer.writeheader()
        writer.writerows(sanitized_rows)


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def compute_stats(ad_groups: list[dict], negative_keywords: list[str]) -> dict:
    """Compute summary statistics."""
    campaigns = set()
    ag_count = 0
    kw_total = 0
    kw_phrase = 0
    kw_exact = 0
    kw_broad = 0
    ad_count = 0

    for ag in ad_groups:
        campaigns.add(ag["campaign"])
        ag_count += 1
        ad_count += len(ag["ads"])
        keywords = parse_keywords(ag["keywords_raw"])
        for _, mt in keywords:
            kw_total += 1
            if mt == "Phrase":
                kw_phrase += 1
            elif mt == "Exact":
                kw_exact += 1
            else:
                kw_broad += 1

    return {
        "campaigns": len(campaigns),
        "ad_groups": ag_count,
        "keywords_total": kw_total,
        "keywords_phrase": kw_phrase,
        "keywords_exact": kw_exact,
        "keywords_broad": kw_broad,
        "ads": ad_count,
        "negative_keywords": len(negative_keywords),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate Google Ads Editor CSV")
    parser.add_argument("--input-dir", required=True, help="Folder with analysis + RSA .md files")
    parser.add_argument("--output-dir", required=True, help="Folder to save the CSV")
    parser.add_argument("--budget", default="", help="Campaign daily budget")
    parser.add_argument("--target-cpa", default="", help="Target CPA for Maximize conversions bid strategy")
    parser.add_argument("--tracking-template", default="", help="Tracking template")
    parser.add_argument("--final-url-suffix", default="", help="Final URL suffix")
    parser.add_argument("--language", default="", help="Language code (e.g. sv, en)")
    parser.add_argument("--location-id", default="", help="Google Ads Location ID")
    parser.add_argument("--location-name", default="", help="Location name (fallback)")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not input_dir.is_dir():
        print(f"Error: Input directory '{input_dir}' does not exist.", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Classify files
    analysis_path, rsa_paths = classify_files(input_dir)

    if not rsa_paths:
        print("Error: No RSA files found in the input directory.", file=sys.stderr)
        sys.exit(1)

    if not analysis_path:
        print("Warning: No analysis file found. Negative keywords will be empty.", file=sys.stderr)

    # Parse RSA files
    ad_groups = []
    for rsa_path in rsa_paths:
        ag = parse_rsa_file(rsa_path)
        ad_groups.append(ag)

    # Parse negative keywords
    negative_keywords = []
    if analysis_path:
        negative_keywords = parse_analysis_file(analysis_path)

    # Detect language
    language = args.language
    if not language:
        all_keywords = []
        for ag in ad_groups:
            kws = parse_keywords(ag["keywords_raw"])
            all_keywords.extend([kw for kw, _ in kws])
        language = detect_language(all_keywords)

    # Resolve locations – CLI flags take precedence, otherwise parse from RSA files
    locations: list[tuple[str | None, str | None]] = []
    if args.location_id:
        locations = [(args.location_id, None)]
    elif args.location_name:
        locations = [(None, args.location_name)]
    elif ad_groups:
        loc_text = ad_groups[0].get("location_targeting", "")
        if loc_text:
            locations = resolve_location(loc_text)

    # Validate
    warnings = validate_ads(ad_groups)
    if warnings:
        print("Character limit warnings:", file=sys.stderr)
        for w in warnings:
            print(w, file=sys.stderr)

    # Generate CSV
    campaign_name, rows = generate_csv(
        ad_groups=ad_groups,
        negative_keywords=negative_keywords,
        budget=args.budget,
        target_cpa=args.target_cpa,
        tracking_template=args.tracking_template,
        final_url_suffix=args.final_url_suffix,
        language=language,
        locations=locations,
    )

    # Build filename
    today = date.today().isoformat()
    slug = slugify(campaign_name) or "campaign"
    filename = f"{slug}_{today}.csv"
    output_path = output_dir / filename

    write_csv(rows, output_path)

    # Print stats as JSON to stdout
    stats = compute_stats(ad_groups, negative_keywords)
    stats["filename"] = filename
    stats["output_path"] = str(output_path)
    stats["language"] = language
    stats["locations"] = [
        {"location_id": lid or "", "location_name": lname or ""}
        for lid, lname in locations
    ]
    stats["warnings"] = warnings

    import json
    print(json.dumps(stats, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
