---
name: gads-editor-csv-creator
description: >
  Generate a Google Ads Editor CSV import file from analysis and RSA Markdown files.
  ALWAYS use this skill when the user mentions Google Ads Editor, CSV export, import file,
  or turning ad copy / RSA files / keyword clusters into a Google Ads Editor file. This is
  the final step in the gads toolchain – after gads-landing-page-analyzer and
  gads-responsive-search-ads-creator have produced Markdown output, this skill creates a
  ready-to-import CSV with campaigns, ad groups, keywords, RSA ads, and negative keywords.
  Trigger on: "CSV", "Google Ads Editor", "import file", "importfil", "Editor CSV",
  "export to Editor", "skapa CSV", "create the CSV", "gör CSV", "make the import file",
  "GAds Editor", "bulk import", "editor import", "now create the file", "exportera",
  "generate the file", or "next step" / "now what" after RSA creation.
  When in doubt, trigger – this skill handles all Google Ads Editor CSV generation.
---

# Google Ads Editor CSV Creator

You generate a single CSV file that can be imported into Google Ads Editor to create complete Search campaigns: campaign settings, location targeting, ad groups, keywords, RSA ads, and negative keywords – all from the Markdown files produced by the earlier skills in the chain.

## Context: Where This Fits

This skill is the third and final link in a toolchain:

1. **gads-landing-page-analyzer** – Analyzes a landing page and produces a structured Markdown file with target segments, offers, keyword clusters, and negative keywords.
2. **gads-responsive-search-ads-creator** – Reads the analysis and produces one Markdown file per keyword cluster with complete RSA copy (headlines, descriptions, keywords, URLs, etc.).
3. **gads-editor-csv-creator** (this skill) – Reads the analysis file and all RSA files and produces one CSV file ready for Google Ads Editor import.

## Input Format

The skill reads a folder containing:

1. **One analysis file** (Markdown) – produced by gads-landing-page-analyzer. Contains negative keywords (in the "Negativa sökord" or "Negative keywords" section), landing page URL, geographic scope, and target segments.

2. **One or more RSA files** (Markdown) – produced by gads-responsive-search-ads-creator. Each file describes an ad group with this structure:

```
Campaign: <name>
Ad group: <name>
Keywords: "kw1", "kw2", [kw3], kw4
Location targeting: <geo targeting>
Final URL: <URL>
Display path – level 1: <max 15 chars>
Display path – level 2: <max 15 chars>
Headline N (P): <text>
Description N (P): <text>
```

Legacy Swedish keys (`Kampanj:`, `Annonsgrupp:`, `Sökord:`, `Platsinriktning:`, `Slutlig webbadress:`, `Visningsadress – nivå 1/2:`, `Rubrik N:`, `Beskrivning N:`) are also supported for backward compatibility.

A single RSA file may contain **multiple ads** for the same ad group (max 3), separated by `---`. Each ad after the first inherits the ad group's campaign, ad group name, keywords, and targeting from the header – only headlines, descriptions, display paths, and final URL vary.

### Parsing Rules

Every line containing `: ` (colon followed by space) is a key-value pair. The value after `: ` is copied verbatim (stripped of leading/trailing whitespace).

**Keyword match types** are determined by the surrounding characters:
- `"keyword"` → Phrase match
- `[keyword]` → Exact match
- `keyword` (no surrounding quotes or brackets) → Broad match

**Headline positions** map from the parenthetical to CSV values:
- `(any position)` → empty (unpinned)
- `(position 1)` → `1`
- `(position 2)` → `2`
- `(position 3)` → `3`

**Description positions** follow the same logic (only positions 1 and 2 are valid for descriptions).

## Workflow

### Phase 1: Gather Prerequisites (interactive)

Ask all necessary questions in **a single message**. Adapt based on what is already known from the conversation.

**1. Input folder**

If the user hasn't pointed to a folder containing analysis and RSA files, ask where they are. If you can see them in the workspace already, confirm the path.

**2. Daily budget**

Ask: *"What daily budget do you want for the campaign(s)? Enter an amount (e.g. 200). Leave blank if you prefer to set the budget manually after importing into Google Ads Editor."*

**3. Target CPA**

Ask: *"What target CPA (cost per acquisition) do you want for the campaign(s)? Enter an amount in the account's currency (e.g. 150). This will be used with the 'Maximize conversions' bid strategy."*

**4. Tracking settings**

Present three options:
- **Option 1 (default):** Use a suggested UTM template that works with GA4, Matomo, and other tools:
  - Tracking template: `{lpurl}`
  - Final URL suffix: `utm_source=google&utm_medium=cpc&utm_campaign={campaignid}&utm_term={keyword}&utm_content={creative}&mtm_group={adgroupid}&mtm_cid={gclid}`
