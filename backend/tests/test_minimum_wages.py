"""Comprehensive test suite for CPASS State-wise Minimum Wage Auto-Fetch.

Validates:
1. Excel workbook data integrity (455 records, 13 states, 35 effective periods).
2. Effective-date lookup logic (latest revision on or before salary period):
   - Punjab Nov 2026 -> Oct 2026 revision (16,800)
   - Punjab Feb 2026 -> Oct 2025 revision (16,400)
   - Andhra Pradesh May 2026 -> April 2026 revision (16,100)
   - Telangana Nov 2026 -> Oct 2026 revision (16,300)
   - Kerala Oct 2026 -> Oct 2026 revision (18,900)
   - Pre-2010 salary period -> None / 404
   - Invalid month and year validation (ValueError / 400)
3. API endpoints & Candidate state resolution:
   - get_minimum_wage / lookup_minimum_wage_endpoint
   - Candidate state and training centre authorization enforcement (403 for unauthorized users)
   - Missing beneficiary state (400 validation error)
4. Security & authoritative recalculation:
   - Draft save independently populates authoritative minimum wage
   - Final submission strictly enforces and overwrites client-tampered wages
   - L2 corrections recalculate wages authoritatively
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException

from app.auth import CurrentUser
from app.routers.audits import (
    EmployerEntry,
    L2CorrectionsRequest,
    SalaryEntry,
    SaveAuditDraftRequest,
    SubmitAuditRequest,
    get_minimum_wage,
    lookup_minimum_wage_endpoint,
    save_audit_draft,
    save_l2_corrections,
    submit_audit,
)
from app.services.min_wages import (
    apply_authoritative_minimum_wages,
    lookup_minimum_wage_for_period,
)
from scripts.import_min_wages import parse_workbook, validate_records

L1_PUNJAB_USER = CurrentUser(
    id="l1-punjab-uuid",
    email="pbpe@synchroserve.com",
    full_name="Punjab Coordinator",
    role="L1_COORDINATOR",
    assigned_state="PUNJAB",
    assigned_states=["PUNJAB"],
)

L1_ODISHA_USER = CurrentUser(
    id="l1-odisha-uuid",
    email="odpe@synchroserve.com",
    full_name="Odisha Coordinator",
    role="L1_COORDINATOR",
    assigned_state="ODISHA",
    assigned_states=["ODISHA"],
)

L2_PUNJAB_USER = CurrentUser(
    id="l2-punjab-uuid",
    email="pbch@synchroserve.com",
    full_name="Punjab Centre Head",
    role="L2_MANAGER",
    assigned_state="PUNJAB",
    assigned_states=["PUNJAB"],
)

ADMIN_USER = CurrentUser(
    id="admin-uuid",
    email="admin@cpass.org",
    full_name="Admin User",
    role="ADMIN",
)

PUNJAB_CANDIDATE = {
    "candidate_id": 88001,
    "candidate_first_name": "Gurpreet",
    "candidate_last_name": "Singh",
    "state_name": "PUNJAB",
    "tc_id": 501,
    "tc_name": "Ludhiana Training Centre",
    "appointed": True,
}

ANDHRA_CANDIDATE = {
    "candidate_id": 88002,
    "candidate_first_name": "Venkatesh",
    "candidate_last_name": "Rao",
    "state_name": "ANDHRA PRADESH",
    "tc_id": 502,
    "tc_name": "Vijayawada Centre",
    "appointed": True,
}


@pytest.fixture(autouse=True)
def mock_all_db():
    """Mock database access across all modules to ensure zero-network, ultra-fast test execution."""
    mock_sb = MagicMock()

    def table_side_effect(tbl):
        m = MagicMock()
        if tbl in ("ddugky_candidates", "candidates"):
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[PUNJAB_CANDIDATE])
        elif tbl == "user_centres":
            m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"tc_id": 501}])
        elif tbl == "placement_audits":
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[{"id": "audit-uuid-1", "candidate_id": 88001, "audit_status": "DRAFT", "signoff_details": {}}]
            )
            m.insert.return_value.execute.return_value = MagicMock(data=[{"id": "audit-uuid-1", "audit_status": "SUBMITTED"}])
            m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "audit-uuid-1"}])
        elif tbl == "candidate_holds":
            m.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        elif tbl == "candidate_documents":
            m.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(
                data=[
                    {"document_type": "APPOINTMENT_LETTER", "employer_id": "emp_1", "upload_status": "SUCCESS"},
                    {"document_type": "SALARY_SLIP", "employer_id": "emp_1", "reporting_month": 10, "reporting_year": 2026, "upload_status": "SUCCESS"},
                    {"document_type": "SALARY_SLIP", "employer_id": "emp_1", "reporting_month": 11, "reporting_year": 2026, "upload_status": "SUCCESS"},
                    {"document_type": "SALARY_SLIP", "employer_id": "emp_1", "reporting_month": 12, "reporting_year": 2026, "upload_status": "SUCCESS"},
                    {"document_type": "BANK_STATEMENT", "employer_id": "emp_1", "is_consolidated": True, "coverage_start_month": 10, "coverage_start_year": 2026, "coverage_end_month": 12, "coverage_end_year": 2026, "covered_months": [{"month": 10, "year": 2026}, {"month": 11, "year": 2026}, {"month": 12, "year": 2026}], "upload_status": "SUCCESS"},
                ]
            )
        return m

    mock_sb.table.side_effect = table_side_effect
    with patch("app.db.supabase", mock_sb), \
         patch("app.auth.supabase", mock_sb), \
         patch("app.routers.audits.supabase", mock_sb), \
         patch("app.services.min_wages.supabase", mock_sb):
        yield mock_sb


# =============================================================================
# 1. Excel Workbook Data Tests
# =============================================================================

def test_excel_workbook_455_records_and_validation():
    """Verify all 455 records, 13 states, 35 periods from main register."""
    project_root = Path(__file__).resolve().parents[2]
    excel_path = project_root / "Minimum_Wages_Semi_Skilled_2010_2026.xlsx"
    records = parse_workbook(excel_path)
    assert len(records) == 455

    summary = validate_records(records)
    assert summary["total_records"] == 455
    assert summary["distinct_states"] == 13
    assert summary["distinct_periods"] == 35
    assert summary["earliest_date"] == "2010-01-01"
    assert summary["latest_date"] == "2026-10-01"
    assert summary["min_wage"] == 2780.0
    assert summary["max_wage"] == 18900.0

    expected_states = {
        "ANDHRA PRADESH", "BIHAR", "GUJARAT", "KERALA", "MIZORAM",
        "ODISHA", "PUDUCHERRY", "PUNJAB", "RAJASTHAN", "TAMIL NADU",
        "TELANGANA", "UTTAR PRADESH", "WEST BENGAL",
    }
    assert set(summary["states"]) == expected_states


# =============================================================================
# 2. Minimum Wage Service Lookup Unit Tests
# =============================================================================

def make_db_records():
    """Sample realistic revisions for unit testing."""
    return [
        {"state": "PUNJAB", "month": 10, "year": 2026, "effective_date": "2026-10-01", "minimum_wage": 16800.0, "skill_category": "SEMI-SKILLED"},
        {"state": "PUNJAB", "month": 4, "year": 2026, "effective_date": "2026-04-01", "minimum_wage": 16600.0, "skill_category": "SEMI-SKILLED"},
        {"state": "PUNJAB", "month": 10, "year": 2025, "effective_date": "2025-10-01", "minimum_wage": 16400.0, "skill_category": "SEMI-SKILLED"},
        {"state": "ANDHRA PRADESH", "month": 4, "year": 2026, "effective_date": "2026-04-01", "minimum_wage": 16100.0, "skill_category": "SEMI-SKILLED"},
        {"state": "ANDHRA PRADESH", "month": 10, "year": 2025, "effective_date": "2025-10-01", "minimum_wage": 15800.0, "skill_category": "SEMI-SKILLED"},
        {"state": "TELANGANA", "month": 10, "year": 2026, "effective_date": "2026-10-01", "minimum_wage": 16300.0, "skill_category": "SEMI-SKILLED"},
        {"state": "KERALA", "month": 10, "year": 2026, "effective_date": "2026-10-01", "minimum_wage": 18900.0, "skill_category": "SEMI-SKILLED"},
        {"state": "ODISHA", "month": 1, "year": 2010, "effective_date": "2010-01-01", "minimum_wage": 2780.0, "skill_category": "SEMI-SKILLED"},
    ]


def test_effective_date_lookup_scenarios():
    """Verify effective date rule: effective_date <= requested period, ordered by date DESC."""
    all_recs = make_db_records()

    def mock_query(tbl):
        m = MagicMock()
        def mock_select(*args, **kwargs):
            sel_mock = MagicMock()
            def mock_eq_state(col, val):
                eq1_mock = MagicMock()
                def mock_eq_skill(col2, val2):
                    eq2_mock = MagicMock()
                    def mock_lte(col3, target_date):
                        lte_mock = MagicMock()
                        def mock_order(col4, desc=True):
                            ord_mock = MagicMock()
                            def mock_limit(n):
                                lim_mock = MagicMock()
                                matching = [
                                    r for r in all_recs
                                    if r["state"] == val and r["effective_date"] <= target_date
                                ]
                                matching.sort(key=lambda x: x["effective_date"], reverse=desc)
                                lim_mock.execute.return_value = MagicMock(data=matching[:n])
                                return lim_mock
                            ord_mock.limit.side_effect = mock_limit
                            return ord_mock
                        lte_mock.order.side_effect = mock_order
                        return lte_mock
                    eq2_mock.lte.side_effect = mock_lte
                    return eq2_mock
                eq1_mock.eq.side_effect = mock_eq_skill
                return eq1_mock
            sel_mock.eq.side_effect = mock_eq_state
            return sel_mock
        m.select.side_effect = mock_select
        return m

    mock_sb = MagicMock()
    mock_sb.table.side_effect = mock_query

    with patch("app.services.min_wages.supabase", mock_sb):
        # 1. Punjab - November 2026 -> Oct 2026 revision (16,800)
        res1 = lookup_minimum_wage_for_period("PUNJAB", 11, 2026)
        assert res1 is not None
        assert res1["minimum_wage"] == 16800.0
        assert res1["effective_month"] == 10
        assert res1["effective_year"] == 2026

        # 2. Punjab - February 2026 -> Oct 2025 revision (16,400)
        res2 = lookup_minimum_wage_for_period("PUNJAB", 2, 2026)
        assert res2 is not None
        assert res2["minimum_wage"] == 16400.0
        assert res2["effective_month"] == 10
        assert res2["effective_year"] == 2025

        # 3. Andhra Pradesh - May 2026 -> April 2026 revision (16,100)
        res3 = lookup_minimum_wage_for_period("ANDHRA PRADESH", 5, 2026)
        assert res3 is not None
        assert res3["minimum_wage"] == 16100.0
        assert res3["effective_month"] == 4
        assert res3["effective_year"] == 2026

        # 4. Telangana - November 2026 -> Oct 2026 revision (16,300)
        res4 = lookup_minimum_wage_for_period("TELANGANA", 11, 2026)
        assert res4 is not None
        assert res4["minimum_wage"] == 16300.0
        assert res4["effective_month"] == 10
        assert res4["effective_year"] == 2026

        # 5. Kerala - October 2026 -> Oct 2026 revision (18,900)
        res5 = lookup_minimum_wage_for_period("KERALA", 10, 2026)
        assert res5 is not None
        assert res5["minimum_wage"] == 18900.0

        # 6. Period before earliest available record (December 2009 for Odisha)
        res6 = lookup_minimum_wage_for_period("ODISHA", 12, 2009)
        assert res6 is None

        # 7. Invalid month validation
        with pytest.raises(ValueError, match="Invalid month"):
            lookup_minimum_wage_for_period("PUNJAB", 13, 2026)
        with pytest.raises(ValueError, match="Invalid month"):
            lookup_minimum_wage_for_period("PUNJAB", 0, 2026)

        # 8. Invalid year validation
        with pytest.raises(ValueError, match="Invalid year"):
            lookup_minimum_wage_for_period("PUNJAB", 5, 1999)
        with pytest.raises(ValueError, match="Invalid year"):
            lookup_minimum_wage_for_period("PUNJAB", 5, 2055)


# =============================================================================
# 3. API Endpoint Tests
# =============================================================================

def test_get_minimum_wage_endpoint_success():
    """Verify endpoint returns authoritative wage with candidate state derivation."""
    with patch("app.routers.audits.lookup_minimum_wage_for_period") as mock_lookup, \
         patch("app.services.min_wages.lookup_minimum_wage_for_period") as mock_lookup_svc:
        wage_dict = {
            "state": "PUNJAB",
            "skill_category": "SEMI-SKILLED",
            "requested_month": 11,
            "requested_year": 2026,
            "minimum_wage": 16800.0,
            "effective_month": 10,
            "effective_year": 2026,
            "effective_date": "2026-10-01",
        }
        mock_lookup.return_value = wage_dict
        mock_lookup_svc.return_value = wage_dict

        # 1. Main endpoint: /candidates/{id}/audit/minimum-wage
        res = get_minimum_wage(candidate_id=88001, month=11, year=2026, user=L1_PUNJAB_USER)
        assert res["minimum_wage"] == 16800.0
        assert res["state"] == "PUNJAB"
        assert res["effective_month"] == 10
        assert res["effective_year"] == 2026

        # 2. Direct alias endpoint: /minimum-wages/lookup
        alias_res = lookup_minimum_wage_endpoint(candidate_id=88001, month=11, year=2026, user=L1_PUNJAB_USER)
        assert alias_res["minimum_wage"] == 16800.0


def test_get_minimum_wage_endpoint_authorization_enforced():
    """Verify unauthorized coordinator cannot access another state's candidate minimum wage."""
    with pytest.raises(HTTPException) as exc_info:
        get_minimum_wage(candidate_id=88001, month=11, year=2026, user=L1_ODISHA_USER)
    assert exc_info.value.status_code == 403
    assert "You do not have access to candidates in this state" in str(exc_info.value.detail)


