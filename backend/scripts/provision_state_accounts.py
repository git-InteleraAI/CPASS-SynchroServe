"""CPASS State-Wise Account Provisioning and Management Script.

Provisions, verifies, and manages the 24 canonical state accounts:
- 12 L1 Placement Executives (PE): <state-code>pe@synchroserve.com
- 12 L2 Centre Heads (CH):         <state-code>ch@synchroserve.com

Roles:
- L1: L1_COORDINATOR
- L2: L2_MANAGER

Features:
- Idempotent: safe to run multiple times without creating duplicates.
- Automatic pre-migration backup of existing accounts & profiles.
- Validates Supabase Auth identities and public.profiles records.
- Secure password rotation operational path.
- State-isolation verification.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys
from typing import Any

# Add backend directory to sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.auth import ALL_12_STATES, resolve_state
from app.db import get_auth_client, supabase

logger = logging.getLogger("cpass.provision")

# -----------------------------------------------------------------------------
# Canonical 12 States & Account Matrix
# -----------------------------------------------------------------------------
STATE_ACCOUNTS_CONFIG = [
    {
        "code": "ap",
        "state": "ANDHRA PRADESH",
        "title": "Andhra Pradesh",
    },
    {
        "code": "gj",
        "state": "GUJARAT",
        "title": "Gujarat",
    },
    {
        "code": "kl",
        "state": "KERALA",
        "title": "Kerala",
    },
    {
        "code": "mz",
        "state": "MIZORAM",
        "title": "Mizoram",
    },
    {
        "code": "od",
        "state": "ODISHA",
        "title": "Odisha",
    },
    {
        "code": "py",
        "state": "PUDUCHERRY",
        "title": "Puducherry",
    },
    {
        "code": "pb",
        "state": "PUNJAB",
        "title": "Punjab",
    },
    {
        "code": "rj",
        "state": "RAJASTHAN",
        "title": "Rajasthan",
    },
    {
        "code": "tn",
        "state": "TAMIL NADU",
        "title": "Tamil Nadu",
    },
    {
        "code": "ts",
        "state": "TELANGANA",
        "title": "Telangana",
    },
    {
        "code": "up",
        "state": "UTTAR PRADESH",
        "title": "Uttar Pradesh",
    },
    {
        "code": "wb",
        "state": "WEST BENGAL",
        "title": "West Bengal",
    },
]


def build_account_definitions() -> list[dict[str, Any]]:
    """Build the exact specification for all 24 state accounts."""
    accounts = []
    for item in STATE_ACCOUNTS_CONFIG:
        code = item["code"]
        state_canon = item["state"]
        state_title = item["title"]

        # L1 Placement Executive
        accounts.append({
            "code": code,
            "role_level": "L1",
            "role": "L1_COORDINATOR",
            "state": state_canon,
            "email": f"{code}pe@synchroserve.com",
            "default_password": f"{code}pe@cpass",
            "full_name": f"{state_title} - Placement Executive",
        })

        # L2 Centre Head
        accounts.append({
            "code": code,
            "role_level": "L2",
            "role": "L2_MANAGER",
            "state": state_canon,
            "email": f"{code}ch@synchroserve.com",
            "default_password": f"{code}ch@cpass",
            "full_name": f"{state_title} - Centre Head",
        })
    return accounts


# -----------------------------------------------------------------------------
# Backup Utility
# -----------------------------------------------------------------------------
def export_accounts_backup(output_dir: Path | None = None) -> Path:
    """Export current Supabase Auth users and public.profiles into a timestamped JSON backup."""
    dest_dir = output_dir or (BACKEND_DIR / "scripts" / "backups")
    dest_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_file = dest_dir / f"accounts_backup_{timestamp}.json"

    # 1. Fetch public.profiles
    profiles_data = supabase.table("profiles").select("*").execute().data or []

    # 2. Fetch Supabase Auth users
    auth_users_data = []
    try:
        users_resp = supabase.auth.admin.list_users()
        user_list = users_resp.users if hasattr(users_resp, "users") else users_resp
        for u in user_list:
            auth_users_data.append({
                "id": str(u.id),
                "email": u.email,
                "created_at": str(getattr(u, "created_at", None)),
                "last_sign_in_at": str(getattr(u, "last_sign_in_at", None)),
                "user_metadata": getattr(u, "user_metadata", {}) or {},
            })
    except Exception as exc:
        print(f"[WARN] Could not export auth.users via admin API: {exc}")

    backup_payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "total_profiles": len(profiles_data),
        "total_auth_users": len(auth_users_data),
        "profiles": profiles_data,
        "auth_users": auth_users_data,
    }

    with open(backup_file, "w", encoding="utf-8") as f:
        json.dump(backup_payload, f, indent=2)

    print(f"[BACKUP] Successfully exported {len(profiles_data)} profiles & {len(auth_users_data)} auth users to: {backup_file}")
    return backup_file


# -----------------------------------------------------------------------------
# Provisioning Engine
# -----------------------------------------------------------------------------
def provision_state_accounts(
    dry_run: bool = False,
    rotate_passwords: bool = False,
    filter_state: str | None = None,
) -> dict[str, Any]:
    """Idempotently provision all 24 state accounts in Supabase Auth & public.profiles."""
    all_defs = build_account_definitions()
    if filter_state:
        canon_filter = resolve_state(filter_state)
        all_defs = [a for a in all_defs if a["state"] == canon_filter or a["code"] == filter_state.lower()]
        if not all_defs:
            print(f"[ERROR] No accounts match filter state: {filter_state}")
            return {"created": 0, "updated": 0, "errors": 1}

    print("=" * 78)
    print(f"CPASS STATE-WISE ACCOUNT PROVISIONING ({len(all_defs)} Accounts Target)")
    print("=" * 78)

    # Pre-fetch existing Supabase Auth users
    print("[1/3] Reading existing Supabase Auth users...")
    auth_map: dict[str, Any] = {}
    try:
        users_resp = supabase.auth.admin.list_users()
        user_list = users_resp.users if hasattr(users_resp, "users") else users_resp
        for u in user_list:
            if u.email:
                auth_map[u.email.lower()] = u
    except Exception as exc:
        print(f"[ERROR] Failed to list auth users via service role client: {exc}")
        return {"created": 0, "updated": 0, "errors": 1}

    # Pre-fetch existing public.profiles
    print("[2/3] Reading existing public.profiles table...")
    prof_map: dict[str, Any] = {}
    try:
        profiles_res = supabase.table("profiles").select("*").execute()
        for p in (profiles_res.data or []):
            if p.get("email"):
                prof_map[p["email"].lower()] = p
            if p.get("id"):
                prof_map[str(p["id"])] = p
    except Exception as exc:
        print(f"[ERROR] Failed to fetch public.profiles: {exc}")
        return {"created": 0, "updated": 0, "errors": 1}

    # Process accounts
    print(f"[3/3] Provisioning {len(all_defs)} state-specific accounts...")
    created_count = 0
    updated_count = 0
    unchanged_count = 0
    error_count = 0

    results = []

    for acc in all_defs:
        email = acc["email"].lower()
        role = acc["role"]
        state = acc["state"]
        full_name = acc["full_name"]
        password = acc["default_password"]

        auth_user = auth_map.get(email)
        user_id = None
        status_msg = ""

        user_metadata = {
            "full_name": full_name,
            "role": role,
            "assigned_state": state,
        }

        if dry_run:
            print(f" [DRY-RUN] Would check/provision {email} ({role} | {state})")
            continue

        try:
            # 1. Supabase Auth user check/create/update
            if not auth_user:
                auth_res = supabase.auth.admin.create_user({
                    "email": email,
                    "password": password,
                    "email_confirm": True,
                    "user_metadata": user_metadata,
                })
                auth_user = auth_res.user
                user_id = str(auth_user.id)
                status_msg += "Auth:CREATED "
                created_count += 1
            else:
                user_id = str(auth_user.id)
                # If rotation requested or metadata out of date, update
                update_kwargs: dict[str, Any] = {"user_metadata": user_metadata}
                if rotate_passwords:
                    update_kwargs["password"] = password
                    status_msg += "Auth:PASS_ROTATED "
                else:
                    status_msg += "Auth:EXISTS "

                supabase.auth.admin.update_user_by_id(user_id, update_kwargs)

            # 2. public.profiles check/insert/update
            existing_prof = prof_map.get(email) or prof_map.get(user_id)
            profile_payload = {
                "id": user_id,
                "email": email,
                "full_name": full_name,
                "role": role,
                "assigned_state": state,
                "is_active": True,
            }

            if not existing_prof:
                supabase.table("profiles").insert(profile_payload).execute()
                status_msg += "| Profile:INSERTED"
                if not status_msg.startswith("Auth:CREATED"):
                    updated_count += 1
            else:
                # Update profile to guarantee correct role, assigned_state, and full_name
                supabase.table("profiles").update(profile_payload).eq("id", user_id).execute()
                status_msg += "| Profile:VERIFIED/UPDATED"
                unchanged_count += 1

            results.append({
                "email": email,
                "role": role,
                "state": state,
                "id": user_id,
                "status": status_msg,
            })
            print(f"  [OK] {email:<28} | {role:<15} | {state:<16} | {status_msg}")

        except Exception as exc:
            print(f"  [FAIL] {email:<28} | {role:<15} | ERROR: {exc}")
            error_count += 1

    print("=" * 78)
    print("PROVISIONING SUMMARY:")
    print(f"  Total Accounts Target:   {len(all_defs)}")
    print(f"  New Identities Created:  {created_count}")
    print(f"  Identities Verified:     {unchanged_count + updated_count}")
    print(f"  Errors / Failures:       {error_count}")
    print("=" * 78)

    return {
        "total": len(all_defs),
        "created": created_count,
        "verified": unchanged_count + updated_count,
        "errors": error_count,
        "results": results,
    }


# -----------------------------------------------------------------------------
# Validation Utility
# -----------------------------------------------------------------------------
def validate_accounts() -> bool:
    """Verify that all 24 accounts exist in auth and profiles, and can authenticate."""
    print("=" * 78)
    print("VALIDATING 24 STATE ACCOUNTS (SUPABASE AUTH & PROFILES INTEGRITY)")
    print("=" * 78)

    all_defs = build_account_definitions()
    auth_client = get_auth_client()

    all_valid = True

    # Pre-fetch profiles
    profs = supabase.table("profiles").select("*").execute().data or []
    prof_by_email = {p.get("email", "").lower(): p for p in profs}

    for acc in all_defs:
        email = acc["email"].lower()
        expected_role = acc["role"]
        expected_state = acc["state"]
        password = acc["default_password"]

        prof = prof_by_email.get(email)
        if not prof:
            print(f"  [FAIL] {email:<28} | Missing public.profiles row!")
            all_valid = False
            continue

        if prof.get("role") != expected_role:
            print(f"  [FAIL] {email:<28} | Role mismatch: {prof.get('role')} != {expected_role}")
            all_valid = False
            continue

        if resolve_state(prof.get("assigned_state")) != expected_state:
            print(f"  [FAIL] {email:<28} | State mismatch: {prof.get('assigned_state')} != {expected_state}")
            all_valid = False
            continue

        if not prof.get("is_active"):
            print(f"  [FAIL] {email:<28} | Profile is inactive!")
            all_valid = False
            continue

        # Test login
        try:
            sign_in = auth_client.auth.sign_in_with_password({
                "email": email,
                "password": password,
            })
            if not sign_in.user or not sign_in.session:
                print(f"  [FAIL] {email:<28} | Authentication returned empty session")
                all_valid = False
            else:
                print(f"  [OK]   {email:<28} | {expected_role:<15} | {expected_state:<15} | Login OK")
        except Exception as exc:
            print(f"  [FAIL] {email:<28} | Login authentication failed: {exc}")
            all_valid = False

    print("=" * 78)
    if all_valid:
        print("ALL 24 STATE ACCOUNTS VERIFIED SUCCESSFULLY!")
    else:
        print("[WARNING] One or more accounts failed verification.")
    print("=" * 78)
    return all_valid


# -----------------------------------------------------------------------------
# Password Rotation Utility
# -----------------------------------------------------------------------------
def rotate_account_password(email: str, new_password: str) -> bool:
    """Secure operational function to rotate an individual account's password."""
    email = email.strip().lower()
    if len(new_password) < 8:
        print("[ERROR] New password must be at least 8 characters.")
        return False

    users_resp = supabase.auth.admin.list_users()
    user_list = users_resp.users if hasattr(users_resp, "users") else users_resp
    target_user = next((u for u in user_list if u.email and u.email.lower() == email), None)

    if not target_user:
        print(f"[ERROR] User with email {email} not found in Supabase Auth.")
        return False

    try:
        supabase.auth.admin.update_user_by_id(target_user.id, {"password": new_password})
        print(f"[SUCCESS] Password rotated successfully for user {email} ({target_user.id}).")
        return True
    except Exception as exc:
        print(f"[ERROR] Failed to rotate password: {exc}")
        return False


