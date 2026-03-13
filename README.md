# gads-responsive-search-ads-creator

A Claude skill that generates complete Responsive Search Ad (RSA) copy for Google Ads from a landing page analysis.

## What it does

Takes a structured landing page analysis (produced by [gads-landing-page-analyzer](https://github.com/AnnonsKansen/gads-landing-page-analyzer) or similar) and generates publication-ready RSA ad copy – one Markdown document per keyword cluster.

Each document includes 15 headlines, 4 descriptions, display paths, keyword lists, and pinning logic – all within Google Ads character limits.

## Why

Writing RSA copy is deceptively hard. Headlines max out at 30 characters, descriptions at 90, and Google combines them freely. On top of that, LLMs count characters unreliably. This skill solves both: it provides a framework for high-CTR, high-relevance ads, and a validation script that enforces limits programmatically.

## Structure

```
gads-responsive-search-ads-creator/
├── SKILL.md                        # Skill instructions
├── scripts/
│   └── validate_rsa.py             # Character limit validator
└── references/
    └── worked-example.md           # Complete example RSA document
```

## Validation script

The bundled `validate_rsa.py` checks all character limits after generation:

```bash
python scripts/validate_rsa.py path/to/output/
```

Exit code 0 means all OK; exit code 1 means violations found (with details).

## Suggested workflow

1. Create a project directory for the campaign you're working on – if one doesn't already exist.
2. Add a `CLAUDE.md` file in the project root with background information about the sender, industry, target audiences, value propositions, and anything else that's relevant. The skill reads this file automatically and uses it to improve the ad copy.
3. Run the landing page analysis first (using `gads-landing-page-analyzer`) to produce the analysis file the skill needs as input.
4. Trigger the skill with a prompt like: *"Create RSA ads based on the analysis in analysis.md"*

## License

MIT
