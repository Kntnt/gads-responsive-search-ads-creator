---
name: gads-responsive-search-ads-creator
description: >
  Create Responsive Search Ads (RSA) for Google Ads based on a landing page analysis.
  Use this skill whenever the user wants to create RSA ads, ad copy, ad groups with ads,
  or responsive search ads – based on a landing page analysis or keyword cluster. Also
  trigger when the user wants to generate ad copy for Google Ads from an existing analysis
  file produced by gads-landing-page-analyzer. Trigger phrases include: "create ads",
  "RSA", "responsive search ads", "ad foundation", "ad group with ads",
  "Google Ads ads", "write ads for", "make ads", "ad copy",
  "generate ad copy", "ad text", or any request to produce
  Google Ads ad copy from a keyword list or landing page analysis. Even if the user just says
  "make ads from this analysis" or "now I want ads" after running a landing page
  analysis, this skill should trigger.
---

# Google Ads RSA Creator

You generate complete Responsive Search Ad (RSA) copy for Google Ads – one Markdown document per keyword cluster. The input is a landing page analysis (produced by `gads-landing-page-analyzer` or structured the same way) and the output is publication-ready ad copy with all fields Google Ads requires.

## Context: Where This Fits

This skill is the second link in a toolchain:

1. **gads-landing-page-analyzer** – Analyzes a landing page and produces a structured Markdown file with target segments, offers, keyword clusters, and negative keywords.
2. **gads-responsive-search-ads-creator** (this skill) – Reads the analysis and produces one Markdown file per keyword cluster with complete RSA copy.
3. **gads-editor-csv-creator** – Reads the analysis file and all RSA files and produces one CSV file ready for Google Ads Editor import.

Because the output of this skill feeds directly into gads-editor-csv-creator, the RSA document format must follow the exact field names and conventions specified below. The CSV creator parses these files programmatically.

## Why a dedicated skill for this

Writing good RSA copy is deceptively hard. Each headline has only 30 characters. Each description has only 90. Google combines them freely, so every element must work independently and in any combination. On top of that, LLMs are notoriously bad at counting characters – they routinely produce headlines that are 32 or 35 characters while believing they're within the limit. This skill addresses both challenges: it provides a framework for writing high-CTR, high-relevance ads, and it includes a validation script that programmatically enforces character limits after generation.

## Workflow

### Phase 1: Gather Prerequisites

**1. Analysis file**

You need a Markdown file containing a landing page analysis (produced by `gads-landing-page-analyzer`). The analysis file uses standardized **English section headings and labels** regardless of the document's content language. The structure you need to locate:

- `## Summary` – contains `**Page:**`, `**Sender:**`, `**Geography:**`, `**CTA:**`
- `## Target segments and offers` – segment → offer pairs
- `## Keyword clusters` – one or more `### Cluster name` subsections, each with `**Target segment:**`, `**Offer:**`, `**Search intent:**` (values: *navigational*, *informational*, *commercial investigation*, *transactional*), and a keyword list
- `## Negative keywords` – optional list of negative keywords

Note: while the headings and labels above are always in English, the cluster names, keyword text, segment descriptions, and other values are in the document's language (which matches the user's language).

If the user hasn't provided an analysis file, ask for one.

**2. Marketing context and geo targeting**

Check whether you already have background information about the sender (e.g. from a `CLAUDE.md` in the project root or other context already present in the conversation). This context may include the sender's brand voice, USPs, certifications, geographic targeting (as Criteria IDs or place names), and other campaign defaults. If such information exists, use it directly without asking – this includes geo targeting.

If you do **not** have background information, ask the user: *"Do you have supplementary information about the sender, the industry, the target audiences, or the offer? This can be text directly in the chat, a file to upload, a link to Google Drive, or similar. Such information improves the accuracy of the ads, but is not a requirement."*

### Phase 2: Generate Ad Copy (autonomous – do not interrupt)

Work through all keyword clusters without stopping. Deliver the result as finished Markdown files.

**For each keyword cluster**, create one Markdown document. All documents from the same analysis are saved in the same folder. Name the folder after the campaign (slugified).

#### Document Format

Each document uses this structure:

```
Campaign: <Name>
Ad group: <Name>
Keywords: <comma-separated list in quotes>
Location targeting: <semicolon-separated IDs, names, or proximity targets – or empty>
Final URL: <URL>
Display path – level 1: <max 15 chars>
Display path – level 2: <max 15 chars>
Headline 1 (any position): <max 30 chars>
Headline 2 (position 2): <max 30 chars>
...
Description 1 (any position): <max 90 chars>
...
```

**Copy-ready output – no annotations:** Each line after the colon and space must contain only the actual ad text that goes into Google Ads. Do not append character counts, category labels, or any other annotations (e.g. `[28 chars – keyword match]` or `[82 chars]`). The output should be directly copy-pasteable into Google Ads without any cleanup. The validation script handles character counting separately.

#### Field Rules

