"""Create a dedicated L2 Center Manager test account in Supabase Auth & public.profiles.

Ensures:
1. Supabase Auth user is created with confirmed email.
2. Corresponding profile in public.profiles is created/updated with matching UUID.
3. Role is set to L2_MANAGER and is_active is True.
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

DEFAULT_L2_EMAIL = "l2_manager@cpass.org"
DEFAULT_L2_NAME = "Suresh Kumar (Centre Manager)"
DEFAULT_L2_PASS = "Cpass@Manager2026!"


def create_or_update_l2_user(
    email: str = DEFAULT_L2_EMAIL,
    password: str = DEFAULT_L2_PASS,
    full_name: str = DEFAULT_L2_NAME,
) -> dict:
    email = email.strip().lower()
    print(f"Creating/Verifying L2 Center Manager account for: {email}...")

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

    # 3. Check public.profiles record
    prof_res = supabase.table("profiles").select("*").eq("id", user_id).execute()
    profile_data = {
        "id": user_id,
        "email": email,
        "full_name": full_name,
        "role": "L2_MANAGER",
        "is_active": True,
    }

    if not prof_res.data:
        print("[INFO] Creating matching row in public.profiles...")
        insert_res = supabase.table("profiles").insert(profile_data).execute()
        print(f"[OK] Inserted profile record: {insert_res.data}")
    else:
        print(f"[INFO] Existing profile found. Ensuring role=L2_MANAGER and is_active=True...")
        update_res = (
            supabase.table("profiles")
            .update({"role": "L2_MANAGER", "is_active": True, "full_name": full_name, "email": email})
            .eq("id", user_id)
            .execute()
        )
        print(f"[OK] Updated profile record: {update_res.data}")

    return {
        "user_id": user_id,
        "email": email,
        "role": "L2_MANAGER",
        "full_name": full_name,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create or verify L2 Center Manager user.")
    parser.add_argument("--email", default=DEFAULT_L2_EMAIL, help="User email")
    parser.add_argument("--password", default=DEFAULT_L2_PASS, help="User password")
    parser.add_argument("--name", default=DEFAULT_L2_NAME, help="Full name")
    args = parser.parse_args()

    res = create_or_update_l2_user(args.email, args.password, args.name)
    print("\nAccount Ready:")
    print(f"  Email: {res['email']}")
    print(f"  Role: {res['role']}")
    print(f"  Name: {res['full_name']}")
