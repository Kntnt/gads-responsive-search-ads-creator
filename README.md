# gads-editor-csv-creator

A Claude skill that generates a Google Ads Editor CSV import file from analysis and RSA Markdown files.

## What it does

Given a folder of Markdown files produced by [gads-landing-page-analyzer](https://github.com/Kntnt/gads-landing-page-analyzer) and [gads-responsive-search-ads-creator](https://github.com/Kntnt/gads-responsive-search-ads-creator), this skill produces a single CSV file ready for import into Google Ads Editor -- complete with campaign settings, location targeting, ad groups, keywords, RSA ads, and negative keywords.

This is the third and final link in a toolchain:

1. **gads-landing-page-analyzer** -- analyzes a landing page and produces keyword clusters
2. **gads-responsive-search-ads-creator** -- generates RSA ad copy for each cluster
3. **gads-editor-csv-creator** (this skill) -- turns it all into a Google Ads Editor CSV

## When it triggers

The skill activates when you ask Claude to create a Google Ads Editor CSV, import file, or export ad copy to Editor format. Trigger phrases include "CSV", "Google Ads Editor", "import file", "importfil", "Editor CSV", "skapa CSV", and similar. It also triggers on "next step" after running the RSA creator.

## Installation

In Claude Desktop (Cowork), install the packaged `.skill` file via the skill installer. Alternatively, copy this repository into your skills directory.

## Repo structure

```
SKILL.md                           Main skill instructions
scripts/
  generate_csv.py                  CSV generation script (parsing, validation, output)
references/
  exempel/                         Example input files (analysis + RSA Markdown)
```

## Configuration

During CSV generation, the skill asks for:

- **Daily budget** -- campaign budget (optional)
- **Target CPA** -- target cost per acquisition for the Maximize conversions bid strategy
- **Tracking settings** -- default, suggested UTM template, or custom

## Opinionated defaults

The skill follows best practices as defaults:

- **Maximize conversions with Target CPA** as the bid strategy
- **Nominal ad group bids** (0.01) for Default max. CPC, Max. CPM, Target CPV, and Target CPM -- required by Google Ads Editor even when using smart bidding (the values have no effect on actual bidding)
- **One location row per target location** -- location targeting uses numeric Google Ads Criteria IDs (format: `[+|-]ID, ...`). Each ID produces its own row. IDs prefixed with `-` are excluded (negative targeting).
- **Phrase match** as the default keyword match type
- **Google Search only** -- no Search Partners
- **Campaign paused, everything else enabled** at creation -- enable the campaign to go live
- **EU political ads declaration** set to "No" by default
- **Negative keywords at campaign level** with phrase match

## Future extension (v2)

A future version will support **updating existing campaigns** using `#Original` columns. This requires the user to provide an exported CSV from Google Ads Editor (current state) alongside updated RSA files. The skill will compare and produce `#Original` columns for changed fields. This is not in scope for v1.

## License

MIT