def test_get_minimum_wage_endpoint_missing_state_400():
    """Verify 400 response when candidate beneficiary state is missing."""
    cand_no_state = dict(PUNJAB_CANDIDATE)
    cand_no_state["state_name"] = None

    mock_custom_sb = MagicMock()
    mock_custom_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[cand_no_state]
    )

    with patch("app.routers.audits.supabase", mock_custom_sb):
        # 1. State-scoped L1 user fails closed with 403 on missing candidate state
        with pytest.raises(HTTPException) as exc_info_403:
            get_minimum_wage(candidate_id=88001, month=11, year=2026, user=L1_PUNJAB_USER)
        assert exc_info_403.value.status_code == 403

        # 2. Unrestricted Admin user gets 400 validation error
        with pytest.raises(HTTPException) as exc_info_400:
            get_minimum_wage(candidate_id=88001, month=11, year=2026, user=ADMIN_USER)
        assert exc_info_400.value.status_code == 400
        assert "does not have an authoritative beneficiary state" in str(exc_info_400.value.detail)


def test_get_minimum_wage_endpoint_no_revision_found_404():
    """Verify 404 response when no revision exists on or before requested period."""
    with patch("app.routers.audits.lookup_minimum_wage_for_period", return_value=None), \
         patch("app.services.min_wages.lookup_minimum_wage_for_period", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            get_minimum_wage(candidate_id=88001, month=1, year=2008, user=L1_PUNJAB_USER)
        assert exc_info.value.status_code == 404
        assert "No statutory semi-skilled minimum wage revision found" in str(exc_info.value.detail)


# =============================================================================
# 4. Tampering Protection & Authoritative Overwrite Tests
# =============================================================================

def test_tampered_wage_overwritten_on_draft_and_submit():
    """Verify that client-supplied fabricated minimum wage is ignored and overwritten by authoritative backend lookup."""
    saved_payload = {}
    def mock_save_call(payload):
        nonlocal saved_payload
        saved_payload = dict(payload)
        res_mock = MagicMock()
        res_mock.execute.return_value = MagicMock(data=[{"id": "audit-uuid-1", "candidate_id": 88001, "audit_status": "DRAFT", **payload}])
        return res_mock

    def table_mock(tbl):
        m = MagicMock()
        if tbl in ("ddugky_candidates", "candidates"):
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[PUNJAB_CANDIDATE])
        elif tbl == "user_centres":
            m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"tc_id": 501}])
        elif tbl == "placement_audits":
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[{"id": "audit-uuid-1", "candidate_id": 88001, "audit_status": "DRAFT", "signoff_details": {}}]
            )
            m.insert.side_effect = mock_save_call
            def mock_update(payload):
                mock_save_call(payload)
                up_mock = MagicMock()
                up_mock.eq.return_value.execute.return_value = MagicMock(data=[{"id": "audit-uuid-1", **payload}])
                return up_mock
            m.update.side_effect = mock_update
        elif tbl == "candidate_holds":
            m.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        elif tbl == "candidate_documents":
            m.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(
                data=[
                    {"document_type": "APPOINTMENT_LETTER", "employer_id": "emp_1", "upload_status": "SUCCESS"},
                    {"document_type": "SALARY_SLIP", "employer_id": "emp_1", "reporting_month": 10, "reporting_year": 2026, "upload_status": "SUCCESS"},
                    {"document_type": "SALARY_SLIP", "employer_id": "emp_1", "reporting_month": 11, "reporting_year": 2026, "upload_status": "SUCCESS"},
                    {"document_type": "SALARY_SLIP", "employer_id": "emp_1", "reporting_month": 12, "reporting_year": 2026, "upload_status": "SUCCESS"},
                    {"document_type": "BANK_STATEMENT", "employer_id": "emp_1", "is_consolidated": True, "coverage_start_month": 10, "coverage_start_year": 2026, "coverage_end_month": 12, "coverage_end_year": 2026, "covered_months": [{"month": 10, "year": 2026}, {"month": 11, "year": 2026}, {"month": 12, "year": 2026}], "upload_status": "SUCCESS"},
                ]
            )
        return m

    mock_db = MagicMock()
    mock_db.table.side_effect = table_mock

    tampered_draft_request = SaveAuditDraftRequest(
        candidate_snapshot={},
        employer_details=[EmployerEntry(id="emp_1", employer_name="Punjab Textiles Ltd", monthly_ctc=20000.0)],
        salary_details=[
            SalaryEntry(employer_id="emp_1", month=10, year=2026, gross_salary=20000, net_salary=18000, minimum_wage=99999.0, minimum_wage_state="BIHAR"),
            SalaryEntry(employer_id="emp_1", month=11, year=2026, gross_salary=20000, net_salary=18000, minimum_wage=0.0, minimum_wage_state="TAMIL NADU"),
            SalaryEntry(employer_id="emp_1", month=12, year=2026, gross_salary=20000, net_salary=18000, minimum_wage=None),
        ],
    )

    tampered_submit_request = SubmitAuditRequest(
        candidate_snapshot={},
        employer_details=[EmployerEntry(id="emp_1", employer_name="Punjab Textiles Ltd", monthly_ctc=20000.0)],
        salary_details=[
            SalaryEntry(employer_id="emp_1", month=10, year=2026, gross_salary=20000, net_salary=18000, minimum_wage=99999.0, minimum_wage_state="BIHAR"),
            SalaryEntry(employer_id="emp_1", month=11, year=2026, gross_salary=20000, net_salary=18000, minimum_wage=0.0, minimum_wage_state="TAMIL NADU"),
            SalaryEntry(employer_id="emp_1", month=12, year=2026, gross_salary=20000, net_salary=18000, minimum_wage=None),
        ],
    )

    with patch("app.routers.audits.supabase", mock_db), \
         patch("app.routers.audits.lookup_minimum_wage_for_period") as mock_lookup, \
         patch("app.services.min_wages.lookup_minimum_wage_for_period") as mock_lookup_svc:

        wage_dict = {
            "state": "PUNJAB",
            "skill_category": "SEMI-SKILLED",
            "requested_month": 10,
            "requested_year": 2026,
            "minimum_wage": 16800.0,
            "effective_month": 10,
            "effective_year": 2026,
            "effective_date": "2026-10-01",
        }
        mock_lookup.return_value = wage_dict
        mock_lookup_svc.return_value = wage_dict

        # 1. Draft save recalculation and authoritative overwrite
        save_audit_draft(candidate_id=88001, payload=tampered_draft_request, user=L1_PUNJAB_USER)
        assert saved_payload["salary_details"][0]["minimum_wage"] == 16800.0
        assert saved_payload["salary_details"][0]["minimum_wage_state"] == "PUNJAB"
        assert saved_payload["salary_details"][0]["minimum_wage_effective_month"] == 10
        assert saved_payload["salary_details"][0]["minimum_wage_effective_year"] == 2026

        # 2. Final submission recalculation and authoritative overwrite
        submit_audit(candidate_id=88001, payload=tampered_submit_request, user=L1_PUNJAB_USER)
        assert saved_payload["salary_details"][0]["minimum_wage"] == 16800.0
        assert saved_payload["salary_details"][0]["minimum_wage_state"] == "PUNJAB"