- **Option 2:** Leave empty – use the account's default tracking settings.
- **Option 3:** Enter your own tracking template and/or suffix.

**5. Summary and confirmation**

Before generating, show a summary of all settings that will be used:
- Bid strategy: Maximize conversions (Target CPA: [user-specified amount])
- Networks: Google Search only
- Status: Campaign paused; ad groups, keywords, and ads enabled (activate by enabling the campaign)
- Negative keywords: Campaign level, phrase match
- Language targeting: [detected from analysis/keywords]
- Location targeting: [from RSA files]
- Count: N campaigns, N ad groups, N keywords, N ads found

Ask the user to confirm or suggest changes. If changes are requested, show an updated summary and ask again.

### Phase 2: Generate CSV (autonomous)

Once the user confirms, work without interruption:

1. **Parse all RSA files.** Extract campaign name, ad group names, keywords with match types, headlines with positions, descriptions with positions, URLs, and display paths. Use the bundled script for reliable parsing:

```bash
python <skill-path>/scripts/generate_csv.py <input-folder> [options]
```

The script handles all parsing, validation, and CSV generation. See the Script Reference section below for usage details.

2. **Parse the analysis file** to extract negative keywords from the "Negativa sökord" or "Negative keywords" section.

3. **Validate character limits:**
   - Headlines: max 30 characters
   - Descriptions: max 90 characters
   - Display paths: max 15 characters each

   If violations are found, **warn the user** in the chat message but still generate the CSV. List all violations so the user can fix them.

4. **Detect language** from the keywords and analysis. Map to Google Ads language code (e.g. Swedish → `sv`, English → `en`).

