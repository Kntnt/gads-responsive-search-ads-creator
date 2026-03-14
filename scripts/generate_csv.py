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
        [--target-cpa <amount>] \
        [--tracking-template <template>] \
        [--final-url-suffix <suffix>] \
        [--language <code>] \
        [--location-ids [+|-]<ID>,...]
"""

import argparse
import csv
import os
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path


# ---------------------------------------------------------------------------
# Location ID parsing
# ---------------------------------------------------------------------------

def parse_location_ids(location_text: str) -> tuple[list[str], list[str]]:
    """
    Parse a location targeting string of the format:
        [+|-]<ID>[, [+|-]<ID>]*

    where <ID> is a numeric Google Ads geo target Criteria ID.
    IDs prefixed with '-' are excluded; IDs with '+' or no prefix are included.

    Returns (included_ids, excluded_ids) – both as lists of ID strings
    (without the +/- prefix).
    """
    # Remove all whitespace, then split on commas
    cleaned = re.sub(r"\s+", "", location_text)
    tokens = cleaned.split(",")

    included = []
    excluded = []
    for token in tokens:
        if not token:
            continue
        if token.startswith("-"):
            excluded.append(token[1:])
        elif token.startswith("+"):
            included.append(token[1:])
        else:
            included.append(token)

    return included, excluded


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


def parse_position(pos_text: str) -> str:
    """Extract numeric position from parenthetical text, or empty string."""
    pos_text = pos_text.strip().lower()
    if "valfri" in pos_text or "any" in pos_text:
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

# Key aliases: Swedish -> English
KEY_ALIASES = {
    "kampanj": "campaign",
    "annonsgrupp": "ad_group",
    "sökord": "keywords",
    "platsinriktning": "location_targeting",
    "slutlig webbadress": "final_url",
    "visningsadress – nivå 1": "path1",
    "visningsadress – nivå 2": "path2",
    "visningsadress - nivå 1": "path1",
    "visningsadress - nivå 2": "path2",
    # English equivalents
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
    """Normalize a Swedish/English key to internal name."""
    k = key.strip().lower()
    return KEY_ALIASES.get(k, k)


def parse_headline_or_desc(key: str) -> tuple[str, int, str] | None:
    """
    Parse a headline/description key like 'Rubrik 3 (position 2)'.
    Returns (type, number, position_csv_value) or None.
    """
    # Swedish patterns
    m = re.match(r"(?:rubrik|headline)\s+(\d+)\s*\(([^)]+)\)", key, re.IGNORECASE)
    if m:
        return ("headline", int(m.group(1)), parse_position(m.group(2)))
    m = re.match(r"(?:beskrivning|description)\s+(\d+)\s*\(([^)]+)\)", key, re.IGNORECASE)
    if m:
        return ("description", int(m.group(1)), parse_position(m.group(2)))
    return None


def parse_rsa_file(filepath: Path) -> list[dict]:
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
    Looks for a section titled 'Negativa sökord' or 'Negative keywords'.
    Returns a list of keyword strings.
    """
    content = filepath.read_text(encoding="utf-8")
    lines = content.splitlines()

    negatives = []
    in_negatives = False

    for line in lines:
        stripped = line.strip()
        # Detect section header
        if re.match(r"^#{1,3}\s+(Negativa sökord|Negative keywords)", stripped, re.IGNORECASE):
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

        # Analysis files contain "negativa sökord" or "negative keywords"
        if "negativa sökord" in content.lower() or "negative keywords" in content.lower():
            # Also check it's not an RSA file that mentions it
            if "kampanj:" not in first_lines and "campaign:" not in first_lines:
                analysis = f
                continue

        # RSA files start with "Kampanj:" or "Campaign:"
        first_content_line = ""
        for line in content.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                first_content_line = stripped.lower()
                break

        if first_content_line.startswith("kampanj:") or first_content_line.startswith("campaign:"):
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
    included_locations: list[str] | None = None,
    excluded_locations: list[str] | None = None,
) -> tuple[str, list[dict]]:
    """
    Generate all CSV rows. Returns (campaign_name, rows).

    included_locations / excluded_locations are lists of Google Ads geo target
    Criteria ID strings. Each ID produces its own row in the CSV. Excluded
    locations get Criterion Type "Excluded" so Google Ads Editor treats them
    as negative location targets.
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

    # 2. Location targeting rows – one row per included location
    if included_locations:
        for loc_id in included_locations:
            loc_row = make_row(Campaign=campaign_name, **{"Location ID": loc_id})
            rows.append(loc_row)

    # 2b. Excluded location rows
    if excluded_locations:
        for loc_id in excluded_locations:
            loc_row = make_row(
                Campaign=campaign_name,
                **{"Location ID": loc_id},
                **{"Criterion Type": "Excluded"},
            )
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

        # Keyword rows – Google Ads Editor requires match-type formatting in
        # BOTH the keyword text and the Criterion Type column. Phrase match
        # keywords must be wrapped in "...", exact match in [...], and broad
        # match left unformatted. This mirrors what we already do for negative
        # keywords and ensures Google Ads Editor correctly imports the match type.
        keywords = parse_keywords(ag["keywords_raw"])
        for kw, match_type in keywords:
            if match_type == "Phrase":
                formatted_kw = f'"{kw}"'
            elif match_type == "Exact":
                formatted_kw = f'[{kw}]'
            else:
                formatted_kw = kw  # Broad – no wrapping
            kw_row = make_row(
                Campaign=campaign_name,
                **{"Ad Group": ag["ad_group"]},
                Keyword=formatted_kw,
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


def write_csv(rows: list[dict], output_path: Path) -> None:
    """Write rows to a CSV file with UTF-8 BOM encoding."""
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=ALL_COLUMNS, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)


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
    parser.add_argument("--location-ids", default="",
                        help="Comma-separated Location IDs ([+|-]ID,...)")
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

    # Resolve locations – CLI flag takes precedence, otherwise parse from RSA files
    included_locations: list[str] = []
    excluded_locations: list[str] = []
    if args.location_ids:
        included_locations, excluded_locations = parse_location_ids(args.location_ids)
    elif ad_groups:
        loc_text = ad_groups[0].get("location_targeting", "")
        if loc_text:
            included_locations, excluded_locations = parse_location_ids(loc_text)

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
        included_locations=included_locations,
        excluded_locations=excluded_locations,
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
    stats["included_locations"] = included_locations
    stats["excluded_locations"] = excluded_locations
    stats["warnings"] = warnings

    import json
    print(json.dumps(stats, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
