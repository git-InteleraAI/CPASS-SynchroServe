"""Tests for Duplicate Review Router & Authorization (Phase 2).

Verifies role permissions, centre scoping, mandatory reason validation for consequential
review decisions, non-destructive behavior, warning vs hold semantics, and hold placement/release lifecycle.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.auth import CurrentUser, get_current_user
from app.main import app

client = TestClient(app)


@pytest.fixture
def mock_supabase():
    with patch("app.routers.duplicates.supabase") as mock_sb:
        yield mock_sb


def test_consequential_decision_requires_mandatory_reason(mock_supabase):
    """Transitioning to CONFIRMED_DUPLICATE without a reason must fail with 422."""
    admin_user = CurrentUser(id="admin-uuid", email="admin@cpass.org", full_name="Admin User", role="ADMIN")
    app.dependency_overrides[get_current_user] = lambda: admin_user

    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"id": "case-123", "status": "PENDING", "tc_id": 10}
    ]

    try:
        response = client.post(
            "/duplicates/cases/case-123/review",
            json={
                "to_status": "CONFIRMED_DUPLICATE",
                "decision": "Confirmed after document verification",
                "reason": "   ",  # Whitespace only
            },
        )
        assert response.status_code == 422
        assert "mandatory non-empty reason is required" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_l1_cannot_make_consequential_decision(mock_supabase):
    """L1 coordinator attempting a consequential review decision must receive 403."""
    l1_user = CurrentUser(id="l1-uuid", email="l1@cpass.org", full_name="L1 User", role="L1_COORDINATOR")
    app.dependency_overrides[get_current_user] = lambda: l1_user

    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"id": "case-123", "status": "PENDING", "tc_id": 10}
    ]

    # User assigned to TC 10
    with patch("app.routers.duplicates.allowed_tc_ids", return_value=[10]):
        try:
            response = client.post(
                "/duplicates/cases/case-123/review",
                json={
                    "to_status": "CONFIRMED_DUPLICATE",
                    "decision": "Marking confirmed",
                    "reason": "Looks the same to me",
                },
            )
            assert response.status_code == 403
            assert "cannot make consequential duplicate review decisions" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()


def test_centre_scoping_enforced(mock_supabase):
    """User not assigned to the case's centre must be rejected with 403."""
    l2_user = CurrentUser(id="l2-uuid", email="l2@cpass.org", full_name="L2 User", role="L2_MANAGER")
    app.dependency_overrides[get_current_user] = lambda: l2_user

    # Case belongs to TC 99, but user only has access to TC 10
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"id": "case-99", "status": "PENDING", "tc_id": 99}
    ]

    with patch("app.routers.duplicates.allowed_tc_ids", return_value=[10]):
        try:
            response = client.get("/duplicates/cases/case-99")
            assert response.status_code == 403
            assert "do not have access to this training centre" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()


