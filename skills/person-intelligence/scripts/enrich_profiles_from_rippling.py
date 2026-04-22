#!/usr/bin/env python3
"""
enrich_profiles_from_rippling.py — tie Rippling HR data into Obsidian person profiles.

⚠ PII HANDLING:
- Reads Rippling cache from %LOCALAPPDATA%\\nsls-private\\rippling\\ (user-local only)
- Writes enrichment into $OBSIDIAN_VAULT_PATH/30-people/*.md (user-local vault)
- Never writes to toolkit repo, OneDrive, or any shared path
- Path allowlist: only 30-people/*.md files in the configured vault
- Idempotent: inserts or updates a `## HR Data (Rippling)` section
- Preserves all other profile content

Usage:
    python enrich_profiles_from_rippling.py              # enrich all matching profiles
    python enrich_profiles_from_rippling.py --dry-run    # preview changes only
    python enrich_profiles_from_rippling.py --email <x>  # single-person enrichment
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
CACHE_DIR = LOCALAPPDATA / "nsls-private" / "rippling"

# Load vault path from toolkit .env
def load_vault_path() -> Path:
    env_path = Path.home() / ".claude" / "local-plugins" / "nsls-personal-toolkit" / ".env"
    if not env_path.exists():
        sys.stderr.write(f"Missing toolkit .env at {env_path}\n")
        sys.exit(1)
    for line in env_path.read_text().splitlines():
        if line.startswith("OBSIDIAN_VAULT_PATH="):
            return Path(line.split("=", 1)[1].strip())
    sys.stderr.write("OBSIDIAN_VAULT_PATH not found in toolkit .env\n")
    sys.exit(1)

VAULT_PATH = load_vault_path()
PEOPLE_DIR = VAULT_PATH / "30-people"
SECTION_MARKER_START = "## HR Data (Rippling)"
SECTION_MARKER_END_SIGNALS = ("\n## ", "\n---\n")

def money(v):
    """Format a Rippling {currency_type, value} object as $X,XXX."""
    if not v or not isinstance(v, dict):
        return "—"
    amt = v.get("value", 0) or 0
    if amt == 0:
        return "—"
    return f"${amt:,.0f}"

def percent(v):
    if v is None or v == 0:
        return "—"
    return f"{v:.1f}%"

def days_since(iso_date: str) -> int | None:
    if not iso_date:
        return None
    try:
        d = datetime.fromisoformat(iso_date.replace("Z", "+00:00")).date() if "T" in iso_date else date.fromisoformat(iso_date)
        return (date.today() - d).days
    except Exception:
        return None

def build_hr_section(worker: dict, sync_date: str) -> str:
    """Produce the `## HR Data (Rippling)` section for a worker record."""
    user = worker.get("user") or {}
    comp = worker.get("compensation") or {}
    dept = worker.get("department") or {}
    et = worker.get("employment_type") or {}
    mgr = worker.get("manager") or {}
    loc = worker.get("location") or {}

    start = worker.get("start_date") or ""
    end = worker.get("end_date") or ""
    status = worker.get("status") or "UNKNOWN"
    tenure_days = days_since(start) if start else None
    tenure_str = ""
    if tenure_days:
        years = tenure_days / 365.25
        if years >= 1:
            tenure_str = f"{years:.1f} yrs"
        else:
            tenure_str = f"{tenure_days // 30} months"

    # Salary effective date — flag recent changes
    salary_eff = comp.get("salary_effective_date") or ""
    salary_eff_days = days_since(salary_eff) if salary_eff else None
    recent_change_flag = ""
    if salary_eff_days is not None:
        if salary_eff_days <= 365:
            recent_change_flag = f" ← change in past {salary_eff_days // 30} months"
        elif salary_eff_days <= 730:
            recent_change_flag = f" (unchanged {salary_eff_days // 30} months)"

    annual_base = comp.get("annual_compensation") or comp.get("annual_salary_equivalent") or {}
    target_bonus = comp.get("target_annual_bonus") or {}
    bonus_pct = comp.get("target_annual_bonus_percent") or 0
    commission = comp.get("on_target_commission") or {}
    signing = comp.get("signing_bonus") or {}
    bonus_schedule = comp.get("bonus_schedule") or "—"

    # Work email / personal email
    work_email = worker.get("work_email") or ""
    personal_email = worker.get("personal_email") or ""

    # User expansion: name, phone, address
    user_name = ""
    user_phones = []
    user_addresses = []
    if user:
        name_obj = user.get("name") or {}
        user_name = name_obj.get("display_name") or name_obj.get("formatted") or f"{name_obj.get('given_name','')} {name_obj.get('family_name','')}".strip()
        user_phones = [p.get("display") or p.get("value") for p in (user.get("phone_numbers") or []) if p]
        user_addresses = [a.get("formatted") for a in (user.get("addresses") or []) if a and a.get("type") == "HOME"]

    # Manager
    mgr_name = ""
    mgr_email = ""
    if mgr:
        mn = mgr.get("name") or {}
        mgr_name = mn.get("display_name") or mn.get("formatted") or ""
        mgr_email = (mgr.get("emails") or [{}])[0].get("value", "")

    lines = [
        SECTION_MARKER_START,
        f"*Synced from local Rippling cache. Last sync: {sync_date}. User-local PII — never share or upload.*",
        "",
        "### Role",
        f"- **Title:** {worker.get('title') or '—'}",
        f"- **Department:** {dept.get('name') or '—'}",
        f"- **Employment type:** {et.get('label') or et.get('name') or '—'}",
        f"- **Status:** {status}",
        f"- **Manager:** {mgr_name} ({mgr_email})" if mgr_name or mgr_email else "- **Manager:** —",
        "",
        "### Dates",
        f"- **Start date (hire date):** {start or '—'}",
    ]
    if end:
        lines.append(f"- **End date (terminated):** {end}")
    if tenure_str:
        lines.append(f"- **Tenure:** {tenure_str}")
    lines.append(f"- **Current comp effective since:** {salary_eff or '—'}{recent_change_flag}")
    lines.append("")

    # Compute bonus percent from dollars if Rippling's percent field is 0/null
    base_val = annual_base.get("value") or 0
    bonus_val = target_bonus.get("value") or 0
    if (bonus_pct is None or bonus_pct == 0) and base_val > 0 and bonus_val > 0:
        bonus_pct = (bonus_val / base_val) * 100
    bonus_pct_str = f"{bonus_pct:.1f}%" if bonus_pct else "—"

    # Detect invoice-based contractors (Rippling shows $0 comp because comp flows via RAMP/NetSuite, not payroll)
    et_name = (et.get("name") or et.get("label") or "").upper()
    is_contractor = "CONTRACTOR" in et_name or "1099" in et_name
    all_comp_zero = base_val == 0 and bonus_val == 0 and (commission.get("value") or 0) == 0 and ((comp.get("hourly_wage") or {}).get("value") or 0) == 0

    lines.append("### Compensation")
    if is_contractor and all_comp_zero:
        lines.append("- ⚠ **Invoice-based contractor.** Rippling shows $0 because comp flows via vendor invoice (RAMP / NetSuite), not Rippling payroll. Actual comp lives in AP records, not here.")
    else:
        lines.append(f"- **Base salary (annual):** {money(annual_base)}")
        lines.append(f"- **Target annual bonus:** {money(target_bonus)} ({bonus_pct_str} of base)")
        if (commission.get("value") or 0) > 0:
            lines.append(f"- **On-target commission:** {money(commission)}")
        if (signing.get("value") or 0) > 0:
            lines.append(f"- **Signing bonus:** {money(signing)}")
        lines.append(f"- **Bonus schedule:** {bonus_schedule}")

    # Total comp if computable
    total_targeted = (annual_base.get("value") or 0) + (target_bonus.get("value") or 0) + (commission.get("value") or 0)
    if total_targeted > 0:
        lines.append(f"- **Total targeted annual comp:** ${total_targeted:,.0f}")
    lines.append("")

    lines.append("### Location")
    lines.append(f"- **Country:** {worker.get('country') or '—'}")
    if loc:
        lines.append(f"- **Location type:** {loc.get('type') or '—'}")
    lines.append("")

    lines.append("### Contact")
    if user_name:
        lines.append(f"- **Display name:** {user_name}")
    if work_email:
        lines.append(f"- **Work email:** {work_email}")
    if personal_email and personal_email != work_email:
        lines.append(f"- **Personal email:** {personal_email}")
    for p in user_phones:
        lines.append(f"- **Phone:** {p}")
    for a in user_addresses:
        lines.append(f"- **Home address:** {a}")
    lines.append("")

    lines.append("### Rippling IDs (for reference)")
    lines.append(f"- worker_id: `{worker.get('id','')}`")
    lines.append(f"- user_id: `{worker.get('user_id','')}`")
    lines.append(f"- compensation_id: `{worker.get('compensation_id','')}`")
    lines.append(f"- department_id: `{worker.get('department_id','')}`")
    lines.append("")

    return "\n".join(lines)


def upsert_section(md: str, new_section: str) -> str:
    """Insert or replace the ## HR Data (Rippling) section.
    Position: right before ## Coaching Goals, or before ## Meeting Log, or at end."""
    if SECTION_MARKER_START in md:
        # Replace existing section
        start = md.index(SECTION_MARKER_START)
        # Find end of section: next ## heading or end of file
        rest = md[start + len(SECTION_MARKER_START):]
        next_h2 = re.search(r"\n## ", rest)
        end = start + len(SECTION_MARKER_START) + (next_h2.start() if next_h2 else len(rest))
        return md[:start] + new_section + md[end:]

    # Insert before ## Coaching Goals, or ## Meeting Log, or at end
    for anchor in ("## Coaching Goals", "## Recurring Meetings", "## Meeting Log"):
        if anchor in md:
            idx = md.index(anchor)
            return md[:idx] + new_section + "\n" + md[idx:]
    # No anchor — append at end
    return md.rstrip() + "\n\n" + new_section + "\n"


