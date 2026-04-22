#!/usr/bin/env python3
"""
fetch_ramp.py — fetch vendor invoices, transactions, reimbursements from Ramp Developer API.

⚠ PII HANDLING RULES — read before modifying:
- Reads client_id + client_secret from %LOCALAPPDATA%\\nsls-private\\ramp\\.env
- Writes cache ONLY to %LOCALAPPDATA%\\nsls-private\\ramp\\*.json
- Hardcoded path allowlist refuses any other write destination
- Scrubs bank account / routing numbers before caching (BANNED_FIELDS)
- Token cache uses short-lived access tokens auto-refreshed via OAuth client_credentials

Usage:
    python fetch_ramp.py                # full sync
    python fetch_ramp.py --smoke        # token exchange + quick /users ping (no cache write)
    python fetch_ramp.py --dry-run      # show what would be fetched

Requires: requests, python-dotenv
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
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
CACHE_DIR = LOCALAPPDATA / "nsls-private" / "ramp"
ENV_PATH = CACHE_DIR / ".env"
TOKEN_CACHE = CACHE_DIR / "token_cache.json"

ALLOWED_OUTPUT_FILES = {
    "bills.json",
    "vendors.json",
    "transactions.json",
    "reimbursements.json",
    "users.json",
    "departments.json",
    "locations.json",
    "token_cache.json",
    "last_sync.txt",
}

# Fields that must NEVER be fetched or cached (banking / routing / sensitive payment PII)
BANNED_FIELDS = {
    "ssn",
    "social_security_number",
    "tin",
    "national_id",
    "bank_account_number",
    "account_number_last_four",  # still identifying; strip to be safe
    "routing_number",
    "iban",
    "swift_code",
}


def safe_write(filename: str, content: str) -> None:
    if filename not in ALLOWED_OUTPUT_FILES:
        raise RuntimeError(
            f"REFUSED: '{filename}' not in allowlist. "
            f"This script can only write: {sorted(ALLOWED_OUTPUT_FILES)}"
        )
    target = CACHE_DIR / filename
    target.resolve().relative_to(CACHE_DIR.resolve())
    target.write_text(content, encoding="utf-8")
    sys.stderr.write(f"Wrote: {target}\n")


def scrub_banned(record: Any) -> Any:
    if isinstance(record, dict):
        out = {}
        for k, v in record.items():
            if k.lower() in BANNED_FIELDS:
                continue
            out[k] = scrub_banned(v)
        return out
    if isinstance(record, list):
        return [scrub_banned(x) for x in record]
    return record


# ---------------------------------------------------------------------------
# OAuth 2.0 client_credentials flow with token caching
# ---------------------------------------------------------------------------
class RampClient:
    def __init__(self, client_id: str, client_secret: str, base: str, scopes: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base = base.rstrip("/")
        self.scopes = scopes
        self.session = requests.Session()
        self._access_token: str | None = None
        self._token_expiry: float = 0

    def _load_cached_token(self) -> bool:
        if not TOKEN_CACHE.exists():
            return False
        try:
            cache = json.loads(TOKEN_CACHE.read_text())
            if cache.get("expires_at", 0) > time.time() + 30:  # 30s buffer
                self._access_token = cache["access_token"]
                self._token_expiry = cache["expires_at"]
                sys.stderr.write(
                    f"  Using cached token (expires in {int((self._token_expiry - time.time()) / 60)} min)\n"
                )
                return True
        except Exception:
            return False
        return False

    def _save_cached_token(self, access_token: str, expires_in: int) -> None:
        self._access_token = access_token
        self._token_expiry = time.time() + expires_in
        cache = {"access_token": access_token, "expires_at": self._token_expiry}
        safe_write("token_cache.json", json.dumps(cache))

    def _refresh_token(self) -> None:
        token_url = f"{self.base}/token"
        sys.stderr.write(f"  Exchanging client credentials at {token_url}\n")
        resp = requests.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "scope": " ".join(s.strip() for s in self.scopes.split(",") if s.strip()),
            },
            auth=(self.client_id, self.client_secret),
            timeout=30,
        )
        if resp.status_code == 401:
            sys.stderr.write(f"AUTH FAILED. Check client_id/client_secret.\n")
            sys.stderr.write(f"Response: {resp.text[:500]}\n")
            sys.exit(2)
        if resp.status_code != 200:
            sys.stderr.write(f"Token exchange failed: HTTP {resp.status_code}\n")
            sys.stderr.write(f"Body: {resp.text[:500]}\n")
            sys.exit(3)
        data = resp.json()
        access_token = data.get("access_token")
        expires_in = data.get("expires_in", 3600)
        if not access_token:
            sys.stderr.write(f"No access_token in response: {data}\n")
            sys.exit(4)
        self._save_cached_token(access_token, expires_in)
        sys.stderr.write(f"  Got new access token (valid {expires_in // 60} min)\n")

    def ensure_token(self) -> str:
        if self._access_token and self._token_expiry > time.time() + 30:
            return self._access_token
        if self._load_cached_token():
            return self._access_token
        self._refresh_token()
        return self._access_token

    def get(self, path: str, params: dict | None = None) -> list[dict]:
        """GET with cursor-based pagination (Ramp follows page.next URL)."""
        token = self.ensure_token()
        url = f"{self.base}{path}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "nsls-personal-toolkit/person-intelligence (local-only)",
        }
        all_results = []
        params = dict(params or {})
        params.setdefault("page_size", 100)
        page_count = 0
        while True:
            page_count += 1
            resp = self.session.get(url, headers=headers, params=params, timeout=30)
            if resp.status_code == 401:
                # Token may have expired mid-request; refresh once and retry
                self._refresh_token()
                headers["Authorization"] = f"Bearer {self._access_token}"
                resp = self.session.get(url, headers=headers, params=params, timeout=30)
            if resp.status_code == 429:
                sys.stderr.write("  Rate limited. Backing off 30s.\n")
                time.sleep(30)
                continue
            resp.raise_for_status()
            data = resp.json()
            batch = data.get("data", []) if isinstance(data, dict) else data
            if not batch:
                break
            all_results.extend(batch)
            # Ramp uses page.next cursor — full URL in next field
            page = data.get("page") if isinstance(data, dict) else None
            next_url = page.get("next") if page else None
            if not next_url:
                break
            url = next_url
            params = {}  # next URL has all params embedded
            if page_count > 500:
                sys.stderr.write(f"  WARN: stopped at {page_count} pages (safety limit)\n")
                break
        return all_results


# ---------------------------------------------------------------------------
# Endpoints to sync
# ---------------------------------------------------------------------------
ENDPOINTS = [
    ("/users", "users.json", "Ramp user accounts"),
    ("/vendors", "vendors.json", "Vendor directory — match by name to tie payments to people"),
    ("/bills", "bills.json", "Vendor invoices + payment history (where 1099 contractor comp lives)"),
    ("/transactions", "transactions.json", "Corporate card transactions"),
    ("/reimbursements", "reimbursements.json", "Employee expense reimbursements"),
    ("/departments", "departments.json", "Ramp departments"),
    ("/locations", "locations.json", "Ramp office/work locations"),
]


def fetch_all(client: RampClient, dry_run: bool = False) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    total_records = 0
    for path, filename, desc in ENDPOINTS:
        sys.stderr.write(f"\n--- {desc} ---\n")
        sys.stderr.write(f"GET {path} -> {filename}\n")
        if dry_run:
            sys.stderr.write("(dry-run; skipping fetch)\n")
            continue
        try:
            records = client.get(path)
            records = [scrub_banned(r) for r in records]
            total_records += len(records)
            safe_write(filename, json.dumps(records, indent=2, default=str))
            sys.stderr.write(f"  fetched {len(records)} records\n")
        except requests.HTTPError as e:
            sys.stderr.write(f"  HTTP {e.response.status_code}: {e.response.text[:200]}\n")
            sys.stderr.write("  (continuing to next endpoint)\n")
        except Exception as e:
            sys.stderr.write(f"  ERROR: {type(e).__name__}: {e}\n")
    timestamp = datetime.now(timezone.utc).isoformat()
    safe_write("last_sync.txt", f"{timestamp}\nfetched {total_records} total records\n")
    sys.stderr.write(f"\nSync complete. {total_records} total records cached at {CACHE_DIR}\n")


def smoke_test(client: RampClient) -> None:
    """Verify token exchange + quick /users ping. Writes only token_cache.json."""
    sys.stderr.write("--- Smoke test ---\n")
    client.ensure_token()
    sys.stderr.write("\n--- GET /users (first page only) ---\n")
    token = client.ensure_token()
    resp = requests.get(
        f"{client.base}/users",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        params={"page_size": 5},
        timeout=30,
    )
    if resp.status_code != 200:
        sys.stderr.write(f"  HTTP {resp.status_code}: {resp.text[:400]}\n")
        sys.exit(5)
    data = resp.json()
    users = data.get("data", [])
    sys.stderr.write(f"  SUCCESS: got {len(users)} users on first page\n")
    for u in users:
        name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or "(no name)"
        email = u.get("email") or ""
        role = u.get("role") or ""
        print(f"  {name}\t{email}\t{role}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Ramp data (user-local PII cache).")
    parser.add_argument("--smoke", action="store_true", help="Smoke test: token exchange + /users ping")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be fetched; no API calls")
    args = parser.parse_args()

    if not ENV_PATH.exists():
        sys.stderr.write(f"Missing: {ENV_PATH}\n")
        sys.stderr.write(f"Copy .env.template to .env in {CACHE_DIR} and fill in RAMP_CLIENT_ID + RAMP_CLIENT_SECRET.\n")
        return 1

    load_dotenv(ENV_PATH)
    client_id = os.environ.get("RAMP_CLIENT_ID")
    client_secret = os.environ.get("RAMP_CLIENT_SECRET")
    base = os.environ.get("RAMP_API_BASE", "https://api.ramp.com/developer/v1")
    scopes = os.environ.get("RAMP_SCOPES", "bills:read,vendors:read,transactions:read,reimbursements:read,users:read")

    if not client_id or not client_secret or client_id.strip() == "" or client_secret.strip() == "":
        sys.stderr.write("RAMP_CLIENT_ID and RAMP_CLIENT_SECRET must be set in .env\n")
        return 1

    client = RampClient(client_id=client_id, client_secret=client_secret, base=base, scopes=scopes)

    if args.smoke:
        smoke_test(client)
    else:
        fetch_all(client, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
