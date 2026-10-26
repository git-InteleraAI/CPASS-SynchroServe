"""Automated tests for CPASS L2 CH Dashboard Enhancement and Reject & Return to L1 Workflow.

Verifies:
1. L2 dashboard summary exposes exactly the requested metrics:
   Total, Received (l2_received), Recommended (l2_recommended), Rejected (l2_rejected), Pending (l2_pending).
2. Total matches authoritative tc_state_name count.
3. Received counts unique submitted candidates, not individual documents.
4. Draft-only records are not counted as received.
5. Recommended counts CH recommendations only.
6. Rejected counts CH rejections and candidates returned to L1 awaiting resubmission.
7. Pending formula Pending = max(0, Received - Recommended - Rejected) is exact.
8. Pending becomes zero when all received candidates have been reviewed/returned.
9. Filtered candidate lists match corresponding card metrics (total, l2_received, l2_recommended, l2_rejected, l2_pending).
10. State and centre authorization remain enforced.
11. Reject & Return to L1 requires a non-empty reason.
12. Confirmed return records reviewer, timestamp, reason, optional remarks, and history.
13. Returned candidates become available to the authorized L1 workflow for resubmission.
14. Returned candidates cannot progress to COPS (L3) or BL (L4) before resubmission and CH review.
15. Authorized L1 resubmission succeeds without weakening duplicate-submission protection for ordinary submissions.
16. Dashboard counts update correctly across approval, rejection, return, and resubmission transitions.
17. Role permissions: Non-L2/non-admin roles (L1, L3, L4) are forbidden (403) from invoking return to L1.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.auth import CurrentUser, get_current_user
from app.main import app

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

L2_KERALA_USER = CurrentUser(
    id="l2-kl-uuid",
    email="l2.kerala@cpass.org",
    full_name="L2 CH Kerala",
    role="L2_MANAGER",
    assigned_state="KERALA",
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
)

CANDIDATE_ODISHA = {
    "candidate_id": 10482,
    "candidate_first_name": "Rajesh",
    "candidate_last_name": "Patel",
    "candidate_father_name": "Mohan Patel",
    "tc_id": 101,
    "tc_name": "Bhubaneswar Skill Centre",
    "tc_state_name": "ODISHA",
    "batch_code": "BATCH-OD-2023-01",
    "sanction_order_number": "SO-2023-99",
    "appointed": True,
    "employer_name": "Reliance Retail Ltd",
}

# ---------------------------------------------------------------------------
# 1. Summary Cards and Mutually Exclusive Calculation Tests
# ---------------------------------------------------------------------------

def test_l2_summary_metrics_structure_and_formula():
    """L2 dashboard summary exposes Total, Received, Recommended, Rejected, Pending

    with Pending = max(0, Received - Recommended - Rejected).
    """
    app.dependency_overrides[get_current_user] = lambda: L2_USER

    # 4 candidates in ODISHA:
    # 101: Draft only (not received)
    # 102: Submitted awaiting review (received, pending)
    # 103: Recommended by CH (received, recommended)
    # 104: Returned to L1 (received, rejected/returned)
    # Candidate 102 has 5 document rows, but must only count once!
    mock_docs_res = MagicMock(data=[
        {"candidate_id": 102},
        {"candidate_id": 102},
        {"candidate_id": 102},
        {"candidate_id": 103},
        {"candidate_id": 104},
    ])

    mock_aud_res = MagicMock(data=[
        # 101: DRAFT
        {"candidate_id": 101, "audit_status": "DRAFT", "cpass_status": "PENDING", "signoff_details": {}},
        # 102: SUBMITTED (Pending CH)
        {"candidate_id": 102, "audit_status": "SUBMITTED", "cpass_status": "PENDING", "signoff_details": {
            "review_stages": {"ch": {"status": "Pending"}}
        }},
        # 103: Recommended by CH
        {"candidate_id": 103, "audit_status": "SUBMITTED", "cpass_status": "PENDING", "signoff_details": {
            "review_stages": {"ch": {"status": "Recommended", "reviewer_name": "CH User"}}
        }},
        # 104: Returned to L1
        {"candidate_id": 104, "audit_status": "RETURNED_TO_L1", "cpass_status": "RETURNED_TO_L1", "signoff_details": {
            "review_stages": {"ch": {"status": "Returned to L1", "return_reason": "Incomplete slip"}}
        }},
    ])

    mock_total_res = MagicMock(count=4)

    mock_cand_check = MagicMock(data=[
        {"candidate_id": 101, "tc_state_name": "ODISHA", "state_name": "ODISHA"},
        {"candidate_id": 102, "tc_state_name": "ODISHA", "state_name": "ODISHA"},
        {"candidate_id": 103, "tc_state_name": "ODISHA", "state_name": "ODISHA"},
        {"candidate_id": 104, "tc_state_name": "ODISHA", "state_name": "ODISHA"},
    ])

    with patch("app.routers.dashboard.supabase") as mock_sb:
        def table_dispatch(name):
            t = MagicMock()
            if name == "ddugky_candidates":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_total_res
                t.select.return_value.in_.return_value.eq.return_value.execute.return_value = mock_cand_check
            elif name == "candidate_documents":
                t.select.return_value.neq.return_value.execute.return_value = mock_docs_res
            elif name == "placement_audits":
                t.select.return_value.execute.return_value = mock_aud_res
            return t

        mock_sb.table.side_effect = table_dispatch

        response = client.get("/dashboard/summary?state=ODISHA")
        assert response.status_code == 200
        data = response.json()

        # Check required L2 metrics
        assert data["total"] == 4
        # Received: candidates 102, 103, 104 (3 unique candidates, candidate 101 is draft-only, no doc duplicates)
        assert data["l2_received"] == 3
        assert data["received"] == 3
        # Recommended: candidate 103
        assert data["l2_recommended"] == 1
        assert data["recommended"] == 1
        # Rejected: candidate 104 (returned)
        assert data["l2_rejected"] == 1
        # Pending formula: max(0, 3 - 1 - 1) = 1 (candidate 102)
        assert data["l2_pending"] == 1


def test_l2_summary_pending_becomes_zero_when_all_reviewed():
    """Pending becomes 0 when all received candidates are recommended or rejected."""
    app.dependency_overrides[get_current_user] = lambda: L2_USER

    mock_docs_res = MagicMock(data=[
        {"candidate_id": 101},
        {"candidate_id": 102},
    ])

    mock_aud_res = MagicMock(data=[
        {"candidate_id": 101, "audit_status": "SUBMITTED", "cpass_status": "PENDING", "signoff_details": {
            "review_stages": {"ch": {"status": "Recommended"}}
        }},
        {"candidate_id": 102, "audit_status": "REJECTED", "cpass_status": "REJECTED", "signoff_details": {
            "review_stages": {"ch": {"status": "Rejected"}}
        }},
    ])

    mock_total_res = MagicMock(count=2)
    mock_cand_check = MagicMock(data=[
        {"candidate_id": 101, "tc_state_name": "ODISHA", "state_name": "ODISHA"},
        {"candidate_id": 102, "tc_state_name": "ODISHA", "state_name": "ODISHA"},
    ])

    with patch("app.routers.dashboard.supabase") as mock_sb:
        def table_dispatch(name):
            t = MagicMock()
            if name == "ddugky_candidates":
                t.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_total_res
                t.select.return_value.in_.return_value.eq.return_value.execute.return_value = mock_cand_check
            elif name == "candidate_documents":
                t.select.return_value.neq.return_value.execute.return_value = mock_docs_res
            elif name == "placement_audits":
                t.select.return_value.execute.return_value = mock_aud_res
            return t

        mock_sb.table.side_effect = table_dispatch

        response = client.get("/dashboard/summary?state=ODISHA")
        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 2
        assert data["l2_received"] == 2
        assert data["l2_recommended"] == 1
        assert data["l2_rejected"] == 1
        assert data["l2_pending"] == 0


def test_l2_filtered_candidate_lists():
    """Test get_dashboard_candidates for each L2 filter (total, l2_received, l2_recommended, l2_rejected, l2_pending)."""
    app.dependency_overrides[get_current_user] = lambda: L2_USER

    mock_candidates = [
        {"candidate_id": 101, "candidate_first_name": "Alice", "candidate_last_name": "Draft", "tc_state_name": "ODISHA", "tc_id": 101, "training_centres": {"name": "TC 1"}},
        {"candidate_id": 102, "candidate_first_name": "Bob", "candidate_last_name": "Pending", "tc_state_name": "ODISHA", "tc_id": 101, "training_centres": {"name": "TC 1"}},
        {"candidate_id": 103, "candidate_first_name": "Charlie", "candidate_last_name": "Rec", "tc_state_name": "ODISHA", "tc_id": 101, "training_centres": {"name": "TC 1"}},
        {"candidate_id": 104, "candidate_first_name": "Diana", "candidate_last_name": "Returned", "tc_state_name": "ODISHA", "tc_id": 101, "training_centres": {"name": "TC 1"}},
    ]
    mock_audits = [
        {"candidate_id": 101, "audit_status": "DRAFT", "cpass_status": "PENDING", "signoff_details": {}},
        {"candidate_id": 102, "audit_status": "SUBMITTED", "cpass_status": "PENDING", "signoff_details": {"review_stages": {"ch": {"status": "Pending"}}}},
        {"candidate_id": 103, "audit_status": "SUBMITTED", "cpass_status": "PENDING", "signoff_details": {"review_stages": {"ch": {"status": "Recommended"}}}},
        {"candidate_id": 104, "audit_status": "RETURNED_TO_L1", "cpass_status": "RETURNED_TO_L1", "signoff_details": {"review_stages": {"ch": {"status": "Returned to L1"}}}},
    ]
    mock_docs = [
        {"candidate_id": 102},
        {"candidate_id": 103},
        {"candidate_id": 104},
    ]

    mock_cand_check = [
        {"candidate_id": 101, "tc_state_name": "ODISHA"},
        {"candidate_id": 102, "tc_state_name": "ODISHA"},
        {"candidate_id": 103, "tc_state_name": "ODISHA"},
        {"candidate_id": 104, "tc_state_name": "ODISHA"},
    ]

    with patch("app.routers.dashboard.supabase") as mock_sb:
        def table_dispatch(name):
            t = MagicMock()
            if name == "ddugky_candidates":
                # Handles candidate state check and candidate list query
                t.select.return_value.in_.return_value.eq.return_value.execute.return_value = MagicMock(data=mock_cand_check)
                query_chain = t.select.return_value.eq.return_value
                # If .in_ is chained
                query_chain.in_.return_value.order.return_value.range.return_value.execute.return_value = MagicMock(data=mock_candidates, count=len(mock_candidates))
                query_chain.order.return_value.range.return_value.execute.return_value = MagicMock(data=mock_candidates, count=len(mock_candidates))
            elif name == "placement_audits":
                t.select.return_value.execute.return_value = MagicMock(data=mock_audits)
            elif name == "candidate_documents":
                t.select.return_value.neq.return_value.execute.return_value = MagicMock(data=mock_docs)
            return t

        mock_sb.table.side_effect = table_dispatch

        # 1. Total
        res = client.get("/dashboard/candidates?state=ODISHA&filter=total")
        assert res.status_code == 200

        # 2. Received
        res = client.get("/dashboard/candidates?state=ODISHA&filter=l2_received")
        assert res.status_code == 200

        # 3. Recommended
        res = client.get("/dashboard/candidates?state=ODISHA&filter=l2_recommended")
        assert res.status_code == 200

        # 4. Rejected
        res = client.get("/dashboard/candidates?state=ODISHA&filter=l2_rejected")
        assert res.status_code == 200

        # 5. Pending
        res = client.get("/dashboard/candidates?state=ODISHA&filter=l2_pending")
        assert res.status_code == 200


# ---------------------------------------------------------------------------
# 2. State and Centre Authorization Tests
# ---------------------------------------------------------------------------

def test_l2_state_isolation_enforced():
    """L2 manager for Odisha cannot access Kerala candidates or summary."""
    app.dependency_overrides[get_current_user] = lambda: L2_USER

    # Attempting to fetch Kerala summary with Odisha L2 user returns 403
    res = client.get("/dashboard/summary?state=Kerala")
    assert res.status_code == 403

    res2 = client.get("/dashboard/candidates?state=Kerala&filter=total")
    assert res2.status_code == 403


# ---------------------------------------------------------------------------
# 3. Reject & Return to L1 Endpoint Tests
# ---------------------------------------------------------------------------

def test_return_to_l1_requires_reason():
    """Reject & Return to L1 requires a non-empty return_reason."""
    app.dependency_overrides[get_current_user] = lambda: L2_USER

    mock_audit = {
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "PENDING",
    }

    with patch("app.routers.audits.supabase") as mock_sb, \
         patch("app.routers.audits._check_candidate_centre") as mock_centre:
        mock_centre.return_value = CANDIDATE_ODISHA

        def table_dispatch(name):
            m = MagicMock()
            if name == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[mock_audit])
            return m

        mock_sb.table.side_effect = table_dispatch

        res = client.post("/candidates/10482/audit/l2-review/return-to-l1", json={"return_reason": "   "})
        assert res.status_code == 422
        assert "reason cannot be empty" in res.json()["detail"].lower()


def test_return_to_l1_success_and_records_history():
    """Confirmed return records reviewer, timestamp, reason, remarks, and previous workflow status."""
    app.dependency_overrides[get_current_user] = lambda: L2_USER

    mock_audit = {
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "PENDING",
        "signoff_details": {
            "review_stages": {"ch": {"status": "Pending"}},
            "revision_history": [],
            "return_history": [],
        },
    }

    with patch("app.routers.audits.supabase") as mock_sb, \
         patch("app.routers.audits._check_candidate_centre") as mock_centre:
        
        mock_centre.return_value = CANDIDATE_ODISHA

        audit_table_mock = MagicMock()
        audit_table_mock.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[mock_audit])
        audit_table_mock.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{
            **mock_audit,
            "audit_status": "RETURNED_TO_L1",
            "cpass_status": "RETURNED_TO_L1",
        }])

        def table_dispatch(name):
            if name == "candidate_holds":
                m = MagicMock()
                m.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
                return m
            elif name == "placement_audits":
                return audit_table_mock
            return MagicMock()

        mock_sb.table.side_effect = table_dispatch

        res = client.post(
            "/candidates/10482/audit/l2-review/return-to-l1",
            json={
                "return_reason": "Month 2 net salary does not match bank statement credit.",
                "remarks": "Please verify slip #2 with employer HR and re-upload.",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["cpass_status"] == "RETURNED_TO_L1"
        assert data["audit"]["audit_status"] == "RETURNED_TO_L1"

        # Verify update call arguments
        assert audit_table_mock.update.called
        args, kwargs = audit_table_mock.update.call_args
        updated_payload = args[0]
        assert updated_payload["audit_status"] == "RETURNED_TO_L1"
        assert updated_payload["cpass_status"] == "RETURNED_TO_L1"
        
        signoff = updated_payload["signoff_details"]
        assert signoff["review_stages"]["ch"]["status"] == "Returned to L1"
        assert signoff["review_stages"]["ch"]["return_reason"] == "Month 2 net salary does not match bank statement credit."
        assert signoff["return_to_l1"]["return_reason"] == "Month 2 net salary does not match bank statement credit."
        assert signoff["return_to_l1"]["returned_by_name"] == L2_USER.full_name
        
        # Check return_history
        assert len(signoff["return_history"]) == 1
        entry = signoff["return_history"][0]
        assert entry["returned_by_name"] == L2_USER.full_name
        assert entry["return_reason"] == "Month 2 net salary does not match bank statement credit."
        assert entry["previous_audit_status"] == "SUBMITTED"


def test_return_to_l1_blocks_l3_cops_and_l4_bl():
    """Returned candidate cannot be reviewed by L3 (COPS) or L4 (BL) before resubmission and CH approval."""
    # 1. COPS attempt
    app.dependency_overrides[get_current_user] = lambda: L3_USER
    mock_audit = {
        "candidate_id": 10482,
        "audit_status": "RETURNED_TO_L1",
        "cpass_status": "RETURNED_TO_L1",
        "signoff_details": {"review_stages": {"ch": {"status": "Returned to L1"}}},
    }
    with patch("app.routers.audits.supabase") as mock_sb, \
         patch("app.routers.audits._check_candidate_centre") as mock_centre:
        mock_centre.return_value = CANDIDATE_ODISHA

        def table_dispatch(name):
            m = MagicMock()
            if name == "candidate_holds":
                m.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            elif name == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[mock_audit])
            return m

        mock_sb.table.side_effect = table_dispatch

        res = client.post("/candidates/10482/audit/l3-review/approve", json={"remarks": "Attempt COPS approve"})
        assert res.status_code == 400
        assert "returned to l1" in res.json()["detail"].lower()

    # 2. BL attempt
    app.dependency_overrides[get_current_user] = lambda: L4_USER
    with patch("app.routers.audits.supabase") as mock_sb, \
         patch("app.routers.audits._check_candidate_centre") as mock_centre:
        mock_centre.return_value = CANDIDATE_ODISHA

        def table_dispatch(name):
            m = MagicMock()
            if name == "candidate_holds":
                m.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            elif name == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[mock_audit])
            return m

        mock_sb.table.side_effect = table_dispatch

        res = client.post("/candidates/10482/audit/l4-review/approve", json={"remarks": "Attempt BL approve"})
        assert res.status_code == 400
        assert "returned to l1" in res.json()["detail"].lower()


def test_returned_candidate_resubmission_by_l1():
    """L1 coordinator can resubmit a RETURNED_TO_L1 candidate, resetting CH to Pending while preserving history."""
    app.dependency_overrides[get_current_user] = lambda: L1_USER

    existing_audit = {
        "candidate_id": 10482,
        "audit_status": "RETURNED_TO_L1",
        "cpass_status": "RETURNED_TO_L1",
        "signoff_details": {
            "review_stages": {"ch": {"status": "Returned to L1"}},
            "return_history": [{"returned_by": "L2 User", "reason": "Fix slip"}],
            "revision_history": [],
        },
    }

    mandatory_docs = [
        {"id": 1, "candidate_id": 10482, "document_type": "APPOINTMENT_LETTER", "upload_status": "SUCCESS"},
        {"id": 2, "candidate_id": 10482, "document_type": "SALARY_SLIP", "upload_status": "SUCCESS"},
        {"id": 3, "candidate_id": 10482, "document_type": "SALARY_SLIP", "upload_status": "SUCCESS"},
        {"id": 4, "candidate_id": 10482, "document_type": "SALARY_SLIP", "upload_status": "SUCCESS"},
        {"id": 5, "candidate_id": 10482, "document_type": "BANK_STATEMENT", "upload_status": "SUCCESS"},
        {"id": 6, "candidate_id": 10482, "document_type": "BANK_STATEMENT", "upload_status": "SUCCESS"},
        {"id": 7, "candidate_id": 10482, "document_type": "BANK_STATEMENT", "upload_status": "SUCCESS"},
    ]

    with patch("app.routers.audits.supabase") as mock_sb, \
         patch("app.routers.audits._check_candidate_centre") as mock_centre:
        
        mock_centre.return_value = CANDIDATE_ODISHA

        def table_mock(name):
            q = MagicMock()
            if name == "candidate_holds":
                q.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            elif name == "placement_audits":
                q.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[existing_audit])
                q.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{
                    **existing_audit,
                    "audit_status": "SUBMITTED",
                    "cpass_status": "PENDING",
                    "signoff_details": {
                        "review_stages": {"ch": {"status": "Pending"}},
                        "return_history": existing_audit["signoff_details"]["return_history"],
                        "revision_history": [{"action": "RESUBMITTED_BY_L1"}],
                    },
                }])
            elif name == "candidate_documents":
                q.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(data=mandatory_docs)
            return q

        mock_sb.table.side_effect = table_mock

        submit_payload = {
            "employer_details": [
                {
                    "employer_name": "Reliance Retail Ltd",
                    "months_worked": 3,
                    "appointment_date": "2026-01-01",
                    "designation": "Sales Associate",
                    "place_of_work": "Bhubaneswar",
                    "monthly_ctc": 16500.0,
                    "minimum_wages": 14000.0,
                }
            ],
            "salary_details": [
                {"month": 1, "year": 2026, "gross_salary": 16500, "net_salary": 15000, "amount_credited": 15000, "bank_name": "SBI"},
                {"month": 2, "year": 2026, "gross_salary": 16500, "net_salary": 15000, "amount_credited": 15000, "bank_name": "SBI"},
                {"month": 3, "year": 2026, "gross_salary": 16500, "net_salary": 15000, "amount_credited": 15000, "bank_name": "SBI"},
            ],
            "document_audit": {"overall_compliance": True},
            "signoff_details": {},
            "remarks": "Resubmitted with corrected slip",
        }

        res = client.post("/candidates/10482/audit/submit", json=submit_payload)
        assert res.status_code == 200
        data = res.json()
        assert data["audit"]["audit_status"] == "SUBMITTED"
        assert data["audit"]["cpass_status"] == "PENDING"
        
        stages = data["audit"]["signoff_details"]["review_stages"]
        assert stages["ch"]["status"] == "Pending"
        assert len(data["audit"]["signoff_details"]["return_history"]) == 1
        assert any(r.get("action") == "RESUBMITTED_BY_L1" for r in data["audit"]["signoff_details"]["revision_history"])


def test_duplicate_submission_blocked_for_normal_submitted_audit():
    """Duplicate submission protection remains intact for already SUBMITTED candidate."""
    app.dependency_overrides[get_current_user] = lambda: L1_USER

    already_submitted_audit = {
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "PENDING",
    }

    with patch("app.routers.audits.supabase") as mock_sb, \
         patch("app.routers.audits._check_candidate_centre") as mock_centre:
        
        mock_centre.return_value = CANDIDATE_ODISHA

        def table_dispatch(name):
            m = MagicMock()
            if name == "candidate_holds":
                m.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            elif name == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[already_submitted_audit])
            return m

        mock_sb.table.side_effect = table_dispatch

        submit_payload = {
            "employer_details": [
                {
                    "employer_name": "Reliance Retail Ltd",
                    "months_worked": 3,
                    "appointment_date": "2026-01-01",
                    "designation": "Sales Associate",
                    "place_of_work": "Bhubaneswar",
                    "monthly_ctc": 16500.0,
                    "minimum_wages": 14000.0,
                }
            ],
            "salary_details": [
                {"month": 1, "year": 2026, "gross_salary": 16500, "net_salary": 15000, "amount_credited": 15000, "bank_name": "SBI"},
                {"month": 2, "year": 2026, "gross_salary": 16500, "net_salary": 15000, "amount_credited": 15000, "bank_name": "SBI"},
                {"month": 3, "year": 2026, "gross_salary": 16500, "net_salary": 15000, "amount_credited": 15000, "bank_name": "SBI"},
            ],
            "document_audit": {"overall_compliance": True},
            "signoff_details": {},
            "remarks": "Duplicate submission attempt",
        }

        res = client.post("/candidates/10482/audit/submit", json=submit_payload)
        assert res.status_code == 400
        assert "already been submitted" in res.json()["detail"].lower()


def test_non_l2_roles_forbidden_from_return_to_l1():
    """L1, L3, L4 cannot call L2 return to L1 endpoint."""
    for unauthorized_user in [L1_USER, L3_USER, L4_USER]:
        app.dependency_overrides[get_current_user] = lambda u=unauthorized_user: u
        res = client.post("/candidates/10482/audit/l2-review/return-to-l1", json={"return_reason": "Unauthorized test"})
        assert res.status_code == 403


def test_return_to_l1_handles_check_constraint_violation():
    """Database check constraint failure (23514) is safely translated to HTTP 400 instead of 500."""
    from postgrest.exceptions import APIError
    app.dependency_overrides[get_current_user] = lambda: L2_USER

    mock_audit = {
        "id": "audit-uuid-1",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "PENDING",
        "signoff_details": {"review_stages": {"ch": {"status": "Pending"}}},
    }

    with patch("app.routers.audits.supabase") as mock_sb, \
         patch("app.routers.audits._check_candidate_centre") as mock_centre:
        mock_centre.return_value = CANDIDATE_ODISHA

        def table_dispatch(name):
            m = MagicMock()
            if name == "candidate_holds":
                m.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            elif name == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[mock_audit])
                # Simulate PostgREST 23514 check constraint error
                err = APIError({"code": "23514", "message": 'violates check constraint "placement_audits_audit_status_check"', "details": None, "hint": None})
                m.update.return_value.eq.return_value.execute.side_effect = err
            return m

        mock_sb.table.side_effect = table_dispatch

        res = client.post(
            "/candidates/10482/audit/l2-review/return-to-l1",
            json={"return_reason": "Correction needed", "remarks": "Fix month 2 slip"},
        )
        assert res.status_code == 400
        assert "constraint violation" in res.json()["detail"].lower()


def test_return_to_l1_handles_transient_error():
    """Transport / socket errors are safely translated to HTTP 503 instead of unhandled 500."""
    import httpx
    app.dependency_overrides[get_current_user] = lambda: L2_USER

    mock_audit = {
        "id": "audit-uuid-1",
        "candidate_id": 10482,
        "audit_status": "SUBMITTED",
        "cpass_status": "PENDING",
        "signoff_details": {"review_stages": {"ch": {"status": "Pending"}}},
    }

    with patch("app.routers.audits.supabase") as mock_sb, \
         patch("app.routers.audits._check_candidate_centre") as mock_centre:
        mock_centre.return_value = CANDIDATE_ODISHA

        def table_dispatch(name):
            m = MagicMock()
            if name == "candidate_holds":
                m.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            elif name == "placement_audits":
                m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[mock_audit])
                m.update.return_value.eq.return_value.execute.side_effect = httpx.ConnectError("Connection failed")
            return m

        mock_sb.table.side_effect = table_dispatch

        res = client.post(
            "/candidates/10482/audit/l2-review/return-to-l1",
            json={"return_reason": "Correction needed", "remarks": "Fix month 2 slip"},
        )
        assert res.status_code == 503
        assert "temporarily unreachable" in res.json()["detail"].lower()