STATUS_PRIORITY = {"ACTIVE": 0, "HIRED": 1, "ON_LEAVE": 2, "TERMINATED": 3, None: 4}

def load_cache():
    workers_path = CACHE_DIR / "workers.json"
    last_sync_path = CACHE_DIR / "last_sync.txt"
    if not workers_path.exists():
        sys.stderr.write(f"Missing {workers_path}. Run fetch_rippling_people.py first.\n")
        sys.exit(1)
    workers = json.loads(workers_path.read_text())
    sync_date = "unknown"
    if last_sync_path.exists():
        first_line = last_sync_path.read_text().strip().splitlines()[0]
        sync_date = first_line[:10]  # just the date part

    # Index by work_email and personal_email
    # When multiple workers share an email, prefer ACTIVE > HIRED > ON_LEAVE > TERMINATED
    # (e.g., a person who was terminated and rehired will have 2 records)
    by_email: dict[str, dict] = {}
    for w in workers:
        for key in ("work_email", "personal_email"):
            email = (w.get(key) or "").strip().lower()
            if not email:
                continue
            incumbent = by_email.get(email)
            if incumbent is None:
                by_email[email] = w
                continue
            # Replace if this worker has a better status
            if STATUS_PRIORITY.get(w.get("status")) < STATUS_PRIORITY.get(incumbent.get("status")):
                by_email[email] = w
            elif STATUS_PRIORITY.get(w.get("status")) == STATUS_PRIORITY.get(incumbent.get("status")):
                # Same status — prefer the one with later start_date (more recent tenure)
                if (w.get("start_date") or "") > (incumbent.get("start_date") or ""):
                    by_email[email] = w
    return by_email, sync_date


