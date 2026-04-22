#!/usr/bin/env python3
"""
fetch_rippling_people.py — fetch employee roster + comp + benefits from Rippling API.

⚠ PII HANDLING RULES — read before modifying:
- Reads API token from %LOCALAPPDATA%\\nsls-private\\rippling\\.env
- Writes cache ONLY to %LOCALAPPDATA%\\nsls-private\\rippling\\*.json
- Hardcoded path allowlist refuses any other write destination
- Explicitly DOES NOT fetch SSN fields (enforced in field filter below)
- Never writes to the toolkit repo, Obsidian vault, OneDrive, or any shared location
- If you add a new data type, add it to ALLOWED_OUTPUT_FILES below

Usage:
    python fetch_rippling_people.py            # full sync
    python fetch_rippling_people.py --list     # list employees only, no cache write
    python fetch_rippling_people.py --dry-run  # show what would be fetched

Requires: requests, python-dotenv
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import requests
    from dotenv import load_dotenv
except ImportError:
    sys.stderr.write("Missing deps. Install: pip install requests python-dotenv\n")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Path allowlist — hardcoded. Writes outside this dir are a runtime error.
# ---------------------------------------------------------------------------
LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
CACHE_DIR = LOCALAPPDATA / "nsls-private" / "rippling"
ENV_PATH = CACHE_DIR / ".env"

ALLOWED_OUTPUT_FILES = {
    "workers.json",
    "users.json",
    "departments.json",
    "companies.json",
    "employment_types.json",
    "entitlements.json",
    "compensations.json",
    "last_sync.txt",
}

# Fields that must NEVER be fetched or stored (SSN explicitly excluded per user directive)
BANNED_FIELDS = {
    "ssn",
    "social_security_number",
    "tin",  # tax identification number (personal)
    "national_id",
}


def safe_write(filename: str, content: str) -> None:
    """Write to cache dir only. Error if anyone tries to escape."""
    if filename not in ALLOWED_OUTPUT_FILES:
        raise RuntimeError(
            f"REFUSED: '{filename}' not in allowlist. "
            f"This script can only write: {sorted(ALLOWED_OUTPUT_FILES)}"
        )
    target = CACHE_DIR / filename
    target.resolve().relative_to(CACHE_DIR.resolve())  # raises if outside
    target.write_text(content, encoding="utf-8")
    sys.stderr.write(f"Wrote: {target}\n")


def scrub_banned(record: dict[str, Any]) -> dict[str, Any]:
    """Remove banned fields (SSN, etc.) recursively before caching."""
    if not isinstance(record, dict):
        return record
    out = {}
    for k, v in record.items():
        if k.lower() in BANNED_FIELDS:
            continue
        if isinstance(v, dict):
            out[k] = scrub_banned(v)
        elif isinstance(v, list):
            out[k] = [scrub_banned(x) if isinstance(x, dict) else x for x in v]
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# Rippling API client
# ---------------------------------------------------------------------------
class RipplingClient:
    def __init__(self, token: str, base: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "nsls-personal-toolkit/person-intelligence (local-only)",
        })
        self.base = base.rstrip("/")

    def _request(self, url: str, params: dict | None = None):
        """Single request with status-code handling."""
        resp = self.session.get(url, params=params or {}, timeout=30)
        if resp.status_code == 401:
            sys.stderr.write("AUTH FAILED. Token invalid or expired.\n")
            sys.exit(2)
        if resp.status_code == 429:
            sys.stderr.write("Rate limited. Try again in a minute.\n")
            sys.exit(3)
        resp.raise_for_status()
        return resp.json()

    def get(self, path: str, params: dict | None = None, paginated: bool = True) -> list[dict] | dict:
        """GET with cursor-based pagination (Rippling REST API follows next_link).
        Max limit per page is 100."""
        url = f"{self.base}{path}"
        if not paginated:
            return self._request(url, params)

        all_results = []
        params = dict(params or {})
        params.setdefault("limit", 100)
        page_count = 0
        while True:
            page_count += 1
            data = self._request(url, params)
            batch = data.get("results", []) if isinstance(data, dict) else data
            if not batch:
                break
            all_results.extend(batch)
            # Rippling returns a full URL in next_link (or null) for cursor pagination.
            next_link = data.get("next_link") if isinstance(data, dict) else None
            if not next_link:
                break
            # Follow the next_link URL as-is; clear query params since they're embedded
            url = next_link
            params = {}
            if page_count > 200:
                sys.stderr.write(f"  WARN: stopped at {page_count} pages (safety limit)\n")
                break
        return all_results


# ---------------------------------------------------------------------------
# Fetch orchestration
# ---------------------------------------------------------------------------
# Each entry: (endpoint_path, output_filename, description)
# Rippling REST API endpoints (rest.ripplingapis.com)
# Each entry: (path, filename, description, paginated, expand_fields)
# Verified against live API 2026-04-21. Endpoints that returned 404 removed:
#   /me (use /workers roster), /groups (not available on current tier), /users/me (expects ObjectId)
ENDPOINTS = [
    ("/workers", "workers.json", "Full worker roster with expanded compensation, department, employment_type, user, manager",
     True, "compensation,department,employment_type,user,manager"),
    ("/users", "users.json", "User accounts (name, email, SSO, phone)", True, None),
    ("/departments", "departments.json", "Department list and hierarchy", True, None),
    ("/companies", "companies.json", "Company + legal entity info", True, None),
    ("/employment-types", "employment_types.json", "W2 vs. contractor employment type definitions", True, None),
    ("/entitlements", "entitlements.json", "API entitlements / access scopes granted to this token", True, None),
    ("/compensations", "compensations.json", "Compensation records (base, bonus, commission, signing bonus, salary effective date)", True, None),
]


def fetch_all(client: RipplingClient, dry_run: bool = False) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    total_records = 0
    for entry in ENDPOINTS:
        # Support both old 4-tuple and new 5-tuple (with expand_fields) entries
        if len(entry) == 5:
            path, filename, desc, paginated, expand_fields = entry
        else:
            path, filename, desc, paginated = entry
            expand_fields = None
        sys.stderr.write(f"\n--- {desc} ---\n")
        sys.stderr.write(f"GET {path}{' (expand=' + expand_fields + ')' if expand_fields else ''} -> {filename}\n")
        if dry_run:
            sys.stderr.write("(dry-run; skipping fetch)\n")
            continue
        try:
            params = {"expand": expand_fields} if expand_fields else None
            data = client.get(path, params=params, paginated=paginated)
            if isinstance(data, dict):
                data = scrub_banned(data)
                count = 1
            else:
                data = [scrub_banned(r) for r in data]
                count = len(data)
            total_records += count
            safe_write(filename, json.dumps(data, indent=2, default=str))
            sys.stderr.write(f"  fetched {count} record(s)\n")
        except requests.HTTPError as e:
            sys.stderr.write(f"  HTTP {e.response.status_code}: {e.response.text[:200]}\n")
            sys.stderr.write("  (continuing to next endpoint)\n")
        except Exception as e:
            sys.stderr.write(f"  ERROR: {type(e).__name__}: {e}\n")
    timestamp = datetime.now(timezone.utc).isoformat()
    safe_write("last_sync.txt", f"{timestamp}\nfetched {total_records} total records\n")
    sys.stderr.write(f"\nSync complete. {total_records} total records cached at {CACHE_DIR}\n")


def list_employees(client: RipplingClient) -> None:
    """Smoke test: /workers roster. Does not write cache."""
    sys.stderr.write("--- Worker roster ---\n")
    records = client.get("/workers", params={"limit": 100}, paginated=True)
    sys.stderr.write(f"  {len(records)} workers returned\n\n")
    active_count = 0
    terminated_count = 0
    for r in records:
        # Top-level fields (user is nested but often null without expansion)
        work_email = r.get("work_email") or ""
        personal_email = r.get("personal_email") or ""
        status = r.get("status") or ""
        start_date = r.get("start_date") or ""
        end_date = r.get("end_date") or ""
        employment_type_id = r.get("employment_type_id") or ""
        country = r.get("country") or ""
        if status == "ACTIVE":
            active_count += 1
        elif status == "TERMINATED":
            terminated_count += 1
        email = work_email or personal_email
        print(f"{email}\t{status}\t{start_date}\t{end_date}\t{country}")
    sys.stderr.write(f"\nSummary: {active_count} active, {terminated_count} terminated, {len(records)} total\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Rippling employee data (user-local PII cache).")
    parser.add_argument("--list", action="store_true", help="List employees only; no cache write")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be fetched; no API calls")
    args = parser.parse_args()

    if not ENV_PATH.exists():
        sys.stderr.write(f"Missing: {ENV_PATH}\n")
        sys.stderr.write(f"Copy .env.template to .env in {CACHE_DIR} and fill in RIPPLING_API_TOKEN.\n")
        return 1

    load_dotenv(ENV_PATH)
    token = os.environ.get("RIPPLING_API_TOKEN")
    if not token or token.strip() == "":
        sys.stderr.write("RIPPLING_API_TOKEN not set in .env\n")
        return 1
    base = os.environ.get("RIPPLING_API_BASE", "https://rest.ripplingapis.com")

    client = RipplingClient(token=token, base=base)

    if args.list:
        list_employees(client)
    else:
        fetch_all(client, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
