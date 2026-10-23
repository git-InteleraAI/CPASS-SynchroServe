"""Create or update dedicated state-specific L1 Placement Coordinator accounts in Supabase Auth & public.profiles.

Ensures:
1. Supabase Auth user is created with confirmed email and assigned state metadata.
2. Corresponding profile in public.profiles is created/updated with matching UUID, role, and assigned_state.
3. Role is set to L1_COORDINATOR and is_active is True.
4. Conforms to the meeting specification (e.g. tn.cpass@synchroserve.in for Tamil Nadu).
5. Idempotent: safe to run multiple times.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add backend directory to sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.auth import ALL_12_STATES, resolve_state
from app.db import supabase

DEFAULT_L1_EMAIL = "l1_coordinator@cpass.org"
DEFAULT_L1_NAME = "Ananya Sharma (L1 Coordinator)"
DEFAULT_L1_PASS = "l1@cpass"

STATE_PRESETS: dict[str, dict[str, str]] = {
    "TAMIL NADU": {"prefix": "tn", "name": "Tamil Nadu Placement Coordinator", "password_prefix": "tn"},
    "TELANGANA": {"prefix": "ts", "name": "Telangana Placement Coordinator", "password_prefix": "ts"},
    "ANDHRA PRADESH": {"prefix": "ap", "name": "Andhra Pradesh Placement Coordinator", "password_prefix": "ap"},
    "KERALA": {"prefix": "kl", "name": "Kerala Placement Coordinator", "password_prefix": "kl"},
    "RAJASTHAN": {"prefix": "rj", "name": "Rajasthan Placement Coordinator", "password_prefix": "rj"},
    "ODISHA": {"prefix": "od", "name": "Odisha Placement Coordinator", "password_prefix": "od"},
    "GUJARAT": {"prefix": "gj", "name": "Gujarat Placement Coordinator", "password_prefix": "gj"},
    "PUNJAB": {"prefix": "pb", "name": "Punjab Placement Coordinator", "password_prefix": "pb"},
    "UTTAR PRADESH": {"prefix": "up", "name": "Uttar Pradesh Placement Coordinator", "password_prefix": "up"},
    "MIZORAM": {"prefix": "mz", "name": "Mizoram Placement Coordinator", "password_prefix": "mz"},
    "PUDUCHERRY": {"prefix": "py", "name": "Puducherry Placement Coordinator", "password_prefix": "py"},
    "WEST BENGAL": {"prefix": "wb", "name": "West Bengal Placement Coordinator", "password_prefix": "wb"},
}


def list_state_accounts() -> None:
    print("=" * 65)
    print("12 STATE-SPECIFIC L1 PLACEMENT COORDINATOR CONFIGURATIONS")
    print("=" * 65)
    for state, info in STATE_PRESETS.items():
        prefix = info["prefix"]
        email = f"{prefix}.cpass@synchroserve.in"
        username = f"{prefix}.cpass"
        print(f"State:    {state}")
        print(f"Username: {username}")
        print(f"Email:    {email}")
        print(f"Name:     {info['name']}")
        print("-" * 65)


def create_or_update_l1_user(
    email: str | None = None,
    password: str = DEFAULT_L1_PASS,
    full_name: str | None = None,
    state: str | None = None,
) -> dict:
    canonical_state = resolve_state(state) if state else None
    if canonical_state and canonical_state in STATE_PRESETS:
        password = f"{STATE_PRESETS[canonical_state]['password_prefix']}l1@cpass"
        
    if state and not canonical_state:
        print(f"[ERROR] Unrecognized state: {state}. Valid states are:", file=sys.stderr)
        for s in ALL_12_STATES:
            print(f"  - {s}", file=sys.stderr)
        sys.exit(1)

    if canonical_state and not email:
        info = STATE_PRESETS.get(canonical_state)
        prefix = info["prefix"] if info else canonical_state.lower().replace(" ", "")
        email = f"{prefix}.cpass@synchroserve.in"
        if not full_name:
            full_name = f"{canonical_state.title()} Placement Coordinator"

    email = (email or DEFAULT_L1_EMAIL).strip().lower()
    full_name = full_name or DEFAULT_L1_NAME
    if not canonical_state:
        canonical_state = resolve_state(email)

    print(f"Creating/Verifying L1 Coordinator account for: {email} (State: {canonical_state or 'Unassigned'})...")

    # 1. Check existing Auth users
    auth_user = None
    try:
        users_resp = supabase.auth.admin.list_users()
        user_list = users_resp.users if hasattr(users_resp, "users") else users_resp
        for u in user_list:
            if u.email and u.email.lower() == email:
                auth_user = u
                break
    except Exception as e:
        print(f"Note on listing auth users: {e}")

    # 2. Create in Supabase Auth if missing
    user_metadata = {
        "full_name": full_name,
        "assigned_state": canonical_state,
        "role": "L1_COORDINATOR",
    }
    if not auth_user:
        try:
            auth_res = supabase.auth.admin.create_user({
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": user_metadata,
            })
            auth_user = auth_res.user
            print(f"[OK] Created Supabase Auth user with UUID: {auth_user.id}")
        except Exception as e:
            print(f"[ERROR] Failed to create auth user: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"[OK] Found existing Supabase Auth user with UUID: {auth_user.id}")
        try:
            supabase.auth.admin.update_user_by_id(
                auth_user.id,
                {"password": password, "user_metadata": user_metadata},
            )
            print("[OK] Updated user password and metadata.")
        except Exception as e:
            print(f"Note on updating user: {e}")

    user_id = auth_user.id

    # 3. Create or update profile in public.profiles
    profile_payload: dict[str, Any] = {
        "id": user_id,
        "email": email,
        "full_name": full_name,
        "role": "L1_COORDINATOR",
        "is_active": True,
    }
    if canonical_state:
        profile_payload["assigned_state"] = canonical_state

    try:
        existing_profile = (
            supabase.table("profiles")
            .select("id,role,is_active")
            .eq("id", user_id)
            .limit(1)
            .execute()
            .data
        )
        if existing_profile:
            supabase.table("profiles").update(profile_payload).eq("id", user_id).execute()
            print(f"[OK] Updated profile in public.profiles for UUID: {user_id}")
        else:
            supabase.table("profiles").insert(profile_payload).execute()
            print(f"[OK] Inserted new profile in public.profiles for UUID: {user_id}")
    except Exception as e:
        # Fallback if assigned_state column is not yet migrated in profiles table
        if "assigned_state" in profile_payload and "assigned_state" in str(e):
            del profile_payload["assigned_state"]
            supabase.table("profiles").upsert(profile_payload).execute()
            print("[OK] Upserted profile without assigned_state column (derived via metadata/email).")
        else:
            print(f"[ERROR] Failed to upsert profile: {e}", file=sys.stderr)
            sys.exit(1)

    print("\n" + "=" * 55)
    print("L1 COORDINATOR ACCOUNT READY")
    print("=" * 55)
    print(f"Email:          {email}")
    print(f"Role:           L1_COORDINATOR")
    print(f"Assigned State: {canonical_state or 'Unassigned (Fail-closed)'}")
    print(f"Status:         Active")
    print(f"Auth UUID:      {user_id}")
    print("=" * 55)

    return profile_payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create or manage L1 Coordinator accounts")
    parser.add_argument("--state", help="Canonical state name or abbreviation (e.g. 'TAMIL NADU', 'tn', 'kl')")
    parser.add_argument("--email", default=None, help="User email")
    parser.add_argument("--password", default=DEFAULT_L1_PASS, help="User password")
    parser.add_argument("--name", default=None, help="Full name")
    parser.add_argument("--list", action="store_true", help="List the 12 state-specific account configurations")
    args = parser.parse_args()

    if args.list:
        list_state_accounts()
    else:
        create_or_update_l1_user(
            email=args.email,
            password=args.password,
            full_name=args.name,
            state=args.state,
        )
