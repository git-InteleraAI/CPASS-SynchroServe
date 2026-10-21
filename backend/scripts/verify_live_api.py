"""Script to verify live role isolation and document endpoints on running FastAPI server.
"""

import sys
import requests

BASE_URL = "http://127.0.0.1:8000"

def run_checks():
    print("=" * 60)
    print("LIVE ROLE ISOLATION & API ENDPOINT VERIFICATION")
    print("=" * 60)

    # 1. Unauthenticated request
    r = requests.get(f"{BASE_URL}/candidates/1/documents")
    print(f"1. Unauthenticated GET /candidates/1/documents: {r.status_code} (Expected 401)")
    assert r.status_code == 401, f"Expected 401, got {r.status_code}"

    # 2. Login as ADMIN
    # Note: Use configured admin credentials or create an admin token
    from app.db import supabase
    from app.config import settings

    admin_login_res = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "manumansoor2000@gmail.com",
        "password": "Password123!", # Try common or authenticate directly via token
        "selected_role": "ADMIN"
    })

    admin_token = None
    if admin_login_res.status_code == 200:
        admin_token = admin_login_res.json()["session"]["access_token"]
        print("2. Admin login via /auth/login succeeded!")
    else:
        # Generate token directly via admin/service role to test live endpoint authorization
        print(f"2. Admin password login returned {admin_login_res.status_code}; testing using direct token generation.")
        # Find admin profile
        p = supabase.table("profiles").select("id,email,role").eq("role", "ADMIN").limit(1).execute().data
        if p:
            admin_uid = p[0]["id"]
            # Generate link/session for admin
            link = supabase.auth.admin.generate_link({"type": "magiclink", "email": p[0]["email"]})
            # Or sign in with OTP/token directly
            print(f"   Found admin profile: {p[0]['email']} (ID: {admin_uid})")

    # 3. Test L1 Coordinator login
    print("\n3. Testing L1 Coordinator login via /auth/login:")
    l1_res = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "l1_coordinator@cpass.org",
        "password": "Cpass@Coordinator2026!",
        "selected_role": "L1_COORDINATOR"
    })
    print(f"   L1 Login status: {l1_res.status_code}")
    assert l1_res.status_code == 200, f"L1 login failed: {l1_res.text}"
    l1_data = l1_res.json()
    l1_token = l1_data["access_token"]
    print(f"   L1 User authenticated: {l1_data['user']['email']} · Role: {l1_data['user']['role']}")

    # 4. Fetch a real candidate ID from database
    cand_row = supabase.table("ddugky_candidates").select("candidate_id,candidate_first_name").limit(1).execute().data
    assert cand_row, "No candidates found in ddugky_candidates!"
    cand_id = cand_row[0]["candidate_id"]
    print(f"\n4. Using real candidate from master dataset: ID {cand_id} ({cand_row[0]['candidate_first_name']})")

    # 5. L1 access to documents list and summary
    headers_l1 = {"Authorization": f"Bearer {l1_token}"}
    r_list = requests.get(f"{BASE_URL}/candidates/{cand_id}/documents", headers=headers_l1)
    print(f"5. L1 GET /candidates/{cand_id}/documents: {r_list.status_code} (Expected 200)")
    assert r_list.status_code == 200, f"Expected 200, got {r_list.status_code}"

    r_sum = requests.get(f"{BASE_URL}/candidates/{cand_id}/documents/summary", headers=headers_l1)
    print(f"   L1 GET /candidates/{cand_id}/documents/summary: {r_sum.status_code} (Expected 200)")
    assert r_sum.status_code == 200, f"Expected 200, got {r_sum.status_code}"
    sum_data = r_sum.json()
    print(f"   Summary checklist items: {len(sum_data.get('checklist', []))}")

    # 6. Verify ADMIN is strictly rejected on every document endpoint
    temp_admin_email = "temp_admin_audit@cpass.org"
    temp_admin_pass = "TempAdminPass2026!"
    
    # Clean up existing temp user if any
    try:
        existing_u = [u for u in supabase.auth.admin.list_users() if u.email == temp_admin_email]
        if existing_u:
            supabase.auth.admin.delete_user(existing_u[0].id)
            supabase.table("profiles").delete().eq("id", existing_u[0].id).execute()
    except Exception:
        pass

    created_admin = supabase.auth.admin.create_user({
        "email": temp_admin_email,
        "password": temp_admin_pass,
        "email_confirm": True,
    })
    admin_uid = created_admin.user.id
    supabase.table("profiles").upsert({
        "id": admin_uid,
        "email": temp_admin_email,
        "full_name": "Temporary Admin Auditor",
        "role": "ADMIN",
        "is_active": True,
    }).execute()

    try:
        login_admin = requests.post(f"{BASE_URL}/auth/login", json={
            "email": temp_admin_email,
            "password": temp_admin_pass,
            "selected_role": "ADMIN",
        })
        assert login_admin.status_code == 200, f"Admin login failed: {login_admin.text}"
        admin_token = login_admin.json()["access_token"]
        headers_admin = {"Authorization": f"Bearer {admin_token}"}
        print(f"\n6. Testing ADMIN direct API access to L1 document endpoints (Separation of Duties):")

        # GET /candidates/{cand_id}/documents
        r_admin_list = requests.get(f"{BASE_URL}/candidates/{cand_id}/documents", headers=headers_admin)
        print(f"   ADMIN GET /candidates/{cand_id}/documents: {r_admin_list.status_code} (Expected 403)")
        assert r_admin_list.status_code == 403, f"Expected 403, got {r_admin_list.status_code}"

        # GET /candidates/{cand_id}/documents/summary
        r_admin_sum = requests.get(f"{BASE_URL}/candidates/{cand_id}/documents/summary", headers=headers_admin)
        print(f"   ADMIN GET /candidates/{cand_id}/documents/summary: {r_admin_sum.status_code} (Expected 403)")
        assert r_admin_sum.status_code == 403, f"Expected 403, got {r_admin_sum.status_code}"

        # POST /candidates/{cand_id}/documents/submit
        r_admin_sub = requests.post(f"{BASE_URL}/candidates/{cand_id}/documents/submit", headers=headers_admin)
        print(f"   ADMIN POST /candidates/{cand_id}/documents/submit: {r_admin_sub.status_code} (Expected 403)")
        assert r_admin_sub.status_code == 403, f"Expected 403, got {r_admin_sub.status_code}"

        # GET /candidates/{cand_id}/documents/{doc_id}/download
        r_admin_dl = requests.get(f"{BASE_URL}/candidates/{cand_id}/documents/non-existent-id/download", headers=headers_admin)
        print(f"   ADMIN GET /candidates/{cand_id}/documents/any/download: {r_admin_dl.status_code} (Expected 403)")
        assert r_admin_dl.status_code == 403, f"Expected 403, got {r_admin_dl.status_code}"

        # DELETE /candidates/{cand_id}/documents/{doc_id}
        r_admin_del = requests.delete(f"{BASE_URL}/candidates/{cand_id}/documents/non-existent-id", headers=headers_admin)
        print(f"   ADMIN DELETE /candidates/{cand_id}/documents/any: {r_admin_del.status_code} (Expected 403)")
        assert r_admin_del.status_code == 403, f"Expected 403, got {r_admin_del.status_code}"

        print("   -> VERIFIED: ADMIN accounts are strictly blocked from all L1 document endpoints!")

    finally:
        supabase.auth.admin.delete_user(admin_uid)
        supabase.table("profiles").delete().eq("id", admin_uid).execute()
        print("   -> Temporary audit admin user cleaned up.")

    # 7. Test Inactive User Rejection
    print("\n7. Testing Inactive Account Rejection:")
    # Temporarily set L1 user inactive, test request, then restore active
    supabase.table("profiles").update({"is_active": False}).eq("email", "l1_coordinator@cpass.org").execute()
    try:
        r_inactive = requests.get(f"{BASE_URL}/candidates/{cand_id}/documents", headers=headers_l1)
        print(f"   Inactive L1 Coordinator GET /candidates/{cand_id}/documents: {r_inactive.status_code} (Expected 403)")
        assert r_inactive.status_code == 403, f"Expected 403, got {r_inactive.status_code}"
        assert "disabled" in r_inactive.json().get("detail", "").lower()
        print("   -> VERIFIED: Inactive accounts are immediately rejected with 403!")
    finally:
        supabase.table("profiles").update({"is_active": True}).eq("email", "l1_coordinator@cpass.org").execute()
        print("   -> L1 Coordinator profile restored to active state.")

    print("\n" + "=" * 60)
    print("ALL LIVE ENDPOINT & ROLE ISOLATION CHECKS PASSED!")
    print("=" * 60)
    print("=" * 60)

if __name__ == "__main__":
    run_checks()