5. **Parse location targeting** from the RSA files. The `Platsinriktning` / `Location targeting` field uses a compact ID-based format:

   ```
   [+|-]<ID>[, [+|-]<ID>]*
   ```

   where `<ID>` is a numeric Google Ads geo target Criteria ID (from https://developers.google.com/google-ads/api/data/geotargets). Prefix rules:
   - No prefix or `+` prefix → location is **included** (targeted)
   - `-` prefix → location is **excluded** (negative targeting)

   Examples:
   - `1012511` → include Gothenburg
   - `+21000, -1012511` → include Stockholm County but exclude Gothenburg
   - `21000, 9067792, 1012335` → include multiple locations

   The script parses this by stripping whitespace, splitting on commas, and separating included/excluded IDs. Included locations generate rows with `Location ID` set. Excluded locations generate rows with `Location ID` set and `Criterion Type` set to `Excluded`.

6. **Generate the CSV file** with all rows in hierarchical order.

7. **Save the CSV file** with name `<CampaignName>_<YYYY-MM-DD>.csv` (campaign name slugified, today's date).

8. **Present the result** with a summary including: filename, counts (campaigns, ad groups, keywords by match type, ads, negative keywords), any warnings, and import instructions.

## CSV Output Format

### General Rules

- Standard Google Ads Editor column headers (English) on the first row.
- Comma-separated values.
- UTF-8 encoding with BOM (`\xEF\xBB\xBF`) for compatibility with Excel and Google Ads Editor.
- Fields containing commas, quotes, or newlines are quoted; internal quotes are doubled.
- Leave fields empty (not `[]`) for values that should not be changed.

### Row Types and Order (hierarchical)

The CSV contains these row types in this order:

1. **Campaign row** – one per campaign.
2. **Location targeting rows** – one per location, directly after the campaign row.
3. **Per ad group (repeat for each):**
   a. **Ad group row**
   b. **Keyword rows** – one per keyword
   c. **Ad row(s)** – one per RSA ad (typically 1, max 3)
4. **Campaign-level negative keywords** – all negatives from the analysis, at the end of the file.

### Columns by Row Type

#### Campaign Row

| Column | Value |
|--------|-------|
| Campaign | Campaign name from RSA files |
| Campaign type | `Search` |
| Campaign daily budget | User-specified budget (or empty) |
| Language | Language code detected from analysis (e.g. `sv`) |
| Networks | `Google Search` |
| Bid strategy type | `Maximize conversions` |
| Target CPA | User-specified target CPA amount |
| Campaign status | `Paused` |
| EU Political Ads | `No` |
| Tracking template | Per user choice |
| Final URL suffix | Per user choice |

#### Location Targeting Rows

The location targeting field in RSA files contains a comma-separated list of numeric Google Ads Criteria IDs, optionally prefixed with `+` (include) or `-` (exclude). The script creates **one row per location ID** – this is what Google Ads Editor requires.

For **included** locations:

| Column | Value |
|--------|-------|
| Campaign | Campaign name |
| Location ID | Google Ads Criteria ID (e.g. `2752` for Sweden) |

For **excluded** locations (prefixed with `-`):

| Column | Value |
|--------|-------|
| Campaign | Campaign name |
| Location ID | Google Ads Criteria ID |
| Criterion Type | `Excluded` |

#### Ad Group Row

| Column | Value |
|--------|-------|
| Campaign | Campaign name |
| Ad Group | Ad group name from RSA file |
| Ad Group status | `Enabled` |
| Default max. CPC | `0.01` |
| Max. CPM | `0.01` |
| Target CPV | `0.01` |
| Target CPM | `0.01` |

The nominal bid values (0.01) are included because Google Ads Editor requires ad group-level bids even when using a smart bid strategy like "Maximize conversions". These values have no practical effect – the smart bid strategy overrides them – but their absence causes import warnings in Google Ads Editor.

#### Keyword Row (one per keyword)

| Column | Value |
|--------|-------|
| Campaign | Campaign name |
| Ad Group | Ad group name |
| Keyword | The keyword text with match-type formatting: `"keyword"` for phrase match, `[keyword]` for exact match, or plain text for broad match. Google Ads Editor requires this "power posting" format in addition to the Criterion Type column. |
| Criterion Type | `Broad`, `Phrase`, or `Exact` |
| Status | `Enabled` |

#### Ad Row (RSA)

| Column | Value |
|--------|-------|
| Campaign | Campaign name |
| Ad Group | Ad group name |
| Ad Name | `{AdGroup}_RSA_1` (or `_RSA_2`, `_RSA_3` for additional ads) |
| Ad type | `Responsive search ad` |
| Status | `Enabled` |
| Final URL | Final URL from RSA file |
| Path 1 | Display path level 1 |
| Path 2 | Display path level 2 |
| Headline 1 | Headline 1 text |
| Headline 1 position | Position value (empty/1/2/3) |
| ... | ... (up to Headline 15 + position) |
| Description 1 | Description 1 text |
| Description 1 position | Position value (empty/1/2) |
| ... | ... (up to Description 4 + position) |

#### Negative Keyword Row (campaign level)

| Column | Value |
|--------|-------|
| Campaign | Campaign name |
| Keyword | The negative keyword in phrase match format (wrapped in `"..."`) |
| Criterion Type | `Campaign negative` |

Negative keywords default to phrase match. Each keyword is wrapped in quotation marks in the Keyword column.

## Script Reference

The bundled Python script `scripts/generate_csv.py` handles all parsing, validation, and CSV generation. It is the backbone of this skill – use it rather than writing CSV generation logic from scratch.

**Usage:**

```bash
python <skill-path>/scripts/generate_csv.py \
  --input-dir <folder-with-md-files> \
  --output-dir <where-to-save-csv> \
  [--budget <daily-budget>] \
  [--target-cpa <amount>] \
  [--tracking-template <template>] \
  [--final-url-suffix <suffix>] \
  [--language <lang-code>] \
  [--location-ids [+|-]<ID>,...]
```

The script:
- Auto-detects which file is the analysis (looks for "Negativa sökord" / "Negative keywords" section) and which are RSA files (looks for "Kampanj:" / "Campaign:" on the first line).
- Parses all key-value pairs from RSA files, including multi-ad files separated by `---`.
- Extracts negative keywords from the analysis file.
- Parses location targeting IDs (format: `[+|-]ID, ...`) and creates one CSV row per location, with excluded locations getting `Criterion Type: Excluded`.
- Adds nominal bid values (0.01) on ad group rows to satisfy Google Ads Editor's requirement for ad group-level bids when using smart bid strategies.
- Validates character limits and prints warnings to stderr.
- Generates the CSV with proper encoding (UTF-8 BOM), quoting, and column order.
- Outputs the filename and statistics as JSON to stdout.

If `--language` is not specified, the script detects it from the keyword content. If `--location-ids` is not specified, it reads the "Platsinriktning" / "Location targeting" field from RSA files and parses the ID list (format: `[+|-]ID, ...`).

## Design Principles

This skill is opinionated – it follows best practices as defaults and requires the user to actively choose to deviate:

- **One campaign, many ad groups** is the standard structure. Each ad group has 1–3 RSA ads and a cluster of thematically related keywords.
- **Phrase match is the default** for regular keywords (marked with `"..."` in the RSA files).
- **Exact match** for keywords marked with `[...]`.
- **Broad match** for keywords without any surrounding characters.
- **Maximize conversions with Target CPA** as the bid strategy. The user is asked for their desired target CPA during Phase 1.
- **Google Search only** – no Search Partners, for maximum control.
- **Campaign paused, everything else enabled** at creation – enable the campaign to go live.
- **Negative keywords at campaign level** with phrase match.

## Language

Respond in the same language the user uses. The CSV file always uses English column headers (Google Ads Editor requires this).

## Typography

Use proper Unicode characters in all output:
- En dash: – (U+2013)
- Quotation marks: "..." (U+201C/U+201D)
- Arrow: → (U+2192)