def extract_email_from_profile(md: str) -> str | None:
    """Pull email from frontmatter."""
    m = re.search(r"^email:\s*(.+)$", md, re.MULTILINE)
    if m:
        return m.group(1).strip().strip('"').strip("'")
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--email", help="Enrich only the profile matching this email")
    args = parser.parse_args()

    # Safety: confirm vault path
    if not PEOPLE_DIR.exists():
        sys.stderr.write(f"Missing {PEOPLE_DIR}\n")
        return 1
    # Safety: PEOPLE_DIR must not be inside the toolkit repos
    for forbidden in ("local-plugins/nsls-personal-toolkit", "local-plugins/nsls-builder-toolkit", "OneDrive"):
        if forbidden.lower() in str(PEOPLE_DIR).lower():
            sys.stderr.write(f"REFUSED: vault path '{PEOPLE_DIR}' contains forbidden substring '{forbidden}'\n")
            return 2

    by_email, sync_date = load_cache()
    sys.stderr.write(f"Loaded {len(by_email)} email->worker mappings from Rippling cache (last sync {sync_date})\n")

    matched = 0
    unmatched = 0
    updated = 0
    skipped_non_employee = 0

    profile_files = sorted(PEOPLE_DIR.glob("*.md"))
    for pf in profile_files:
        md = pf.read_text(encoding="utf-8")
        email = extract_email_from_profile(md)
        if not email:
            continue
        if args.email and email.lower() != args.email.lower():
            continue

        worker = by_email.get(email.lower())
        if not worker:
            # Try alt email formats
            # Some nsls.org emails have variants
            unmatched += 1
            continue

        matched += 1
        new_section = build_hr_section(worker, sync_date)
        new_md = upsert_section(md, new_section)
        if new_md == md:
            continue
        if args.dry_run:
            sys.stderr.write(f"[dry-run] would update: {pf.name}\n")
            updated += 1
        else:
            pf.write_text(new_md, encoding="utf-8")
            sys.stderr.write(f"updated: {pf.name}\n")
            updated += 1

    sys.stderr.write(f"\nSummary:\n")
    sys.stderr.write(f"  Profile files scanned: {len(profile_files)}\n")
    sys.stderr.write(f"  Matched to Rippling:   {matched}\n")
    sys.stderr.write(f"  Updated:               {updated}\n")
    sys.stderr.write(f"  Not in Rippling:       {unmatched}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
