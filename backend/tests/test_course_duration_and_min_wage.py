"""Tests for Course Duration Inference, Higher-of-Two Minimum CTC Calculation,
and L1 Submission Validation Enhancement.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException

from app.auth import CurrentUser
from app.routers.audits import (
    EmployerEntry,
    SalaryEntry,
    SubmitAuditRequest,
    submit_audit,
    get_work_states_endpoint,
)
from app.services.course_duration import (
    STANDARD_COURSE_DURATIONS,
    INDIAN_STATES_28,
    INDIAN_UTS_8,
    ALL_36_INDIAN_STATES_AND_UTS,
    calculate_course_duration,
    calculate_applicable_minimum_ctc,
    validate_employer_monthly_ctc,
)

L1_USER = CurrentUser(
    id="l1-user-uuid-1",
    email="l1.punjab@synchroserve.com",
    role="L1_COORDINATOR",
    full_name="Harpreet Kaur",
    assigned_state="PUNJAB",
    assigned_states=["PUNJAB"],
)


# =============================================================================
# 1. Course Duration Inference Tests (9 Scenarios)
# =============================================================================

def test_course_duration_exact_3_months():
    res = calculate_course_duration("2024-01-01", "2024-03-31")
    assert res["status"] == "DETERMINED"
    assert res["months"] == 3
    assert res["label"] == "3 Months"
    assert res["minimum_ctc"] == 6000.0


def test_course_duration_exact_6_months():
    res = calculate_course_duration("2024-01-01", "2024-06-30")
    assert res["status"] == "DETERMINED"
    assert res["months"] == 6
    assert res["label"] == "6 Months"
    assert res["minimum_ctc"] == 8000.0


def test_course_duration_exact_9_months():
    res = calculate_course_duration("2024-01-01", "2024-09-30")
    assert res["status"] == "DETERMINED"
    assert res["months"] == 9
    assert res["label"] == "9 Months"
    assert res["minimum_ctc"] == 12000.0


def test_course_duration_exact_12_months():
    res = calculate_course_duration("2024-01-01", "2024-12-31")
    assert res["status"] == "DETERMINED"
    assert res["months"] == 12
    assert res["label"] == "12 Months"
    assert res["minimum_ctc"] == 15000.0


def test_course_duration_slightly_different_dates():
    # 95 days -> 3 Months
    res3 = calculate_course_duration("2024-01-10", "2024-04-14")
    assert res3["months"] == 3
    assert res3["minimum_ctc"] == 6000.0

    # 195 days -> 6 Months
    res6 = calculate_course_duration("2024-01-15", "2024-07-27")
    assert res6["months"] == 6
    assert res6["minimum_ctc"] == 8000.0

    # 280 days -> 9 Months
    res9 = calculate_course_duration("2024-01-01", "2024-10-06")
    assert res9["months"] == 9
    assert res9["minimum_ctc"] == 12000.0

    # 380 days -> 12 Months
    res12 = calculate_course_duration("2024-01-01", "2025-01-15")
    assert res12["months"] == 12
    assert res12["minimum_ctc"] == 15000.0


def test_course_duration_missing_start_date():
    res = calculate_course_duration(None, "2024-06-30")
    assert res["status"] == "MISSING_DATES"
    assert res["months"] is None
    assert res["minimum_ctc"] is None
    assert "Course duration could not be reliably determined" in res["message"]


def test_course_duration_missing_end_date():
    res = calculate_course_duration("2024-01-01", "Not Available")
    assert res["status"] == "MISSING_DATES"
    assert res["months"] is None
    assert res["minimum_ctc"] is None


def test_course_duration_invalid_dates():
    res = calculate_course_duration("2024-06-30", "2024-01-01")
    assert res["status"] == "INVALID_DATES"
    assert res["months"] is None
    assert res["minimum_ctc"] is None
    assert "Batch end date precedes batch start date" in res["message"]


def test_course_duration_unmatched_duration():
    # Too short (< 65 days)
    res_short = calculate_course_duration("2024-01-01", "2024-01-25")
    assert res_short["status"] == "UNMATCHED_DURATION"
    assert res_short["months"] is None

    # Too long (> 425 days)
    res_long = calculate_course_duration("2024-01-01", "2025-07-01")
    assert res_long["status"] == "UNMATCHED_DURATION"
    assert res_long["months"] is None


# =============================================================================
# 2. Minimum Wage & Higher-of-Two Calculation Tests (10 Scenarios)
# =============================================================================

def test_higher_of_two_course_minimum_higher():
    # 6 months (₹8,000) vs State (₹7,000) -> ₹8,000
    calc = calculate_applicable_minimum_ctc(8000.0, 7000.0)
    assert calc["applicable_minimum_ctc"] == 8000.0
    assert calc["governing_rule"] == "COURSE_DURATION_HIGHER"


def test_higher_of_two_state_minimum_higher():
    # 3 months (₹6,000) vs State (₹9,000) -> ₹9,000
    calc = calculate_applicable_minimum_ctc(6000.0, 9000.0)
    assert calc["applicable_minimum_ctc"] == 9000.0
    assert calc["governing_rule"] == "STATE_WAGE_HIGHER"


def test_higher_of_two_both_equal():
    calc = calculate_applicable_minimum_ctc(8000.0, 8000.0)
    assert calc["applicable_minimum_ctc"] == 8000.0
    assert calc["governing_rule"] == "EQUAL_AMOUNTS"


def test_ctc_validation_below_applicable_minimum():
    course_info = {"months": 6, "label": "6 Months", "minimum_ctc": 8000.0}
    val = validate_employer_monthly_ctc(
        monthly_ctc=9000.0,
        course_duration_info=course_info,
        state_min_wage=10000.0,
        employer_name="Alpha Tech",
    )
    assert val["is_valid"] is False
    assert val["applicable_minimum_ctc"] == 10000.0
    msg = val["user_message"]
    assert "Course Duration: 6 Months" in msg
    assert "Course Minimum CTC: ₹8,000" in msg
    assert "State Minimum Wage: ₹10,000" in msg
    assert "Applicable Minimum CTC: ₹10,000" in msg
    assert "Entered Monthly CTC: ₹9,000" in msg
    assert "Please update the Monthly CTC" in msg


def test_ctc_validation_exactly_equal():
    course_info = {"months": 6, "label": "6 Months", "minimum_ctc": 8000.0}
    val = validate_employer_monthly_ctc(
        monthly_ctc=10000.0,
        course_duration_info=course_info,
        state_min_wage=10000.0,
    )
    assert val["is_valid"] is True
    assert val["applicable_minimum_ctc"] == 10000.0


def test_ctc_validation_above_applicable_minimum():
    course_info = {"months": 6, "label": "6 Months", "minimum_ctc": 8000.0}
    val = validate_employer_monthly_ctc(
        monthly_ctc=12500.0,
        course_duration_info=course_info,
        state_min_wage=10000.0,
    )
    assert val["is_valid"] is True


def test_supported_state_with_historical_wage():
    # Telangana ₹16,950 vs 3 months ₹6,000 -> ₹16,950
    calc = calculate_applicable_minimum_ctc(6000.0, 16950.0)
    assert calc["applicable_minimum_ctc"] == 16950.0


def test_unsupported_state_without_wage_data():
    # Maharashtra (None) vs 6 months ₹8,000 -> ₹8,000
    course_info = {"months": 6, "label": "6 Months", "minimum_ctc": 8000.0}
    calc = calculate_applicable_minimum_ctc(course_info["minimum_ctc"], None)
    assert calc["applicable_minimum_ctc"] == 8000.0
    assert calc["governing_rule"] == "COURSE_DURATION_ONLY"

    # Monthly CTC meets course minimum
    val = validate_employer_monthly_ctc(8500.0, course_info, None)
    assert val["is_valid"] is True

    # Monthly CTC below course minimum
    val_fail = validate_employer_monthly_ctc(7000.0, course_info, None)
    assert val_fail["is_valid"] is False
    assert "State Minimum Wage: Unavailable" in val_fail["user_message"]


def test_state_wage_unavailable_but_course_duration_available():
    course_info = {"months": 12, "label": "12 Months", "minimum_ctc": 15000.0}
    val = validate_employer_monthly_ctc(16000.0, course_info, None)
    assert val["is_valid"] is True
    assert val["applicable_minimum_ctc"] == 15000.0


def test_both_state_wage_and_course_duration_unavailable():
    course_info = {"months": None, "label": None, "minimum_ctc": None}
    val = validate_employer_monthly_ctc(0, course_info, None)
    assert val["is_valid"] is True
    assert val["applicable_minimum_ctc"] is None


# =============================================================================
# 3. Work States Master List Tests
# =============================================================================

def test_work_states_master_list():
    assert len(INDIAN_STATES_28) == 28
    assert len(INDIAN_UTS_8) == 8
    assert len(ALL_36_INDIAN_STATES_AND_UTS) == 36

    res = get_work_states_endpoint(user=L1_USER)
    assert len(res["states"]) == 28
    assert len(res["union_territories"]) == 8
    assert len(res["all"]) == 36
    assert "Maharashtra" in res["states"]
    assert "Delhi" in res["union_territories"]


# =============================================================================
# 4. L1 Submission Endpoint Validation Tests
# =============================================================================

def test_l1_submission_blocked_when_ctc_below_applicable_minimum():
    """Verify that submit_audit returns HTTP 400 when Monthly CTC is below the governing minimum."""
    candidate = {
        "candidate_id": 88001,
        "candidate_first_name": "Gurpreet",
        "candidate_last_name": "Singh",
        "state_name": "PUNJAB",
        "tc_id": 501,
        "tc_name": "Ludhiana Training Centre",
        "appointed": True,
        "batch_start_date": "2024-01-01",
        "batch_end_date": "2024-06-30", # 6 Months -> min CTC ₹8,000
    }

    def table_mock(tbl):
        m = MagicMock()
        if tbl in ("ddugky_candidates", "candidates"):
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[candidate])
        elif tbl == "user_centres":
            m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"tc_id": 501}])
        elif tbl == "placement_audits":
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[{"id": "audit-uuid-1", "candidate_id": 88001, "audit_status": "DRAFT", "signoff_details": {}}]
            )
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

    # Monthly CTC is ₹7,000, but 6-month course requires ₹8,000 (and Ludhiana/Punjab state wage is ₹16,400)
    submit_request = SubmitAuditRequest(
        candidate_snapshot={},
        employer_details=[
            EmployerEntry(id="emp_1", employer_name="Ludhiana Mills", place_of_work="Ludhiana", appointment_date="2026-02-01", monthly_ctc=7000.0),
        ],
        salary_details=[
            SalaryEntry(employer_id="emp_1", month=10, year=2026, gross_salary=20000),
            SalaryEntry(employer_id="emp_1", month=11, year=2026, gross_salary=20000),
            SalaryEntry(employer_id="emp_1", month=12, year=2026, gross_salary=20000),
        ],
    )

    with patch("app.routers.audits.supabase", mock_db), \
         patch("app.services.min_wages.lookup_minimum_wage_for_date") as mock_date, \
         patch("app.services.min_wages.lookup_minimum_wage_for_period") as mock_period:

        mock_date.return_value = {"minimum_wage": 16400.0, "state": "PUNJAB", "effective_month": 10, "effective_year": 2025}
        mock_period.return_value = {"minimum_wage": 16400.0, "state": "PUNJAB", "effective_month": 10, "effective_year": 2025}

        with pytest.raises(HTTPException) as exc_info:
            submit_audit(candidate_id=88001, payload=submit_request, user=L1_USER)

        assert exc_info.value.status_code == 400
        assert "Minimum CTC Requirement Not Met" in str(exc_info.value.detail) or "The entered monthly CTC" in str(exc_info.value.detail)
        assert "Applicable Minimum CTC: ₹16,400" in str(exc_info.value.detail)
        assert "Entered Monthly CTC: ₹7,000" in str(exc_info.value.detail)


def test_l1_submission_permits_unsupported_state_when_ctc_meets_course_minimum():
    """Verify that unsupported state (e.g. Bangalore / Karnataka) is permitted when Monthly CTC
    meets or exceeds the inferred course duration minimum (₹8,000 for 6 months).
    """
    candidate = {
        "candidate_id": 88001,
        "candidate_first_name": "Gurpreet",
        "candidate_last_name": "Singh",
        "state_name": "PUNJAB",
        "tc_id": 501,
        "tc_name": "Ludhiana Training Centre",
        "appointed": True,
        "batch_start_date": "2024-01-01",
        "batch_end_date": "2024-06-30", # 6 Months -> min CTC ₹8,000
    }

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
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[candidate])
        elif tbl == "user_centres":
            m.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"tc_id": 501}])
        elif tbl == "placement_audits":
            m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[{"id": "audit-uuid-1", "candidate_id": 88001, "audit_status": "DRAFT", "signoff_details": {}}]
            )
            def mock_up(p):
                mock_save_update(p)
                up_mock = MagicMock()
                up_mock.eq.return_value.execute.return_value = MagicMock(data=[{"id": "audit-uuid-1", **p}])
                return up_mock
            m.update.side_effect = mock_up
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

    # Monthly CTC is ₹9,000, which exceeds the ₹8,000 course minimum for Karnataka (unsupported state)
    submit_request = SubmitAuditRequest(
        candidate_snapshot={},
        employer_details=[
            EmployerEntry(id="emp_1", employer_name="Bengaluru Systems", place_of_work="Karnataka", appointment_date="2026-02-01", monthly_ctc=9000.0),
        ],
        salary_details=[
            SalaryEntry(employer_id="emp_1", month=10, year=2026, gross_salary=20000),
            SalaryEntry(employer_id="emp_1", month=11, year=2026, gross_salary=20000),
            SalaryEntry(employer_id="emp_1", month=12, year=2026, gross_salary=20000),
        ],
    )

    with patch("app.routers.audits.supabase", mock_db):
        res = submit_audit(candidate_id=88001, payload=submit_request, user=L1_USER)
        assert res["audit"]["audit_status"] == "SUBMITTED"
        assert saved_update["employer_details"][0]["work_state_detection_status"] == "UNSUPPORTED_STATE"
        assert saved_update["employer_details"][0]["minimum_wages"] is None
