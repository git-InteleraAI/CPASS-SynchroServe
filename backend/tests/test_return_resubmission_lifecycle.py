"""Automated regression test suite for CPASS L1 to L5 Return & Resubmission Lifecycle.

Verifies all 10 return scenarios, resubmissions, intermediate sequencing, and return history preservation:
- L2 -> L1 -> L1 resubmission -> L2 re-review
- L3 -> L1 -> L1 resubmission -> L2 recommendation -> L3 verification
- L3 -> L2 -> L2 re-recommendation -> L3 verification
- L4 -> L1 -> L1 resubmission -> L2 recommendation -> L3 verification -> L4 approval
- L4 -> L2 -> L2 re-recommendation -> L3 verification -> L4 approval
- L4 -> L3 -> L3 re-verification -> L4 approval
- L5 -> L1 -> L1 resubmission -> L2 recommendation -> L3 verification -> L4 approval -> L5 sanction
- L5 -> L2 -> L2 re-recommendation -> L3 verification -> L4 approval -> L5 sanction
- L5 -> L3 -> L3 re-verification -> L4 approval -> L5 sanction
- L5 -> L4 -> L4 re-approval -> L5 sanction
- Multi-cycle returns and historical audit trail preservation
- Gate validation ensuring intermediate levels cannot be bypassed
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.auth import CurrentUser, get_current_user
from app.main import app
from app.routers.audits import extract_review_stages

client = TestClient(app)

L1_USER = CurrentUser(
    id="l1-user-uuid",
    email="l1.odisha@cpass.org",
    full_name="L1 Coordinator",
    role="L1_COORDINATOR",
    assigned_state="ODISHA",
)

L2_USER = CurrentUser(
    id="l2-user-uuid",
    email="l2.ch@cpass.org",
    full_name="L2 Centre Head",
    role="L2_MANAGER",
    assigned_state="ODISHA",
)

L3_USER = CurrentUser(
    id="l3-user-uuid",
    email="l3.cops@cpass.org",
    full_name="L3 COPS Auditor",
    role="L3_COPS",
)

L4_USER = CurrentUser(
    id="l4-user-uuid",
    email="l4.bl@cpass.org",
    full_name="L4 Business Leader",
    role="L4_LEADER",
    assigned_states=["ODISHA"],
)

L5_USER = CurrentUser(
    id="l5-user-uuid",
    email="ceo@cpass.org",
    full_name="Chief Executive Officer",
    role="L5_CEO",
)

CANDIDATE_ODISHA = {
    "candidate_id": 10482,
    "state_name": "ODISHA",
    "candidate_first_name": "Rajesh",
    "candidate_last_name": "Patel",
    "tc_id": 101,
    "tc_name": "Bhubaneswar Skill Centre",
    "tc_state_name": "ODISHA",
    "employer_name": "Reliance Retail Ltd",
}

SAMPLE_EMPLOYER_DETAILS = [
    {
        "id": "emp_1",
        "employer_name": "Reliance Retail Ltd",
        "work_location": "Bhubaneswar",
        "designation": "Sales Associate",
    }
]

SAMPLE_SALARY_DETAILS = [
    {"employer_id": "emp_1", "month": 1, "year": 2024, "amount_credited": 12500.0, "gross_salary": 14000.0},
    {"employer_id": "emp_1", "month": 2, "year": 2024, "amount_credited": 12500.0, "gross_salary": 14000.0},
    {"employer_id": "emp_1", "month": 3, "year": 2024, "amount_credited": 12500.0, "gross_salary": 14000.0},
]

SUBMIT_PAYLOAD = {
    "candidate_snapshot": CANDIDATE_ODISHA,
    "employer_details": SAMPLE_EMPLOYER_DETAILS,
    "salary_details": SAMPLE_SALARY_DETAILS,
    "document_audit": {
        "appointment_letter_status": "Uploaded",
        "salary_slips_status": "Uploaded",
        "bank_statements_status": "Uploaded",
    },
    "signoff_details": {},
    "remarks": "Updated placement audit statement with verified documents.",
}


def mock_docs():
    return [
        {"id": 101, "candidate_id": 10482, "document_type": "APPOINTMENT_LETTER", "upload_status": "SUCCESS", "employer_id": "emp_1"},
        {"id": 102, "candidate_id": 10482, "document_type": "SALARY_SLIP", "reporting_month": 1, "reporting_year": 2024, "upload_status": "SUCCESS", "employer_id": "emp_1"},
        {"id": 103, "candidate_id": 10482, "document_type": "SALARY_SLIP", "reporting_month": 2, "reporting_year": 2024, "upload_status": "SUCCESS", "employer_id": "emp_1"},
        {"id": 104, "candidate_id": 10482, "document_type": "SALARY_SLIP", "reporting_month": 3, "reporting_year": 2024, "upload_status": "SUCCESS", "employer_id": "emp_1"},
        {"id": 105, "candidate_id": 10482, "document_type": "BANK_STATEMENT", "reporting_month": 1, "reporting_year": 2024, "upload_status": "SUCCESS"},
        {"id": 106, "candidate_id": 10482, "document_type": "BANK_STATEMENT", "reporting_month": 2, "reporting_year": 2024, "upload_status": "SUCCESS"},
        {"id": 107, "candidate_id": 10482, "document_type": "BANK_STATEMENT", "reporting_month": 3, "reporting_year": 2024, "upload_status": "SUCCESS"},
    ]


def mock_l2_reviewed_audit(base_audit):
    aud = dict(base_audit)
    doc_aud = dict(aud.get("document_audit") or {})
    doc_aud["l2_document_reviews"] = {str(d["id"]): {"reviewed": True} for d in mock_docs()}
    aud["document_audit"] = doc_aud
    return aud


def setup_supabase_mock(audit_data):
    """Create a mock supabase client that reads and updates the provided audit_data in-memory."""
    store = {"audit": dict(audit_data) if audit_data else None}

    def table_mock(tbl):
        m = MagicMock()
        if tbl == "ddugky_candidates":
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[CANDIDATE_ODISHA])
        elif tbl == "candidate_documents":
            m.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(data=mock_docs())
        elif tbl == "candidate_holds":
            m.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        elif tbl == "placement_audits":
            def select_side_effect(*args, **kwargs):
                sel_chain = MagicMock()
                def exec_select():
                    data = [dict(store["audit"])] if store["audit"] else []
                    return MagicMock(data=data)
                sel_chain.eq.return_value.limit.return_value.execute.side_effect = exec_select
                sel_chain.eq.return_value.execute.side_effect = exec_select
                sel_chain.execute.side_effect = exec_select
                return sel_chain
            m.select.side_effect = select_side_effect

            def update_side_effect(up_data):
                up_mock = MagicMock()
                def exec_update():
                    if store["audit"]:
                        store["audit"].update(up_data)
                    else:
                        store["audit"] = dict(up_data)
                    return MagicMock(data=[dict(store["audit"])])
                up_mock.eq.return_value.execute.side_effect = exec_update
                up_mock.execute.side_effect = exec_update
                return up_mock
            m.update.side_effect = update_side_effect

            def insert_side_effect(ins_data):
                ins_mock = MagicMock()
                def exec_insert():
                    store["audit"] = dict(ins_data)
                    return MagicMock(data=[dict(store["audit"])])
                ins_mock.execute.side_effect = exec_insert
                return ins_mock
            m.insert.side_effect = insert_side_effect
        return m

    mock_client = MagicMock()
    mock_client.table.side_effect = table_mock
    return mock_client, store


# =============================================================================
# SCENARIO 1: L2 -> L1 -> L1 Resubmit -> L2 Review
# =============================================================================

def test_scenario_1_l2_return_to_l1_and_resubmit():
    """L2 returns to L1. L1 resubmits. L2 sees PENDING/SUBMITTED, no return banner, can approve."""
    initial_audit = {
        "id": "audit-sc-1",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "PENDING",
        "signoff_details": {
            "review_stages": {"ch": {"status": "Pending"}, "cops": {"status": "Pending"}, "bl": {"status": "Pending"}, "ceo": {"status": "Pending"}},
        },
    }
    mock_sb, store = setup_supabase_mock(initial_audit)

    with patch("app.routers.audits.supabase", mock_sb), patch("app.routers.auth.supabase", mock_sb):
        app.dependency_overrides[get_current_user] = lambda: L2_USER
        # Step 1: L2 returns to L1
        ret_res = client.post("/candidates/10482/audit/l2-review/return-to-l1", json={"return_reason": "Missing salary slip 3"})
        assert ret_res.status_code == 200
        assert store["audit"]["cpass_status"] == "RETURNED_TO_L1"
        assert store["audit"]["audit_status"] == "RETURNED_TO_L1"
        assert store["audit"]["signoff_details"]["review_stages"]["ch"]["status"] == "Returned to L1"
        assert store["audit"]["signoff_details"]["active_return"]["destination"] == "L1"

        # Step 2: L1 resubmits
        app.dependency_overrides[get_current_user] = lambda: L1_USER
        sub_res = client.post("/candidates/10482/audit/submit", json=SUBMIT_PAYLOAD)
        if sub_res.status_code != 200:
            print("SUB_RES ERROR:", sub_res.status_code, sub_res.text)
        assert sub_res.status_code == 200
        assert store["audit"]["cpass_status"] == "PENDING"
        assert store["audit"]["audit_status"] == "SUBMITTED"
        assert store["audit"]["signoff_details"]["review_stages"]["ch"]["status"] == "Pending"
        assert store["audit"]["signoff_details"]["review_stages"]["cops"]["status"] == "Pending"
        assert store["audit"]["signoff_details"]["review_stages"]["ceo"]["status"] == "Pending"
        # Active return MUST be cleared
        assert store["audit"]["signoff_details"].get("active_return") is None
        assert "return_to_l1" not in store["audit"]["signoff_details"]
        assert len(store["audit"]["signoff_details"]["return_history"]) == 1

        # Step 3: L2 views audit statement
        app.dependency_overrides[get_current_user] = lambda: L2_USER
        stmt_res = client.get("/candidates/10482/audit/statement")
        assert stmt_res.status_code == 200
        stmt_data = stmt_res.json()
        assert stmt_data["cpass_status"] == "PENDING"
        assert stmt_data["audit_status"] == "SUBMITTED"
        assert stmt_data["active_return"] is None
        assert stmt_data["return_to_l1"] is None
        assert stmt_data["review_stages"]["ch_status"] == "Pending"

        # Step 4: L2 approves after completing checklist
        store["audit"] = mock_l2_reviewed_audit(store["audit"])
        app_res = client.post("/candidates/10482/audit/l2-review/approve", json={"remarks": "Verified slips"})
        assert app_res.status_code == 200
        assert store["audit"]["cpass_status"] == "L2_APPROVED"
        assert store["audit"]["signoff_details"]["review_stages"]["ch"]["status"] == "Recommended"
        assert store["audit"]["signoff_details"].get("active_return") is None


# =============================================================================
# SCENARIO 2: L3 -> L1 -> L1 Resubmit -> L2 -> L3
# =============================================================================

def test_scenario_2_l3_return_to_l1_and_full_resubmission_cycle():
    """L3 returns to L1. L1 resubmits. Must go through L2 before L3 can verify."""
    initial_audit = {
        "id": "audit-sc-2",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "L2_APPROVED",
        "document_audit": {"l2_review_completed": True},
        "signoff_details": {
            "review_stages": {"ch": {"status": "Recommended"}, "cops": {"status": "Pending"}, "bl": {"status": "Pending"}, "ceo": {"status": "Pending"}},
            "centre_head": {"confirmed": True, "recommended": True},
            "l2_approval": {"approved": True},
        },
    }
    mock_sb, store = setup_supabase_mock(initial_audit)

    with patch("app.routers.audits.supabase", mock_sb), patch("app.routers.auth.supabase", mock_sb):
        app.dependency_overrides[get_current_user] = lambda: L3_USER
        # Step 1: L3 returns to L1
        ret_res = client.post("/candidates/10482/audit/l3-review/return", json={"destination": "L1", "return_reason": "Incomplete bank statement"})
        assert ret_res.status_code == 200
        assert store["audit"]["cpass_status"] == "RETURNED_TO_L1"
        assert store["audit"]["signoff_details"]["active_return"]["destination"] == "L1"

        # Step 2: L3 cannot immediately re-verify while with L1
        block_res = client.post("/candidates/10482/audit/l3-review/approve", json={"remarks": "Try verify"})
        assert block_res.status_code == 400

        # Step 3: L1 resubmits
        app.dependency_overrides[get_current_user] = lambda: L1_USER
        sub_res = client.post("/candidates/10482/audit/submit", json=SUBMIT_PAYLOAD)
        assert sub_res.status_code == 200
        assert store["audit"]["cpass_status"] == "PENDING"
        assert store["audit"]["signoff_details"]["review_stages"]["ch"]["status"] == "Pending"
        assert store["audit"]["signoff_details"].get("active_return") is None

        # Step 4: L3 still cannot verify because L2 has not recommended yet!
        app.dependency_overrides[get_current_user] = lambda: L3_USER
        block_res2 = client.post("/candidates/10482/audit/l3-review/approve", json={"remarks": "Try verify"})
        assert block_res2.status_code == 400

        # Step 5: L2 reviews and approves
        app.dependency_overrides[get_current_user] = lambda: L2_USER
        store["audit"] = mock_l2_reviewed_audit(store["audit"])
        l2_app = client.post("/candidates/10482/audit/l2-review/approve", json={"remarks": "Re-verified after L3 return"})
        assert l2_app.status_code == 200
        assert store["audit"]["cpass_status"] == "L2_APPROVED"
        assert store["audit"]["signoff_details"]["review_stages"]["ch"]["status"] == "Recommended"

        # Step 6: Now L3 can verify
        app.dependency_overrides[get_current_user] = lambda: L3_USER
        l3_app = client.post("/candidates/10482/audit/l3-review/approve", json={"remarks": "Verified bank statement"})
        assert l3_app.status_code == 200
        assert store["audit"]["cpass_status"] == "VERIFIED"
        assert store["audit"]["signoff_details"]["review_stages"]["cops"]["status"] == "Verified"


# =============================================================================
# SCENARIO 3: L3 -> L2 -> L2 Review -> L3 Verify
# =============================================================================

def test_scenario_3_l3_return_to_l2_and_rereview():
    """L3 returns to L2. Candidate is SUBMITTED, CH is Pending. L2 re-approves. L3 verifies."""
    initial_audit = {
        "id": "audit-sc-3",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "L2_APPROVED",
        "document_audit": {"l2_review_completed": True},
        "signoff_details": {
            "review_stages": {"ch": {"status": "Recommended"}, "cops": {"status": "Pending"}, "bl": {"status": "Pending"}, "ceo": {"status": "Pending"}},
            "centre_head": {"confirmed": True, "recommended": True},
            "l2_approval": {"approved": True},
        },
    }
    mock_sb, store = setup_supabase_mock(initial_audit)

    with patch("app.routers.audits.supabase", mock_sb), patch("app.routers.auth.supabase", mock_sb):
        app.dependency_overrides[get_current_user] = lambda: L3_USER
        # Step 1: L3 returns to L2
        ret_res = client.post("/candidates/10482/audit/l3-review/return", json={"destination": "L2", "return_reason": "Salary credit amount discrepancy"})
        assert ret_res.status_code == 200
        assert store["audit"]["cpass_status"] == "SUBMITTED"
        assert store["audit"]["signoff_details"]["review_stages"]["ch"]["status"] == "Pending"
        assert store["audit"]["signoff_details"]["active_return"]["destination"] == "L2"

        # Step 2: L3 cannot approve while waiting for L2
        block_res = client.post("/candidates/10482/audit/l3-review/approve", json={"remarks": "Premature verify"})
        assert block_res.status_code == 400

        # Step 3: L2 re-reviews and approves
        app.dependency_overrides[get_current_user] = lambda: L2_USER
        store["audit"] = mock_l2_reviewed_audit(store["audit"])
        l2_app = client.post("/candidates/10482/audit/l2-review/approve", json={"remarks": "Corrected salary details with manager note"})
        assert l2_app.status_code == 200
        assert store["audit"]["cpass_status"] == "L2_APPROVED"
        assert store["audit"]["signoff_details"]["review_stages"]["ch"]["status"] == "Recommended"
        assert store["audit"]["signoff_details"].get("active_return") is None

        # Step 4: L3 verifies
        app.dependency_overrides[get_current_user] = lambda: L3_USER
        l3_app = client.post("/candidates/10482/audit/l3-review/approve", json={"remarks": "Verified and satisfied with corrections"})
        assert l3_app.status_code == 200
        assert store["audit"]["cpass_status"] == "VERIFIED"


# =============================================================================
# SCENARIO 4: L4 -> L1 -> Resubmit -> L2 -> L3 -> L4
# =============================================================================

def test_scenario_4_l4_return_to_l1_and_progression():
    """L4 BL returns to L1. L1 resubmits. Must follow L2 -> L3 -> L4 sequence."""
    initial_audit = {
        "id": "audit-sc-4",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "VERIFIED",
        "document_audit": {"l2_review_completed": True},
        "signoff_details": {
            "review_stages": {"ch": {"status": "Recommended"}, "cops": {"status": "Verified"}, "bl": {"status": "Pending"}, "ceo": {"status": "Pending"}},
            "centre_head": {"confirmed": True, "recommended": True},
            "l2_approval": {"approved": True},
            "cops_team": {"confirmed": True},
        },
    }
    mock_sb, store = setup_supabase_mock(initial_audit)

    with patch("app.routers.audits.supabase", mock_sb), patch("app.routers.auth.supabase", mock_sb):
        app.dependency_overrides[get_current_user] = lambda: L4_USER
        ret_res = client.post("/candidates/10482/audit/l4-review/return", json={"destination": "L1", "return_reason": "Missing employer appointment letter"})
        assert ret_res.status_code == 200
        assert store["audit"]["cpass_status"] == "RETURNED_TO_L1"

        # L1 resubmits
        app.dependency_overrides[get_current_user] = lambda: L1_USER
        sub_res = client.post("/candidates/10482/audit/submit", json=SUBMIT_PAYLOAD)
        assert sub_res.status_code == 200
        assert store["audit"]["cpass_status"] == "PENDING"
        assert store["audit"]["signoff_details"]["review_stages"]["ch"]["status"] == "Pending"

        # Neither L3 nor L4 can approve until L2 recommends
        app.dependency_overrides[get_current_user] = lambda: L4_USER
        assert client.post("/candidates/10482/audit/l4-review/approve", json={}).status_code == 400

        # L2 approves
        app.dependency_overrides[get_current_user] = lambda: L2_USER
        store["audit"] = mock_l2_reviewed_audit(store["audit"])
        assert client.post("/candidates/10482/audit/l2-review/approve", json={}).status_code == 200

        # L3 verifies
        app.dependency_overrides[get_current_user] = lambda: L3_USER
        assert client.post("/candidates/10482/audit/l3-review/approve", json={}).status_code == 200

        # L4 approves
        app.dependency_overrides[get_current_user] = lambda: L4_USER
        l4_app = client.post("/candidates/10482/audit/l4-review/approve", json={"remarks": "BL approval complete"})
        assert l4_app.status_code == 200
        assert store["audit"]["signoff_details"]["review_stages"]["bl"]["status"] == "Approved"
        assert store["audit"]["signoff_details"].get("active_return") is None


# =============================================================================
# SCENARIO 5: L4 -> L2 -> L2 -> L3 -> L4
# =============================================================================

def test_scenario_5_l4_return_to_l2_and_progression():
    """L4 BL returns to L2. L2 re-approves. L3 re-verifies. L4 approves."""
    initial_audit = {
        "id": "audit-sc-5",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "VERIFIED",
        "document_audit": {"l2_review_completed": True},
        "signoff_details": {
            "review_stages": {"ch": {"status": "Recommended"}, "cops": {"status": "Verified"}, "bl": {"status": "Pending"}, "ceo": {"status": "Pending"}},
            "centre_head": {"confirmed": True, "recommended": True},
            "cops_team": {"confirmed": True},
        },
    }
    mock_sb, store = setup_supabase_mock(initial_audit)

    with patch("app.routers.audits.supabase", mock_sb), patch("app.routers.auth.supabase", mock_sb):
        app.dependency_overrides[get_current_user] = lambda: L4_USER
        ret_res = client.post("/candidates/10482/audit/l4-review/return", json={"destination": "L2", "return_reason": "Salary slips unclear"})
        assert ret_res.status_code == 200
        assert store["audit"]["cpass_status"] == "SUBMITTED"
        assert store["audit"]["signoff_details"]["review_stages"]["ch"]["status"] == "Pending"
        assert store["audit"]["signoff_details"]["active_return"]["destination"] == "L2"

        # L2 approves
        app.dependency_overrides[get_current_user] = lambda: L2_USER
        store["audit"] = mock_l2_reviewed_audit(store["audit"])
        assert client.post("/candidates/10482/audit/l2-review/approve", json={}).status_code == 200
        assert store["audit"]["cpass_status"] == "L2_APPROVED"
        assert store["audit"]["signoff_details"].get("active_return") is None

        # L3 verifies
        app.dependency_overrides[get_current_user] = lambda: L3_USER
        assert client.post("/candidates/10482/audit/l3-review/approve", json={}).status_code == 200
        assert store["audit"]["cpass_status"] == "VERIFIED"

        # L4 approves
        app.dependency_overrides[get_current_user] = lambda: L4_USER
        assert client.post("/candidates/10482/audit/l4-review/approve", json={}).status_code == 200
        assert store["audit"]["signoff_details"]["review_stages"]["bl"]["status"] == "Approved"


# =============================================================================
# SCENARIO 6: L4 -> L3 -> L3 -> L4
# =============================================================================

def test_scenario_6_l4_return_to_l3_and_reapproval():
    """L4 BL returns to L3. CH recommendation preserved. L3 re-verifies. L4 approves."""
    initial_audit = {
        "id": "audit-sc-6",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "VERIFIED",
        "document_audit": {"l2_review_completed": True},
        "signoff_details": {
            "review_stages": {"ch": {"status": "Recommended"}, "cops": {"status": "Verified"}, "bl": {"status": "Pending"}, "ceo": {"status": "Pending"}},
            "centre_head": {"confirmed": True, "recommended": True},
            "cops_team": {"confirmed": True},
        },
    }
    mock_sb, store = setup_supabase_mock(initial_audit)

    with patch("app.routers.audits.supabase", mock_sb), patch("app.routers.auth.supabase", mock_sb):
        app.dependency_overrides[get_current_user] = lambda: L4_USER
        ret_res = client.post("/candidates/10482/audit/l4-review/return", json={"destination": "L3", "return_reason": "Bank statement verification query"})
        assert ret_res.status_code == 200
        assert store["audit"]["cpass_status"] == "L2_APPROVED"
        assert store["audit"]["signoff_details"]["review_stages"]["ch"]["status"] == "Recommended"
        assert store["audit"]["signoff_details"]["review_stages"]["cops"]["status"] == "Pending"
        assert store["audit"]["signoff_details"]["active_return"]["destination"] == "L3"

        # L3 re-verifies
        app.dependency_overrides[get_current_user] = lambda: L3_USER
        assert client.post("/candidates/10482/audit/l3-review/approve", json={}).status_code == 200
        assert store["audit"]["cpass_status"] == "VERIFIED"
        assert store["audit"]["signoff_details"].get("active_return") is None

        # L4 approves
        app.dependency_overrides[get_current_user] = lambda: L4_USER
        assert client.post("/candidates/10482/audit/l4-review/approve", json={}).status_code == 200
        assert store["audit"]["signoff_details"]["review_stages"]["bl"]["status"] == "Approved"


# =============================================================================
# SCENARIO 7: L5 -> L1 -> L1 Resubmit -> L2 -> L3 -> L4 -> L5
# =============================================================================

def test_scenario_7_l5_return_to_l1_full_lifecycle():
    """L5 CEO returns to L1. Complete lifecycle through all 5 levels."""
    initial_audit = {
        "id": "audit-sc-7",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "APPROVED",
        "document_audit": {"l2_review_completed": True},
        "signoff_details": {
            "review_stages": {"ch": {"status": "Recommended"}, "cops": {"status": "Verified"}, "bl": {"status": "Approved"}, "ceo": {"status": "Pending"}},
            "centre_head": {"confirmed": True, "recommended": True},
            "cops_team": {"confirmed": True},
            "business_leader": {"confirmed": True},
        },
    }
    mock_sb, store = setup_supabase_mock(initial_audit)

    with patch("app.routers.audits.supabase", mock_sb), patch("app.routers.auth.supabase", mock_sb):
        app.dependency_overrides[get_current_user] = lambda: L5_USER
        ret_res = client.post("/candidates/10482/audit/l5-review/return", json={"destination": "L1", "return_reason": "Appointment letter illegible"})
        assert ret_res.status_code == 200
        assert store["audit"]["cpass_status"] == "RETURNED_TO_L1"

        # L1 resubmits
        app.dependency_overrides[get_current_user] = lambda: L1_USER
        assert client.post("/candidates/10482/audit/submit", json=SUBMIT_PAYLOAD).status_code == 200
        assert store["audit"]["cpass_status"] == "PENDING"

        # L2 approves
        app.dependency_overrides[get_current_user] = lambda: L2_USER
        store["audit"] = mock_l2_reviewed_audit(store["audit"])
        assert client.post("/candidates/10482/audit/l2-review/approve", json={}).status_code == 200

        # L3 verifies
        app.dependency_overrides[get_current_user] = lambda: L3_USER
        assert client.post("/candidates/10482/audit/l3-review/approve", json={}).status_code == 200

        # L4 approves
        app.dependency_overrides[get_current_user] = lambda: L4_USER
        assert client.post("/candidates/10482/audit/l4-review/approve", json={}).status_code == 200

        # L5 approves
        app.dependency_overrides[get_current_user] = lambda: L5_USER
        l5_app = client.post("/candidates/10482/audit/l5-review/approve", json={"remarks": "Executive sanction granted"})
        assert l5_app.status_code == 200
        assert store["audit"]["cpass_status"] == "APPROVED"
        assert store["audit"]["audit_status"] == "APPROVED"
        assert store["audit"]["signoff_details"]["review_stages"]["ceo"]["status"] == "Approved"
        assert store["audit"]["signoff_details"].get("active_return") is None


# =============================================================================
# SCENARIO 8: L5 -> L2 -> L2 -> L3 -> L4 -> L5
# =============================================================================

def test_scenario_8_l5_return_to_l2():
    """L5 CEO returns to L2. L2 re-approves. Follows L3 -> L4 -> L5."""
    initial_audit = {
        "id": "audit-sc-8",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "APPROVED",
        "document_audit": {"l2_review_completed": True},
        "signoff_details": {
            "review_stages": {"ch": {"status": "Recommended"}, "cops": {"status": "Verified"}, "bl": {"status": "Approved"}, "ceo": {"status": "Pending"}},
            "centre_head": {"confirmed": True, "recommended": True},
            "cops_team": {"confirmed": True},
            "business_leader": {"confirmed": True},
        },
    }
    mock_sb, store = setup_supabase_mock(initial_audit)

    with patch("app.routers.audits.supabase", mock_sb), patch("app.routers.auth.supabase", mock_sb):
        app.dependency_overrides[get_current_user] = lambda: L5_USER
        ret_res = client.post("/candidates/10482/audit/l5-review/return", json={"destination": "L2", "return_reason": "Audit checklist notes incomplete"})
        assert ret_res.status_code == 200
        assert store["audit"]["cpass_status"] == "SUBMITTED"
        assert store["audit"]["signoff_details"]["review_stages"]["ch"]["status"] == "Pending"

        # L2 approves
        app.dependency_overrides[get_current_user] = lambda: L2_USER
        store["audit"] = mock_l2_reviewed_audit(store["audit"])
        assert client.post("/candidates/10482/audit/l2-review/approve", json={}).status_code == 200

        # L3 verifies
        app.dependency_overrides[get_current_user] = lambda: L3_USER
        assert client.post("/candidates/10482/audit/l3-review/approve", json={}).status_code == 200

        # L4 approves
        app.dependency_overrides[get_current_user] = lambda: L4_USER
        assert client.post("/candidates/10482/audit/l4-review/approve", json={}).status_code == 200

        # L5 approves
        app.dependency_overrides[get_current_user] = lambda: L5_USER
        assert client.post("/candidates/10482/audit/l5-review/approve", json={}).status_code == 200
        assert store["audit"]["cpass_status"] == "APPROVED"


# =============================================================================
# SCENARIO 9: L5 -> L3 -> L3 -> L4 -> L5
# =============================================================================

def test_scenario_9_l5_return_to_l3():
    """L5 CEO returns to L3. CH recommendation preserved. Follows L3 -> L4 -> L5."""
    initial_audit = {
        "id": "audit-sc-9",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "APPROVED",
        "document_audit": {"l2_review_completed": True},
        "signoff_details": {
            "review_stages": {"ch": {"status": "Recommended"}, "cops": {"status": "Verified"}, "bl": {"status": "Approved"}, "ceo": {"status": "Pending"}},
            "centre_head": {"confirmed": True, "recommended": True},
            "cops_team": {"confirmed": True},
            "business_leader": {"confirmed": True},
        },
    }
    mock_sb, store = setup_supabase_mock(initial_audit)

    with patch("app.routers.audits.supabase", mock_sb), patch("app.routers.auth.supabase", mock_sb):
        app.dependency_overrides[get_current_user] = lambda: L5_USER
        ret_res = client.post("/candidates/10482/audit/l5-review/return", json={"destination": "L3", "return_reason": "Bank statement re-audit required"})
        assert ret_res.status_code == 200
        assert store["audit"]["cpass_status"] == "L2_APPROVED"
        assert store["audit"]["signoff_details"]["review_stages"]["ch"]["status"] == "Recommended"
        assert store["audit"]["signoff_details"]["review_stages"]["cops"]["status"] == "Pending"

        # L3 verifies
        app.dependency_overrides[get_current_user] = lambda: L3_USER
        assert client.post("/candidates/10482/audit/l3-review/approve", json={}).status_code == 200

        # L4 approves
        app.dependency_overrides[get_current_user] = lambda: L4_USER
        assert client.post("/candidates/10482/audit/l4-review/approve", json={}).status_code == 200

        # L5 approves
        app.dependency_overrides[get_current_user] = lambda: L5_USER
        assert client.post("/candidates/10482/audit/l5-review/approve", json={}).status_code == 200
        assert store["audit"]["cpass_status"] == "APPROVED"


# =============================================================================
# SCENARIO 10: L5 -> L4 -> L4 -> L5
# =============================================================================

def test_scenario_10_l5_return_to_l4():
    """L5 CEO returns to L4. CH and COPS preserved. L4 re-approves. L5 sanctions."""
    initial_audit = {
        "id": "audit-sc-10",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "APPROVED",
        "document_audit": {"l2_review_completed": True},
        "signoff_details": {
            "review_stages": {"ch": {"status": "Recommended"}, "cops": {"status": "Verified"}, "bl": {"status": "Approved"}, "ceo": {"status": "Pending"}},
            "centre_head": {"confirmed": True, "recommended": True},
            "cops_team": {"confirmed": True},
            "business_leader": {"confirmed": True},
        },
    }
    mock_sb, store = setup_supabase_mock(initial_audit)

    with patch("app.routers.audits.supabase", mock_sb), patch("app.routers.auth.supabase", mock_sb):
        app.dependency_overrides[get_current_user] = lambda: L5_USER
        ret_res = client.post("/candidates/10482/audit/l5-review/return", json={"destination": "L4", "return_reason": "Executive question on compensation band"})
        assert ret_res.status_code == 200
        assert store["audit"]["cpass_status"] == "VERIFIED"
        assert store["audit"]["signoff_details"]["review_stages"]["ch"]["status"] == "Recommended"
        assert store["audit"]["signoff_details"]["review_stages"]["cops"]["status"] == "Verified"
        assert store["audit"]["signoff_details"]["review_stages"]["bl"]["status"] == "Pending"

        # L4 approves
        app.dependency_overrides[get_current_user] = lambda: L4_USER
        assert client.post("/candidates/10482/audit/l4-review/approve", json={"remarks": "Band justified and re-approved"}).status_code == 200
        assert store["audit"]["signoff_details"]["review_stages"]["bl"]["status"] == "Approved"
        assert store["audit"]["signoff_details"].get("active_return") is None

        # L5 sanctions
        app.dependency_overrides[get_current_user] = lambda: L5_USER
        assert client.post("/candidates/10482/audit/l5-review/approve", json={"remarks": "Final executive sanction"}).status_code == 200
        assert store["audit"]["cpass_status"] == "APPROVED"
        assert store["audit"]["audit_status"] == "APPROVED"


# =============================================================================
# SCENARIO 11: Multi-Cycle Return History & Audit Trail Preservation
# =============================================================================

def test_scenario_11_multi_cycle_return_history_preservation():
    """Verify that multiple return cycles append to return_history without losing prior reasons."""
    initial_audit = {
        "id": "audit-sc-11",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "APPROVED",
        "document_audit": {"l2_review_completed": True},
        "signoff_details": {
            "review_stages": {"ch": {"status": "Recommended"}, "cops": {"status": "Verified"}, "bl": {"status": "Approved"}, "ceo": {"status": "Pending"}},
            "centre_head": {"confirmed": True, "recommended": True},
            "cops_team": {"confirmed": True},
            "business_leader": {"confirmed": True},
        },
    }
    mock_sb, store = setup_supabase_mock(initial_audit)

    with patch("app.routers.audits.supabase", mock_sb), patch("app.routers.auth.supabase", mock_sb):
        # 1. L5 returns to L4
        app.dependency_overrides[get_current_user] = lambda: L5_USER
        client.post("/candidates/10482/audit/l5-review/return", json={"destination": "L4", "return_reason": "Cycle 1: L5 to L4"})

        # 2. L4 returns to L2
        app.dependency_overrides[get_current_user] = lambda: L4_USER
        client.post("/candidates/10482/audit/l4-review/return", json={"destination": "L2", "return_reason": "Cycle 2: L4 to L2"})

        # 3. L2 returns to L1
        app.dependency_overrides[get_current_user] = lambda: L2_USER
        client.post("/candidates/10482/audit/l2-review/return-to-l1", json={"return_reason": "Cycle 3: L2 to L1"})

        # Verify return history accumulated all 3 return actions
        history = store["audit"]["signoff_details"]["return_history"]
        assert len(history) == 3
        assert history[0]["reason"] == "Cycle 1: L5 to L4"
        assert history[0]["stage"] == "CEO"
        assert history[1]["reason"] == "Cycle 2: L4 to L2"
        assert history[1]["stage"] == "BL"
        assert history[2]["reason"] == "Cycle 3: L2 to L1"
        assert history[2]["stage"] == "CH"

        # 4. L1 resubmits: return_history MUST be preserved in full
        app.dependency_overrides[get_current_user] = lambda: L1_USER
        client.post("/candidates/10482/audit/submit", json=SUBMIT_PAYLOAD)
        assert len(store["audit"]["signoff_details"]["return_history"]) == 3
        assert store["audit"]["signoff_details"].get("active_return") is None
        assert store["audit"]["signoff_details"]["last_return"]["reason"] == "Cycle 3: L2 to L1"


# =============================================================================
# SCENARIO 12: Destination and Validation Edge Cases
# =============================================================================

def test_scenario_12_destination_and_reason_validation():
    """Verify that invalid return destinations or blank reasons are rejected with HTTP 422."""
    initial_audit = {
        "id": "audit-sc-12",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "APPROVED",
        "document_audit": {"l2_review_completed": True},
        "signoff_details": {
            "review_stages": {"ch": {"status": "Recommended"}, "cops": {"status": "Verified"}, "bl": {"status": "Approved"}, "ceo": {"status": "Pending"}},
            "centre_head": {"confirmed": True, "recommended": True},
            "cops_team": {"confirmed": True},
            "business_leader": {"confirmed": True},
        },
    }
    mock_sb, store = setup_supabase_mock(initial_audit)

    with patch("app.routers.audits.supabase", mock_sb), patch("app.routers.auth.supabase", mock_sb):
        # 1. L3 cannot return to L3 or L4
        app.dependency_overrides[get_current_user] = lambda: L3_USER
        assert client.post("/candidates/10482/audit/l3-review/return", json={"destination": "L3", "return_reason": "Invalid self return"}).status_code == 422
        assert client.post("/candidates/10482/audit/l3-review/return", json={"destination": "L4", "return_reason": "Invalid forward return"}).status_code == 422
        assert client.post("/candidates/10482/audit/l3-review/return", json={"destination": "L1", "return_reason": "   "}).status_code == 422

        # 2. L4 cannot return to L4 or L5
        app.dependency_overrides[get_current_user] = lambda: L4_USER
        assert client.post("/candidates/10482/audit/l4-review/return", json={"destination": "L4", "return_reason": "Self return"}).status_code == 422
        assert client.post("/candidates/10482/audit/l4-review/return", json={"destination": "L5", "return_reason": "Forward return"}).status_code == 422
        assert client.post("/candidates/10482/audit/l4-review/return", json={"destination": "L2", "return_reason": ""}).status_code == 422

        # 3. L5 cannot return to L5
        app.dependency_overrides[get_current_user] = lambda: L5_USER
        assert client.post("/candidates/10482/audit/l5-review/return", json={"destination": "L5", "return_reason": "Self return"}).status_code == 422
        assert client.post("/candidates/10482/audit/l5-review/return", json={"destination": "INVALID", "return_reason": "Invalid dest"}).status_code == 422
        assert client.post("/candidates/10482/audit/l5-review/return", json={"destination": "L3", "return_reason": "\t \n"}).status_code == 422


# =============================================================================
# SCENARIO 13: Terminal Approval Immutability Edge Cases
# =============================================================================

def test_scenario_13_terminal_approval_cannot_be_returned():
    """Verify that a candidate with final CEO approval cannot be returned by any stage."""
    final_approved_audit = {
        "id": "audit-sc-13",
        "candidate_id": 10482,
        "audit_status": "APPROVED",
        "cpass_status": "APPROVED",
        "document_audit": {"l2_review_completed": True},
        "signoff_details": {
            "review_stages": {"ch": {"status": "Recommended"}, "cops": {"status": "Verified"}, "bl": {"status": "Approved"}, "ceo": {"status": "Approved"}},
            "centre_head": {"confirmed": True, "recommended": True},
            "cops_team": {"confirmed": True},
            "business_leader": {"confirmed": True},
            "ceo_sanction": {"confirmed": True},
        },
    }
    mock_sb, store = setup_supabase_mock(final_approved_audit)

    with patch("app.routers.audits.supabase", mock_sb), patch("app.routers.auth.supabase", mock_sb):
        # L2 return rejected
        app.dependency_overrides[get_current_user] = lambda: L2_USER
        assert client.post("/candidates/10482/audit/l2-review/return-to-l1", json={"return_reason": "Too late"}).status_code == 400

        # L3 return rejected
        app.dependency_overrides[get_current_user] = lambda: L3_USER
        assert client.post("/candidates/10482/audit/l3-review/return", json={"destination": "L1", "return_reason": "Too late"}).status_code == 400

        # L4 return rejected
        app.dependency_overrides[get_current_user] = lambda: L4_USER
        assert client.post("/candidates/10482/audit/l4-review/return", json={"destination": "L3", "return_reason": "Too late"}).status_code == 400

        # L5 return rejected
        app.dependency_overrides[get_current_user] = lambda: L5_USER
        assert client.post("/candidates/10482/audit/l5-review/return", json={"destination": "L4", "return_reason": "Too late"}).status_code == 400

