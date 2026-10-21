"""Create a dedicated L1 Coordinator test account in Supabase Auth & public.profiles.

Ensures:
1. Supabase Auth user is created with confirmed email.
2. Corresponding profile in public.profiles is created/updated with matching UUID.
3. Role is set to L1_COORDINATOR and is_active is True.
4. Idempotent: safe to run multiple times without creating duplicate profiles.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add backend directory to sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.db import supabase

DEFAULT_L1_EMAIL = "l1_coordinator@cpass.org"
DEFAULT_L1_NAME = "Ananya Sharma (L1 Coordinator)"
DEFAULT_L1_PASS = "Cpass@Coordinator2026!"


def create_or_update_l1_user(
    email: str = DEFAULT_L1_EMAIL,
    password: str = DEFAULT_L1_PASS,
    full_name: str = DEFAULT_L1_NAME,
) -> dict:
    email = email.strip().lower()
    print(f"Creating/Verifying L1 Coordinator account for: {email}...")

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
        print(f"Error checking existing auth users: {e}")

    # 2. Create in Supabase Auth if missing
    if not auth_user:
        try:
            auth_res = supabase.auth.admin.create_user({
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {"full_name": full_name},
            })
            auth_user = auth_res.user
            print(f"[OK] Created Supabase Auth user with UUID: {auth_user.id}")
        except Exception as e:
            print(f"[ERROR] Failed to create auth user: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"[OK] Found existing Supabase Auth user with UUID: {auth_user.id}")
        # Update password to ensure it matches
        try:
            supabase.auth.admin.update_user_by_id(auth_user.id, {"password": password})
            print("[OK] Updated user password.")
        except Exception as e:
            print(f"Note on updating password: {e}")

    user_id = auth_user.id

    # 3. Create or update profile in public.profiles
    profile_payload = {
        "id": user_id,
        "email": email,
        "full_name": full_name,
        "role": "L1_COORDINATOR",
        "is_active": True,
    }

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
        print(f"[ERROR] Failed to upsert profile: {e}", file=sys.stderr)
        sys.exit(1)

    print("\n" + "=" * 55)
    print("L1 COORDINATOR ACCOUNT READY")
    print("=" * 55)
    print(f"Email:     {email}")
    print(f"Role:      L1_COORDINATOR")
    print(f"Status:    Active")
    print(f"Auth UUID: {user_id}")
    print("=" * 55)

    return profile_payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create dedicated L1 Coordinator account")
    parser.add_argument("--email", default=DEFAULT_L1_EMAIL, help="User email")
    parser.add_argument("--password", default=DEFAULT_L1_PASS, help="User password")
    parser.add_argument("--name", default=DEFAULT_L1_NAME, help="Full name")
    args = parser.parse_args()

    create_or_update_l1_user(email=args.email, password=args.password, full_name=args.name)
