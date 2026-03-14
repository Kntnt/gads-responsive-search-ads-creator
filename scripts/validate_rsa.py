#!/usr/bin/env python3
"""
Validate RSA ad copy character limits in Markdown and CSV files.

Usage:
    python validate_rsa.py <path>           # Validate Markdown file(s)
    python validate_rsa.py <path> --csv     # Validate CSV file(s)

Exit codes:
    0 = all OK
    1 = violations found
"""

import sys
import re
import csv
import os
from pathlib import Path


HEADLINE_MAX = 30
DESCRIPTION_MAX = 90
DISPLAY_PATH_MAX = 15


def validate_markdown_file(filepath: str) -> list[dict]:
    """Parse a Markdown RSA file and check character limits."""
    violations = []
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n")
    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Match headlines: "Headline N (P): text" (English)
        m = re.match(r"^Headline\s+(\d+)\s*\([^)]*\)\s*:\s*(.+)$", stripped)
        if m:
            num = m.group(1)
            text = m.group(2).strip()
            # Remove trailing bracket annotations like [23 chars – ...]
            text = re.sub(r"\s*\[.*\]\s*$", "", text).strip()
            char_count = len(text)
            if char_count > HEADLINE_MAX:
                violations.append({
                    "file": filepath,
                    "line": i,
                    "field": f"Headline {num}",
                    "limit": HEADLINE_MAX,
                    "actual": char_count,
                    "text": text,
                })
            continue

        # Match descriptions: "Description N (P): text" (English)
        m = re.match(r"^Description\s+(\d+)\s*\([^)]*\)\s*:\s*(.+)$", stripped)
        if m:
            num = m.group(1)
            text = m.group(2).strip()
            text = re.sub(r"\s*\[.*\]\s*$", "", text).strip()
            char_count = len(text)
            if char_count > DESCRIPTION_MAX:
                violations.append({
                    "file": filepath,
                    "line": i,
                    "field": f"Description {num}",
                    "limit": DESCRIPTION_MAX,
                    "actual": char_count,
                    "text": text,
                })
            continue

        # Match display path level 1 (English)
        m = re.match(r"^Display path\s*[–-]\s*level\s*1\s*:\s*(.+)$", stripped)
        if m:
            text = m.group(1).strip()
            text = re.sub(r"\s*\[.*\]\s*$", "", text).strip()
            char_count = len(text)
            if char_count > DISPLAY_PATH_MAX:
                violations.append({
                    "file": filepath,
                    "line": i,
                    "field": "Display path – level 1",
                    "limit": DISPLAY_PATH_MAX,
                    "actual": char_count,
                    "text": text,
                })
            continue

        # Match display path level 2 (English)
        m = re.match(r"^Display path\s*[–-]\s*level\s*2\s*:\s*(.+)$", stripped)
        if m:
            text = m.group(1).strip()
            text = re.sub(r"\s*\[.*\]\s*$", "", text).strip()
            char_count = len(text)
            if char_count > DISPLAY_PATH_MAX:
                violations.append({
                    "file": filepath,
                    "line": i,
                    "field": "Display path – level 2",
                    "limit": DISPLAY_PATH_MAX,
                    "actual": char_count,
                    "text": text,
                })
            continue

    return violations


def validate_csv_file(filepath: str) -> list[dict]:
    """Parse a CSV file in Google Ads Editor format and check character limits."""
    violations = []
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row_num, row in enumerate(reader, 2):  # row 1 is header
            # Check headlines
            for i in range(1, 16):
                col = f"Headline {i}"
                if col in row and row[col].strip():
                    text = row[col].strip()
                    if len(text) > HEADLINE_MAX:
                        violations.append({
                            "file": filepath,
                            "line": row_num,
                            "field": col,
                            "limit": HEADLINE_MAX,
                            "actual": len(text),
                            "text": text,
                        })

            # Check descriptions
            for i in range(1, 5):
                col = f"Description {i}"
                if col in row and row[col].strip():
                    text = row[col].strip()
                    if len(text) > DESCRIPTION_MAX:
                        violations.append({
                            "file": filepath,
                            "line": row_num,
                            "field": col,
                            "limit": DESCRIPTION_MAX,
                            "actual": len(text),
                            "text": text,
                        })

            # Check paths
            for i, col in enumerate(["Path 1", "Path 2"], 1):
                if col in row and row[col].strip():
                    text = row[col].strip()
                    if len(text) > DISPLAY_PATH_MAX:
                        violations.append({
                            "file": filepath,
                            "line": row_num,
                            "field": col,
                            "limit": DISPLAY_PATH_MAX,
                            "actual": len(text),
                            "text": text,
                        })

    return violations


def collect_files(path: str, is_csv: bool) -> list[str]:
    """Collect files to validate from a path (file or directory)."""
    ext = ".csv" if is_csv else ".md"
    p = Path(path)
    if p.is_file():
        return [str(p)]
    elif p.is_dir():
        return sorted(str(f) for f in p.rglob(f"*{ext}"))
    else:
        print(f"Error: {path} is not a file or directory.")
        sys.exit(2)


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate_rsa.py <path> [--csv]")
        sys.exit(2)

    path = sys.argv[1]
    is_csv = "--csv" in sys.argv

    files = collect_files(path, is_csv)
    if not files:
        print(f"No {'CSV' if is_csv else 'Markdown'} files found in {path}")
        sys.exit(2)

    all_violations = []
    for filepath in files:
        if is_csv:
            violations = validate_csv_file(filepath)
        else:
            violations = validate_markdown_file(filepath)
        all_violations.extend(violations)

    if all_violations:
        print(f"\n{'='*60}")
        print(f"VALIDATION FAILED – {len(all_violations)} violation(s) found")
        print(f"{'='*60}\n")
        for v in all_violations:
            print(f"  File: {v['file']}")
            print(f"  Field: {v['field']} (line {v['line']})")
            print(f"  Limit: {v['limit']} chars | Actual: {v['actual']} chars (+{v['actual'] - v['limit']})")
            print(f"  Text: \"{v['text']}\"")
            print()
        sys.exit(1)
    else:
        print(f"\n{'='*60}")
        print(f"VALIDATION PASSED – all {len(files)} file(s) OK")
        print(f"{'='*60}")
        for f in files:
            print(f"  ✓ {f}")
        print()
        sys.exit(0)


if __name__ == "__main__":
    main()