def test_l2_corrections_recalculates_authoritative_wage():
    """Verify L2 corrections recalculate minimum wage for updated salary periods."""
    saved_update = {}
    def mock_save_update(payload):
        nonlocal saved_update
        saved_update = dict(payload)
        res_mock = MagicMock()
        res_mock.execute.return_value = MagicMock(data=[{"id": "audit-uuid-1", **payload}])
        return res_mock

    def table_mock(tbl):
        m = MagicMock()
        if tbl in ("ddugky_candidates", "candidates"):
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[PUNJAB_CANDIDATE])
        elif tbl == "user_centres":
            m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"tc_id": 501}])
        elif tbl == "placement_audits":
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[{"id": "audit-uuid-1", "candidate_id": 88001, "audit_status": "SUBMITTED", "signoff_details": {}}]
            )
            def mock_update(payload):
                mock_save_update(payload)
                up_mock = MagicMock()
                up_mock.eq.return_value.execute.return_value = MagicMock(data=[{"id": "audit-uuid-1", **payload}])
                return up_mock
            m.update.side_effect = mock_update
        return m

    mock_db = MagicMock()
    mock_db.table.side_effect = table_mock

    corrections_payload = L2CorrectionsRequest(
        employer_details=[EmployerEntry(id="emp_1", employer_name="Punjab Textiles Ltd")],
        salary_details=[
            SalaryEntry(employer_id="emp_1", month=10, year=2026, gross_salary=20000, net_salary=18000, minimum_wage=5000.0),
            SalaryEntry(employer_id="emp_1", month=11, year=2026, gross_salary=20000, net_salary=18000),
            SalaryEntry(employer_id="emp_1", month=12, year=2026, gross_salary=20000, net_salary=18000),
        ],
        correction_notes="Updated salary values",
    )

    with patch("app.routers.audits.supabase", mock_db), \
         patch("app.routers.audits.lookup_minimum_wage_for_period") as mock_lookup, \
         patch("app.services.min_wages.lookup_minimum_wage_for_period") as mock_lookup_svc:

        wage_dict = {
            "state": "PUNJAB",
            "skill_category": "SEMI-SKILLED",
            "requested_month": 10,
            "requested_year": 2026,
            "minimum_wage": 16800.0,
            "effective_month": 10,
            "effective_year": 2026,
            "effective_date": "2026-10-01",
        }
        mock_lookup.return_value = wage_dict
        mock_lookup_svc.return_value = wage_dict

        save_l2_corrections(candidate_id=88001, payload=corrections_payload, user=L2_PUNJAB_USER)
        assert saved_update["salary_details"][0]["minimum_wage"] == 16800.0
        assert saved_update["salary_details"][0]["minimum_wage_state"] == "PUNJAB"