**Campaign:** Identical across all files from the same analysis. Short and recognizable in Google Ads UI and analytics. Example: "Camera surveillance".

**Ad group:** Identifies the keyword cluster. Starts with the campaign name, followed by a distinguishing suffix. Example: "Camera_surveillance_outdoor".

**Keywords:** Comma-separated. Each keyword is wrapped in characters that indicate its match type for Google Ads:
- `"keyword"` → Phrase match (the default and most common)
- `[keyword]` → Exact match
- `keyword` (bare, no wrapping) → Broad match

Example: `"outdoor camera surveillance", "outdoor video surveillance", [outdoor cameras]`

The downstream CSV creator parses these wrapping characters to set the correct match type in Google Ads Editor.

**Location targeting:** This line is always present. It controls geographic targeting in Google Ads. **Leave the value empty** (nothing after the colon and space) if no specific geo targeting is needed (e.g. the analysis says national scope without restrictions, or no geography is mentioned).

When geo targeting applies, list one or more locations **separated by semicolons**. Three formats are supported and can be mixed freely on the same line:

1. **Location ID** – a numeric Google Ads geo target Criteria ID (from https://developers.google.com/google-ads/api/data/geotargets). Example: `1012511` (Gothenburg).
2. **Location name** – a human-readable place name that Google Ads Editor recognizes. Example: `Kungsor, Vastmanland County, Sweden`.
3. **Proximity target** – a radius around a coordinate, written as `(<radius>km:<latitude>:<longitude>)`. Example: `(15km:58.767077:11.631213)`.

Examples:
- `Location targeting:` → no geo targeting (empty value)
- `Location targeting: 1012511` → Gothenburg only (by ID)
- `Location targeting: Kungsor, Vastmanland County, Sweden` → Kungsör (by name)
- `Location targeting: (15km:58.767077:11.631213)` → 15 km radius around a coordinate
- `Location targeting: (10km:57.809148:14.210866); (15km:58.767077:11.631213); 1012421; Kungsor, Vastmanland County, Sweden` → mixed formats

Sources for geo targeting information (checked in this order):
1. `CLAUDE.md` or other project-level context already in the conversation
2. The `**Geography:**` field in the analysis file's `## Summary` section
3. Ask the user (only if neither of the above provides a clear answer)

The downstream CSV creator reads this field and generates one location targeting row per entry in the output CSV. Location IDs are placed in the "Location ID" column; names and proximity targets are placed in the "Location" column. If the value is empty, no location targeting rows are created – the user sets targeting manually in Google Ads Editor.

**Final URL:** The landing page URL from the analysis.

**Display path – level 1 and 2:** Suggest fictional or real directory names (max 15 chars each) that help the searcher understand what awaits on the landing page. Example: "services" / "cameras".

#### Headlines (Headline 1–15)

RSA supports up to 15 headlines. Google places them in three possible positions. Each headline can be **unpinned** (any position – Google chooses placement) or **pinned** to position 1, 2, or 3.

**Pinning logic:**

- **Unpinned (any position):** Headlines containing one of the cluster's keywords. Google's algorithm naturally places these in position 1 because they match the search term best.
- **Position 2:** Headlines highlighting benefits, advantages, or credibility. Prevented from taking position 1 but shown frequently.
- **Position 3:** Headlines with CTA (call-to-action). Shown only when the ad gets three headlines – the right moment for a call to action.

**Format:** `Headline N (P)` where N is 1–15 and P is "any position", "position 1", "position 2", or "position 3".

**Character limit: Max 30 characters per headline (including spaces). This is a hard Google Ads limit.**

#### Descriptions (Description 1–4)

RSA supports up to 4 descriptions. Google places them in two possible positions.

**Pinning logic:**

- **Unpinned (any position):** Descriptions that develop the offer, mention keywords, or explain what the customer gets. Google's algorithm picks the most relevant one for position 1.
- **Position 2:** Pure CTA descriptions or calls to action. Shown only when the ad gets two descriptions, functioning as a closer.

**Format:** `Description N (P)` where N is 1–4 and P is "any position", "position 1", or "position 2".

**Character limit: Max 90 characters per description (including spaces). This is a hard Google Ads limit.**

**Rules for descriptions:**
1. Develop the message from the headlines – don't repeat them.
2. Highlight USPs that didn't fit in the headlines.
3. At least one description must be a pure CTA (pinned to position 2).

#### Principles for High-CTR, High-Relevance Ad Copy

The ads must optimize for two goals: high click-through rate (CTR) and high relevance between keywords and ad text.

**Keyword relevance (Ad Relevance)**

This is the single most important factor for Quality Score.

- At least 3–4 headlines must contain the cluster's primary keyword or close variants. They don't need to be verbatim – inflections, synonyms, and natural rephrasings work – but the core term must be immediately recognizable.
- At least 3 other headlines must *not* contain keywords – they give Google variation to combine and prevent the ad from feeling repetitive.
- At least one description must mention the keyword or offer in plain text.
- The ad copy must reflect the search intent from the analysis. Transactional intent requires action-oriented copy ("Order", "Book", "Get a quote"). Informational intent requires knowledge-oriented copy ("How it works…", "Guide to…").

**Headline strategy for CTR**

Each headline has only 30 characters. Every word must earn its place.

- Write headlines in varying lengths – some short (15–20 chars), some using the full space (28–30 chars). Variation gives Google more combination options and fits more screen sizes.
- Each headline must make sense on its own – Google can combine any of them.
- No repetition: no headline should convey the same message as another, even with different words.
- Headlines should cover these categories with approximate distribution across 15 headlines:
  - **Keyword match (4–5):** Headlines directly matching what the searcher types, with variants of the cluster's keywords. ("Camera surveillance for HOA")
  - **Benefit/advantage (3–4):** Concrete outcome the searcher gets. ("Safer for residents")
  - **Credibility/social proof (2–3):** Experience, certifications, customer count. ("30 years of experience")
  - **Differentiation (2–3):** What sets the sender apart from competitors. ("Our own 24/7 monitoring center")
  - **CTA (2–3):** Clear calls to action with variation. ("Request a quote today")
- Use specific, concrete words over vague ones. "Free needs assessment" beats "Contact us". Numbers ("30 years of experience", "Response within 24h") increase CTR.
- No exclamation marks in headlines – Google doesn't allow them.

**Description strategy for CTR**

Descriptions have 90 characters – enough for one full sentence, but not more.

- Place the most important information at the start. On mobile, text can be truncated.
- Use active verbs and action-oriented language. "We design and install" beats "Design and installation services".
- At least one description should be a pure CTA with a clear call to action and possibly an incentive ("Request a free quote – response within 24h").
- Other descriptions should develop the offer, address objections, or highlight USPs that didn't fit in headlines.
- Avoid generic phrases like "We offer high-quality services" – they waste characters without adding meaning.

**Combination harmony**

Since Google combines headlines and descriptions freely, every combination of unpinned elements must produce an ad that is coherent, not contradictory, and not repetitive:

- Avoid two headlines that mention the same keyword in the exact same form – if Google shows them side by side, the ad looks clumsy.
- Headline + description should complement each other: if the headline says *what*, the description should explain *why* or *how*.
- Avoid the same CTA appearing in both a headline and a description – it becomes redundant if shown together.

**Adapt to sender context**

If marketing context or other sender context is available:

- Tone and word choice should match the brand's voice.
- USPs, certifications, customer promises, and offers from the context should be woven into headlines and descriptions.
- If the sender has a known market position (e.g. industry leader, local player, affordable alternative), this should come through in the ad text.

#### Keyword Coverage – Additional Ads if Needed

If not all keywords in the cluster appear among headlines and descriptions in the first ad, suggest additional ads in the same ad group (max 3 ads total per ad group). Having just one RSA per ad group is strongly preferred. All ads in the same ad group go in the same document, separated by `---` on its own line. Each ad after the first inherits the ad group's campaign, ad group name, keywords, and targeting from the header – only headlines, descriptions, display paths, and final URL vary.

#### Character Limit Validation

After generating all Markdown files, run the bundled validation script:

```bash
python <skill-path>/scripts/validate_rsa.py <folder-with-markdown-files>
```

The script checks: headlines ≤ 30 chars, descriptions ≤ 90 chars, display path levels ≤ 15 chars. If violations are found, fix them and re-run until everything passes.

This step is essential because LLMs count characters unreliably. The script is the safety net.

## Worked Example

See `references/worked-example.md` for a complete RSA document for the cluster "Camera surveillance for HOAs and apartment buildings". It demonstrates the correct format, pinning logic, category distribution, and character counting.

## Do / Don't

| Don't | Do | Why |
|-------|-----|-----|
| "Great camera surveillance for HOA" | "Camera surveillance for HOA" | "Great" is filler – says nothing, wastes 6 chars. |
| "Contact us" | "Book free consultation" | Generic CTA vs specific CTA with incentive. Specific gets higher CTR. |
| "We offer professional security solutions of high quality" | "We design, install, and service camera systems for HOAs." | Vague and generic vs concrete with active verbs. |
| "Camera surveillance HOA" + "Camera surveillance for HOA" | "Camera surveillance HOA" + "Cameras in stairwells and waste rooms" | Near-identical headlines → waste. Better to vary and cover more keywords. |
| "Safe HOA. Contact us today for more information about our services." | "Camera surveillance for garages, stairwells, and waste rooms. Tailored for HOAs." | Description should be specific and informative – not vague with a generic CTA. |

## Typography

Use correct Unicode characters:

- En dash: – (U+2013)
- Em dash: — (U+2014)
- Quotation marks: "…" (U+201C/U+201D)
- Arrow: → (U+2192)

## Language

Respond in the same language the user used. The ads must be in the same language as the keywords in the analysis file.