def test_successful_review_records_history_and_preserves_candidates(mock_supabase):
    """Authorized review decision records audit history and never modifies candidate records."""
    l2_user = CurrentUser(id="l2-uuid", email="l2@cpass.org", full_name="L2 User", role="L2_MANAGER")
    app.dependency_overrides[get_current_user] = lambda: l2_user

    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"id": "case-123", "status": "PENDING", "tc_id": 10}
    ]

    with patch("app.routers.duplicates.allowed_tc_ids", return_value=[10]):
        try:
            response = client.post(
                "/duplicates/cases/case-123/review",
                json={
                    "to_status": "DISTINCT_CANDIDATES",
                    "decision": "Verified physical IDs",
                    "reason": "Examined Aadhaar cards; two distinct cousins with the same name.",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["to_status"] == "DISTINCT_CANDIDATES"
            assert data["preserved_candidates"] is True

            # Verify duplicate_review_history insert was invoked
            insert_calls = [
                call for call in mock_supabase.table.mock_calls if "duplicate_review_history" in str(call)
            ]
            assert len(insert_calls) > 0

            # Verify candidates table was NEVER called for delete, merge, or update
            cand_calls = [
                call for call in mock_supabase.table.mock_calls if "candidates" in str(call) and ("delete" in str(call) or "update" in str(call))
            ]
            assert len(cand_calls) == 0
        finally:
            app.dependency_overrides.clear()


def test_warning_alone_does_not_block_submission(mock_supabase):
    """Unresolved duplicate case produces a warning but can_submit remains True."""
    user = CurrentUser(id="coord-uuid", email="c@cpass.org", full_name="Coordinator", role="L1_COORDINATOR")
    app.dependency_overrides[get_current_user] = lambda: user

    with patch("app.routers.duplicates.allowed_tc_ids", return_value=None), patch(
        "app.routers.duplicates._get_candidate_tc_id", return_value=10
    ):
        # Case member returns 1 unresolved case
        mock_members = MagicMock()
        mock_members.execute.return_value.data = [
            {"case_id": "case-1", "duplicate_cases": {"id": "case-1", "status": "PENDING"}}
        ]

        # Hold returns no active hold
        mock_holds = MagicMock()
        mock_holds.execute.return_value.data = []

        def side_effect(table_name):
            tbl = MagicMock()
            if table_name == "duplicate_case_members":
                tbl.select.return_value.eq.return_value.in_.return_value = mock_members
            elif table_name == "candidate_holds":
                tbl.select.return_value.eq.return_value.eq.return_value = mock_holds
            return tbl

        mock_supabase.table.side_effect = side_effect

        try:
            response = client.get("/duplicates/candidates/1001/status")
            assert response.status_code == 200
            res = response.json()
            assert res["has_duplicate_warning"] is True
            assert res["unresolved_cases_count"] == 1
            assert res["has_active_hold"] is False
            # Crucial requirement: Warning alone must not block submission!
            assert res["can_submit"] is True
        finally:
            app.dependency_overrides.clear()


def test_submission_hold_placement_and_release(mock_supabase):
    """Authorized manager places and releases submission hold with mandatory reasons."""
    l2_user = CurrentUser(id="l2-uuid", email="l2@cpass.org", full_name="L2 User", role="L2_MANAGER")
    app.dependency_overrides[get_current_user] = lambda: l2_user

    with patch("app.routers.duplicates.allowed_tc_ids", return_value=[10]), patch(
        "app.routers.duplicates._get_candidate_tc_id", return_value=10
    ):
        try:
            # 1. Place hold
            mock_insert = MagicMock()
            mock_insert.execute.return_value.data = [{"id": "hold-1", "is_active": True}]
            mock_supabase.table.return_value.insert.return_value = mock_insert

            res_hold = client.post(
                "/duplicates/candidates/1001/hold",
                json={"reason": "Suspected duplicate identity undergoing investigation"},
            )
            assert res_hold.status_code == 200
            assert res_hold.json()["can_submit"] is False

            # 2. Release hold
            mock_active = MagicMock()
            mock_active.execute.return_value.data = [{"id": "hold-1"}]
            mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value = mock_active

            res_rel = client.post(
                "/duplicates/candidates/1001/release-hold",
                json={"reason": "Identity verified with physical biometric scan. Candidate cleared."},
            )
            assert res_rel.status_code == 200
            assert res_rel.json()["can_submit"] is True
        finally:
            app.dependency_overrides.clear()


def test_unauthorized_user_cannot_place_hold(mock_supabase):
    """L1 coordinator cannot place holds."""
    l1_user = CurrentUser(id="l1-uuid", email="l1@cpass.org", full_name="L1 User", role="L1_COORDINATOR")
    app.dependency_overrides[get_current_user] = lambda: l1_user

    try:
        response = client.post(
            "/duplicates/candidates/1001/hold",
            json={"reason": "I think this candidate is duplicated"},
        )
        assert response.status_code == 403
        assert "not authorized to place submission holds" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_missing_candidate_returns_404(mock_supabase):
    """Requesting hold for non-existent candidate returns 404."""
    admin_user = CurrentUser(id="admin-uuid", email="admin@cpass.org", full_name="Admin User", role="ADMIN")
    app.dependency_overrides[get_current_user] = lambda: admin_user

    # Candidates table returns no record
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []

    try:
        response = client.post(
            "/duplicates/candidates/999999/hold",
            json={"reason": "Attempting hold on non-existent candidate"},
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_cross_centre_case_access_rejected_for_unrelated_user(mock_supabase):
    """Case with tc_id=None where user belongs to none of the member candidate centres returns 403."""
    l2_user = CurrentUser(id="l2-uuid", email="l2@cpass.org", full_name="L2 User", role="L2_MANAGER")
    app.dependency_overrides[get_current_user] = lambda: l2_user

    # Case has no tc_id (cross-centre)
    case_data = {"id": "case-cross", "status": "PENDING", "tc_id": None}
    # Members belong to TC 50 and TC 60, but user only has TC 10
    members_data = [
        {"candidate_id": 1, "candidates": {"batches": {"tc_id": 50}}},
        {"candidate_id": 2, "candidates": {"batches": {"tc_id": 60}}},
    ]

    def mock_table(table_name):
        tbl = MagicMock()
        if table_name == "duplicate_cases":
            tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [case_data]
        elif table_name == "duplicate_case_members":
            tbl.select.return_value.eq.return_value.execute.return_value.data = members_data
        return tbl

    mock_supabase.table.side_effect = mock_table

    with patch("app.routers.duplicates.allowed_tc_ids", return_value=[10]):
        try:
            response = client.get("/duplicates/cases/case-cross")
            assert response.status_code == 403
            assert "do not have access to any training centres" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()

