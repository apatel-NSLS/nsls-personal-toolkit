#!/usr/bin/env python3
"""
enrich_profiles_from_ramp.py — add Ramp payment data to Obsidian profiles using vendor_mapping.json.

⚠ PII HANDLING:
- Reads from %LOCALAPPDATA%\\nsls-private\\ramp\\ (user-local)
- Writes into $OBSIDIAN_VAULT_PATH/30-people/*.md
- Only enriches profiles explicitly mapped in vendor_mapping.json
- Idempotent: inserts or updates `## Ramp Payments (1099 / contractor)` section
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
CACHE_DIR = LOCALAPPDATA / "nsls-private" / "ramp"

def load_vault_path() -> Path:
    env_path = Path.home() / ".claude" / "local-plugins" / "nsls-personal-toolkit" / ".env"
    for line in env_path.read_text().splitlines():
        if line.startswith("OBSIDIAN_VAULT_PATH="):
            return Path(line.split("=", 1)[1].strip())
    sys.exit(1)

VAULT_PATH = load_vault_path()
PEOPLE_DIR = VAULT_PATH / "30-people"
SECTION_MARKER = "## Ramp Payments (1099 / contractor)"


def build_section(mapping: dict, sync_date: str) -> str:
    """Build the ## Ramp Payments section. Reads from both old and new field formats."""
    name = mapping.get('ramp_vendor_name') or mapping.get('person_name') or '—'
    lines = [
        SECTION_MARKER,
        f"*Synced from local Ramp cache + Contractor Payments Tracking sheet. Last sync: {sync_date}. Vendor mapping: `{name}` → this person. User-local PII.*",
        "",
        f"### Ramp vendor entity",
        f"- **Entity name:** {name}",
        f"- **Relationship:** {mapping.get('relationship_type', '1099 contractor')}",
        f"- **Department (per sheet):** {mapping.get('department_in_sheet') or mapping.get('department') or '—'}",
        f"- **Country / location:** {mapping.get('country', '—')}",
    ]
    if mapping.get('invoice_pattern'):
        lines.append(f"- **Invoice pattern:** {mapping['invoice_pattern']}")
    if mapping.get('cadence'):
        lines.append(f"- **Cadence:** {mapping['cadence']}")
    lines.append("")

    lines.append("### FY26 budget + year-to-date")
    if mapping.get('fy26_budget') is not None:
        lines.append(f"- **FY26 budget:** ${mapping['fy26_budget']:,.2f}")
    ytd = mapping.get('2026_ytd_paid') or mapping.get('ytd_2026')
    if ytd is not None:
        lines.append(f"- **2026 YTD paid:** ${ytd:,.2f}")
    if mapping.get('fy26_budget') and ytd is not None:
        remaining = mapping['fy26_budget'] - ytd
        lines.append(f"- **Remaining budget:** ${remaining:,.2f}")
    if mapping.get('run_rate_monthly'):
        lines.append(f"- **Monthly run rate:** {mapping['run_rate_monthly']}")
    if mapping.get('run_rate_annual'):
        lines.append(f"- **Annualized:** {mapping['run_rate_annual']}")
    lines.append("")

    # Ramp API cross-reference (historical context)
    ramp_total = mapping.get('ramp_all_time_total') or mapping.get('all_time_total')
    year_2025 = mapping.get('year_2025')
    if ramp_total or year_2025 or mapping.get('ramp_latest_bill') or mapping.get('latest_bill_date'):
        lines.append("### Ramp historical (all-time context)")
        if ramp_total:
            lines.append(f"- **All-time total paid:** ${ramp_total:,.2f}")
        if year_2025:
            lines.append(f"- **2025 full year:** ${year_2025:,.2f}")
        if mapping.get('ramp_bill_count'):
            lines.append(f"- **Total bills processed:** {mapping['ramp_bill_count']}")
        first_bill = mapping.get('first_bill_date')
        if first_bill:
            lines.append(f"- **First bill:** {first_bill}")
        latest = mapping.get('ramp_latest_bill') or mapping.get('latest_bill_date')
        if latest:
            lines.append(f"- **Latest bill:** {latest}")
        lines.append("")

    # Preserved rich notes (for the 5 deep mappings)
    if mapping.get('preserved_notes') or mapping.get('notes') or mapping.get('notes_from_sheet'):
        lines.append("### Notes")
        if mapping.get('preserved_notes'):
            lines.append(mapping['preserved_notes'])
        if mapping.get('notes'):
            lines.append(mapping['notes'])
        if mapping.get('notes_from_sheet'):
            lines.append(f"*From master sheet:* {mapping['notes_from_sheet']}")
        lines.append("")

    return "\n".join(lines)


def upsert_section(md: str, new_section: str) -> str:
    if SECTION_MARKER in md:
        start = md.index(SECTION_MARKER)
        rest = md[start + len(SECTION_MARKER):]
        next_h2 = re.search(r"\n## ", rest)
        end = start + len(SECTION_MARKER) + (next_h2.start() if next_h2 else len(rest))
        return md[:start] + new_section + md[end:]
    # Insert before Coaching Goals or Meeting Log
    for anchor in ("## Coaching Goals", "## Recurring Meetings", "## Meeting Log"):
        if anchor in md:
            idx = md.index(anchor)
            return md[:idx] + new_section + "\n" + md[idx:]
    return md.rstrip() + "\n\n" + new_section + "\n"


def find_profile_for_email(email: str) -> Path | None:
    """Scan profiles for matching frontmatter email."""
    email_lower = email.strip().lower()
    for p in sorted(PEOPLE_DIR.glob("*.md")):
        md = p.read_text(encoding="utf-8")
        m = re.search(r"^email:\s*(.+)$", md, re.MULTILINE)
        if m and m.group(1).strip().strip('"').strip("'").lower() == email_lower:
            return p
        # Also check alt_email
        m2 = re.search(r"^alt_email:\s*(.+)$", md, re.MULTILINE)
        if m2 and m2.group(1).strip().strip('"').strip("'").lower() == email_lower:
            return p
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    mapping_path = CACHE_DIR / "vendor_mapping.json"
    if not mapping_path.exists():
        sys.stderr.write(f"Missing {mapping_path}. Create mapping first.\n")
        return 1
    mappings = json.loads(mapping_path.read_text())
    last_sync = (CACHE_DIR / "last_sync.txt").read_text().strip().splitlines()[0][:10] if (CACHE_DIR / "last_sync.txt").exists() else "unknown"

    updated = 0
    missing = 0
    for m in mappings.get("mappings", []):
        email = m.get("person_email")
        if not email:
            continue
        profile = find_profile_for_email(email)
        if not profile:
            sys.stderr.write(f"  no profile found for {email}\n")
            missing += 1
            continue
        md = profile.read_text(encoding="utf-8")
        section = build_section(m, last_sync)
        new_md = upsert_section(md, section)
        if new_md != md:
            if args.dry_run:
                sys.stderr.write(f"[dry-run] would update: {profile.name}\n")
            else:
                profile.write_text(new_md, encoding="utf-8")
                sys.stderr.write(f"updated: {profile.name}\n")
            updated += 1

    sys.stderr.write(f"\nSummary: {updated} profiles updated, {missing} mappings with no matching profile\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