# -----------------------------------------------------------------------------
# Inventory & Legacy Reporting
# -----------------------------------------------------------------------------
def print_accounts_inventory():
    """Print complete inventory of all 24 state accounts and legacy accounts."""
    defs = build_account_definitions()
    print("=" * 86)
    print("CPASS 24 STATE-WISE ACCOUNTS MATRIX")
    print("=" * 86)
    print(f"{'#':<3} {'Role':<6} {'State':<16} {'Email':<26} {'Display Name':<30}")
    print("-" * 86)
    for idx, acc in enumerate(defs, start=1):
        print(f"{idx:<3} {acc['role_level']:<6} {acc['state']:<16} {acc['email']:<26} {acc['full_name']:<30}")
    print("=" * 86)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CPASS State-Wise Account Provisioning and Management")
    parser.add_argument("--provision", action="store_true", help="Provision all 24 state accounts")
    parser.add_argument("--backup", action="store_true", help="Export pre-migration backup of existing accounts")
    parser.add_argument("--validate", action="store_true", help="Validate authentication and profile mapping for all 24 accounts")
    parser.add_argument("--list", action="store_true", help="List the 24 canonical state accounts matrix")
    parser.add_argument("--rotate-passwords", action="store_true", help="Force rotate passwords to the canonical standard")
    parser.add_argument("--set-password", nargs=2, metavar=("EMAIL", "PASSWORD"), help="Set new password for a specific account")
    parser.add_argument("--state", default=None, help="Scope operation to a specific state (e.g. 'ap', 'TAMIL NADU')")
    parser.add_argument("--dry-run", action="store_true", help="Simulate actions without writing to database")

    args = parser.parse_args()

    if args.list:
        print_accounts_inventory()
    elif args.backup:
        export_accounts_backup()
    elif args.validate:
        validate_accounts()
    elif args.set_password:
        rotate_account_password(args.set_password[0], args.set_password[1])
    elif args.provision:
        # Run backup first
        export_accounts_backup()
        provision_state_accounts(
            dry_run=args.dry_run,
            rotate_passwords=args.rotate_passwords,
            filter_state=args.state,
        )
    else:
        # Default help
        parser.print_help()
