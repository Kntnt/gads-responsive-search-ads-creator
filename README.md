# gads-responsive-search-ads-creator

A Claude skill that generates complete Responsive Search Ad (RSA) copy for Google Ads -- one Markdown document per keyword cluster.

## What it does

Given a landing page analysis produced by [gads-landing-page-analyzer](https://github.com/Kntnt/gads-landing-page-analyzer), this skill generates publication-ready RSA ad copy with all fields Google Ads requires: campaign name, ad group, keywords with match types, location targeting (numeric Criteria IDs), display paths, 15 headlines, and 4 descriptions -- all within Google's character limits.

This is the second link in a toolchain:

1. **gads-landing-page-analyzer** -- analyzes a landing page and produces keyword clusters with standardized English headings
2. **gads-responsive-search-ads-creator** (this skill) -- generates RSA ad copy for each cluster
3. **gads-editor-csv-creator** -- turns it all into a Google Ads Editor import file

## When it triggers

The skill activates when you ask Claude to create RSA ads, ad copy, or responsive search ads based on a landing page analysis. Trigger phrases include "create ads", "RSA", "responsive search ads", "ad copy", "make ads", and similar. It also triggers on "now I want ads" after running the landing page analyzer.

## Installation

In Claude Desktop (Cowork), install the packaged `.skill` file via the skill installer. Alternatively, copy this repository into your skills directory.

## Repo structure

```
SKILL.md                           Main skill instructions
scripts/
  validate_rsa.py                  Character limit validation script
  generate_csv.py                  CSV generation script (from gads-editor-csv-creator, for testing)
references/
  worked-example.md                Complete worked example for one cluster
  exempel/                         Full set of example RSA files + analysis
evals/
  evals.json                       Test case definitions
```

## Input format

The skill reads an analysis file with standardized English headings:

- `## Summary` with `**Page:**`, `**Sender:**`, `**Geography:**`, `**CTA:**`
- `## Target segments and offers`
- `## Keyword clusters` with `**Target segment:**`, `**Offer:**`, `**Search intent:**`
- `## Negative keywords`

Note: while headings and labels are always in English, the content (cluster names, keywords, descriptions) follows the document's language.

## Output format

Each RSA file uses English field names for downstream compatibility with gads-editor-csv-creator:

```
Campaign: <name>
Ad group: <name>
Keywords: "kw1", "kw2", [kw3], kw4
Location targeting: <Criteria ID(s) or empty>
Final URL: <URL>
Display path – level 1: <max 15 chars>
Display path – level 2: <max 15 chars>
Headline 1 (any position): <max 30 chars>
...
Description 1 (any position): <max 90 chars>
...
```

### Key conventions

- **Keywords** use match-type wrapping: `"keyword"` for phrase, `[keyword]` for exact, bare for broad
- **Location targeting** line is always present. Leave the value empty when no geo targeting is needed. When targeting specific areas, uses numeric Google Ads Criteria IDs (e.g. `1012511` for Gothenburg). Geo targeting info can come from CLAUDE.md, the analysis file, or the user.
- **Multiple ads** in the same ad group are separated by `---`
- **Headline/Description positions**: `(any position)`, `(position 1)`, `(position 2)`, `(position 3)`

## Character limits

Google Ads enforces strict character limits:

- Headlines: max 30 characters
- Descriptions: max 90 characters
- Display paths: max 15 characters each

The bundled `validate_rsa.py` script programmatically checks these limits after generation.

## License

MIT
