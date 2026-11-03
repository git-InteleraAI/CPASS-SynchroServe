"""Provision and verify CPASS Management Accounts (L4 Business Leaders and L5 CEO).

Accounts:
1. Nama (BL)      -> States: TN, KL, GJ, RJ (TAMIL NADU, KERALA, GUJARAT, RAJASTHAN)
2. Shori (BL)     -> States: PUN, UP, WB (PUNJAB, UTTAR PRADESH, WEST BENGAL)
3. Sowbhagya (BL) -> States: AP (ANDHRA PRADESH)
4. Rajesh (BL)    -> States: MZ, OD, TS (MIZORAM, ODISHA, TELANGANA)
5. CEO (L5)       -> National access to all 12 states (assigned_state: None)

Run with:
    python backend/scripts/provision_management_accounts.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Load environment before importing app modules
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv

env_path = ROOT_DIR / "backend" / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv(ROOT_DIR / ".env")

from backend.app.auth import ALL_12_STATES, resolve_states
from backend.app.db import supabase

MANAGEMENT_ACCOUNTS = [
    {
        "key": "nama",
        "email": "nama.bl@synchroserve.in",
        "username": "nama.bl",
        "full_name": "Nama (Business Leader)",
        "role": "L4_LEADER",
        "assigned_state": "TAMIL NADU, KERALA, GUJARAT, RAJASTHAN",
        "default_password": "namabl@cpass",
        "description": "BL for Southern & Western region (TN, KL, GJ, RJ)",
    },
    {
        "key": "shori",
        "email": "shori.bl@synchroserve.in",
        "username": "shori.bl",
        "full_name": "Shori (Business Leader)",
        "role": "L4_LEADER",
        "assigned_state": "PUNJAB, UTTAR PRADESH, WEST BENGAL",
        "default_password": "shoribl@cpass",
        "description": "BL for Northern & Eastern region (PUN, UP, WB)",
    },
    {
        "key": "sowbhagya",
        "email": "sowbhagya.bl@synchroserve.in",
        "username": "sowbhagya.bl",
        "full_name": "Sowbhagya (Business Leader)",
        "role": "L4_LEADER",
        "assigned_state": "ANDHRA PRADESH",
        "default_password": "sowbhagyabl@cpass",
        "description": "BL for Andhra Pradesh (AP)",
    },
    {
        "key": "rajesh",
        "email": "rajesh.bl@synchroserve.in",
        "username": "rajesh.bl",
        "full_name": "Rajesh (Business Leader)",
        "role": "L4_LEADER",
        "assigned_state": "MIZORAM, ODISHA, TELANGANA",
        "default_password": "rajeshbl@cpass",
        "description": "BL for Central, Eastern & North-Eastern region (MZ, OD, TS)",
    },
    {
        "key": "ceo",
        "email": "ceo@synchroserve.in",
        "username": "ceo",
        "full_name": "Chief Executive Officer",
        "role": "L5_CEO",
        "assigned_state": None,
        "default_password": "ceocpass@2026!",
        "description": "CEO with National access across all 12 CPASS states",
    },
]


def provision_accounts(rotate_passwords: bool = False):
    print("=" * 80)
    print("CPASS MANAGEMENT ACCOUNTS PROVISIONING (L4 BL & L5 CEO)")
    print("=" * 80)

    # 1. Fetch existing users from auth
    try:
        user_list_res = supabase.auth.admin.list_users()
        existing_users = {u.email.lower(): u for u in user_list_res if getattr(u, "email", None)}
    except Exception as exc:
        print(f"[ERROR] Failed to list auth users from Supabase: {exc}")
        return

    # 2. Process each management account
    for acc in MANAGEMENT_ACCOUNTS:
        email = acc["email"].lower()
        password = acc["default_password"]
        full_name = acc["full_name"]
        role = acc["role"]
        assigned_state = acc["assigned_state"]

        auth_user = existing_users.get(email)

        if not auth_user:
            print(f"[CREATE AUTH] Provisioning auth user: {email} ...")
            try:
                create_res = supabase.auth.admin.create_user({
                    "email": email,
                    "password": password,
                    "email_confirm": True,
                    "user_metadata": {
                        "full_name": full_name,
                        "role": role,
                        "assigned_state": assigned_state,
                    },
                })
                auth_user = getattr(create_res, "user", None) or create_res
                print(f"  -> Created auth user id: {auth_user.id}")
            except Exception as exc:
                print(f"  -> [ERROR] Failed to create auth user {email}: {exc}")
                continue
        else:
            print(f"[FOUND AUTH] Existing auth user: {email} (id: {auth_user.id})")
            if rotate_passwords:
                try:
                    supabase.auth.admin.update_user_by_id(auth_user.id, {
                        "password": password,
                        "email_confirm": True,
                        "user_metadata": {
                            "full_name": full_name,
                            "role": role,
                            "assigned_state": assigned_state,
                        },
                    })
                    print(f"  -> Password and metadata updated for {email}")
                except Exception as exc:
                    print(f"  -> [WARNING] Failed to update user {email}: {exc}")

        # 3. Upsert profile in public.profiles
        try:
            profile_payload = {
                "id": auth_user.id,
                "email": email,
                "full_name": full_name,
                "role": role,
                "assigned_state": assigned_state,
                "is_active": True,
            }
            res = (
                supabase.table("profiles")
                .upsert(profile_payload, on_conflict="id")
                .execute()
            )
            states_resolved = resolve_states(assigned_state) if assigned_state else ALL_12_STATES
            print(f"  -> [PROFILE OK] role: {role} | states ({len(states_resolved)}): {', '.join(states_resolved)}")
        except Exception as exc:
            print(f"  -> [ERROR] Failed to upsert profile for {email}: {exc}")

    print("\n" + "=" * 80)
    print("PROVISIONING COMPLETE. CREDENTIALS SUMMARY:")
    print("-" * 80)
    print(f"{'Role':<12} | {'Username':<15} | {'Email':<25} | {'States'}")
    print("-" * 80)
    for acc in MANAGEMENT_ACCOUNTS:
        st_display = acc["assigned_state"] or "ALL 12 STATES (National)"
        print(f"{acc['role']:<12} | {acc['username']:<15} | {acc['email']:<25} | {st_display}")
    print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Provision L4 BL and L5 CEO management accounts.")
    parser.add_argument("--rotate-passwords", action="store_true", help="Rotate passwords to default")
    args = parser.parse_args()
    provision_accounts(rotate_passwords=args.rotate_passwords)

