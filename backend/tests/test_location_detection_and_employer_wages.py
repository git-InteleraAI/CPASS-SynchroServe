"""Comprehensive test suite for CPASS Automatic State Detection from Place of Work.

Covers:
1. Location identification:
   - Chennai -> Tamil Nadu
   - Hyderabad -> Telangana
   - Ludhiana -> Punjab
   - Ambiguous locations (Bilaspur -> Chhattisgarh / Himachal Pradesh)
   - Unsupported states (Whitefield, Bangalore -> Karnataka)
   - Incomplete / short inputs
   - PIN codes (600001 -> Tamil Nadu, 141001 -> Punjab)
2. Employer Minimum Wage lookups:
   - Based on detected work_state and appointment_date
   - Appointment date changes updating wage
3. Multiple employers in different states:
   - Candidate in Punjab placed with Emp 1 (Ludhiana) & Emp 2 (Chennai)
   - Salary rows linked to respective employers using employer work states
   - Candidate beneficiary state never substituted
4. Authoritative security & tampering protection:
   - Draft save re-detection and persistence
   - Final submission strict validation & overwrite
   - L2 corrections recalculation
"""

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
    lookup_employer_wage_endpoint,
    save_audit_draft,
    save_l2_corrections,
    submit_audit,
)
from app.services.location_detector import detect_work_state
from app.services.min_wages import (
    apply_authoritative_employer_and_salary_wages,
    lookup_minimum_wage_for_date,
    lookup_minimum_wage_for_period,
)

L1_PUNJAB_USER = CurrentUser(
    id="l1-pb-uuid",
    email="pbpe@synchroserve.com",
    full_name="Punjab Placement Coordinator",
    role="L1_COORDINATOR",
    assigned_state="PUNJAB",
    assigned_states=["PUNJAB"],
)

L2_PUNJAB_USER = CurrentUser(
    id="l2-pb-uuid",
    email="pbch@synchroserve.com",
    full_name="Punjab Centre Head",
    role="L2_MANAGER",
    assigned_state="PUNJAB",
    assigned_states=["PUNJAB"],
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


@pytest.fixture(autouse=True)
def mock_db_tables():
    """Mock database access for zero-network execution."""
    mock_sb = MagicMock()

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
            m.insert.return_value.execute.return_value = MagicMock(data=[{"id": "audit-uuid-1", "audit_status": "SUBMITTED"}])
            m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "audit-uuid-1"}])
        elif tbl == "candidate_holds":
            m.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        elif tbl == "candidate_documents":
            m.select.return_value.eq.return_value.neq.return_value.execute.return_value = MagicMock(
                data=[
                    {"document_type": "APPOINTMENT_LETTER", "employer_id": "emp_1", "upload_status": "SUCCESS"},
                    {"document_type": "APPOINTMENT_LETTER", "employer_id": "emp_2", "upload_status": "SUCCESS"},
                    {"document_type": "SALARY_SLIP", "employer_id": "emp_1", "reporting_month": 10, "reporting_year": 2026, "upload_status": "SUCCESS"},
                    {"document_type": "SALARY_SLIP", "employer_id": "emp_1", "reporting_month": 11, "reporting_year": 2026, "upload_status": "SUCCESS"},
                    {"document_type": "SALARY_SLIP", "employer_id": "emp_2", "reporting_month": 12, "reporting_year": 2026, "upload_status": "SUCCESS"},
                    {"document_type": "BANK_STATEMENT", "employer_id": "emp_1", "is_consolidated": True, "coverage_start_month": 10, "coverage_start_year": 2026, "coverage_end_month": 12, "coverage_end_year": 2026, "covered_months": [{"month": 10, "year": 2026}, {"month": 11, "year": 2026}, {"month": 12, "year": 2026}], "upload_status": "SUCCESS"},
                ]
            )
        return m

    mock_sb.table.side_effect = table_mock
    with patch("app.db.supabase", mock_sb), \
         patch("app.auth.supabase", mock_sb), \
         patch("app.routers.audits.supabase", mock_sb), \
         patch("app.services.min_wages.supabase", mock_sb):
        yield mock_sb


# -----------------------------------------------------------------------------
# 1-6: Location Identification Unit Tests
# -----------------------------------------------------------------------------

def test_location_detection_chennai_tamil_nadu():
    res = detect_work_state("Chennai")
    assert res.status == "IDENTIFIED"
    assert res.detected_state == "TAMIL NADU"
    assert res.is_supported is True


def test_location_detection_hyderabad_telangana():
    res = detect_work_state("Hyderabad, Telangana")
    assert res.status == "IDENTIFIED"
    assert res.detected_state == "TELANGANA"
    assert res.is_supported is True


def test_location_detection_ludhiana_punjab():
    res = detect_work_state("Ludhiana")
    assert res.status == "IDENTIFIED"
    assert res.detected_state == "PUNJAB"
    assert res.is_supported is True


def test_location_detection_ambiguous_location():
    res = detect_work_state("Bilaspur")
    assert res.status == "AMBIGUOUS"
    assert res.detected_state is None
    assert set(res.candidate_states) == {"CHHATTISGARH", "HIMACHAL PRADESH"}
    assert res.is_supported is False


def test_location_detection_unsupported_state():
    res = detect_work_state("Whitefield, Bangalore")
    assert res.status == "UNSUPPORTED_STATE"
    assert res.detected_state == "KARNATAKA"
    assert res.is_supported is False


def test_location_detection_incomplete_or_empty():
    assert detect_work_state("").status == "INSUFFICIENT_INPUT"
    assert detect_work_state(" ").status == "INSUFFICIENT_INPUT"
    assert detect_work_state("X").status == "INSUFFICIENT_INPUT"
    assert detect_work_state("UnknownLocationXYZ").status == "UNRESOLVED"


def test_location_detection_pin_codes():
    res_tn = detect_work_state("SIPCOT Industrial Park 600001")
    assert res_tn.status == "IDENTIFIED"
    assert res_tn.detected_state == "TAMIL NADU"

    res_pb = detect_work_state("Focal Point, 141001")
    assert res_pb.status == "IDENTIFIED"
    assert res_pb.detected_state == "PUNJAB"


# -----------------------------------------------------------------------------
# 7: Appointment Date Changes and Employer Wage Lookups
# -----------------------------------------------------------------------------

def test_appointment_date_employer_wage_lookup():
    """Verify latest revision effective on or before appointment date."""
    def mock_date_lookup(state, date_str):
        if state == "PUNJAB" and date_str >= "2026-04-01":
            return {"minimum_wage": 16600.0, "state": "PUNJAB", "effective_month": 4, "effective_year": 2026}
        elif state == "PUNJAB" and date_str < "2026-04-01":
            return {"minimum_wage": 16400.0, "state": "PUNJAB", "effective_month": 10, "effective_year": 2025}
        return None

    with patch("app.routers.audits.lookup_minimum_wage_for_date", side_effect=mock_date_lookup):
        # 1. Appointment date in May 2026 -> April 2026 revision (16,600)
        res1 = lookup_employer_wage_endpoint(
            candidate_id=88001,
            appointment_date="2026-05-10",
            location="Ludhiana",
            user=L1_PUNJAB_USER,
        )
        assert res1["minimum_wage"] == 16600.0

        # 2. Changed appointment date to Jan 2026 -> Oct 2025 revision (16,400)
        res2 = lookup_employer_wage_endpoint(
            candidate_id=88001,
            appointment_date="2026-01-15",
            location="Ludhiana",
            user=L1_PUNJAB_USER,
        )
        assert res2["minimum_wage"] == 16400.0


# -----------------------------------------------------------------------------
# 8-9: Multiple Employers in Different States & Salary Row Linkage
# -----------------------------------------------------------------------------

def test_multiple_employers_in_different_states_and_salary_linkage():
    """Verify Candidate from Punjab placed with Emp 1 in Punjab and Emp 2 in Tamil Nadu.
    Salary rows linked to Emp 1 use Punjab rates, and rows linked to Emp 2 use Tamil Nadu rates.
    Neither uses candidate state as a blind substitute.
    """
    employers = [
        {"id": "emp_1", "employer_name": "Hero Cycles Ludhiana", "place_of_work": "Ludhiana", "appointment_date": "2026-01-01"},
        {"id": "emp_2", "employer_name": "TVS Motors Chennai", "place_of_work": "Chennai", "appointment_date": "2026-06-01"},
    ]
    salaries = [
        {"employer_id": "emp_1", "month": 2, "year": 2026, "gross_salary": 18000},
        {"employer_id": "emp_2", "month": 7, "year": 2026, "gross_salary": 20000},
    ]

    def mock_period_lookup(state, month, year):
        if state == "PUNJAB":
            return {"minimum_wage": 16400.0, "state": "PUNJAB", "effective_month": 10, "effective_year": 2025}
        elif state == "TAMIL NADU":
            return {"minimum_wage": 15800.0, "state": "TAMIL NADU", "effective_month": 4, "effective_year": 2026}
        return None

    with patch("app.services.min_wages.lookup_minimum_wage_for_period", side_effect=mock_period_lookup), \
         patch("app.services.min_wages.lookup_minimum_wage_for_date") as mock_date:
        mock_date.return_value = {"minimum_wage": 16400.0, "state": "PUNJAB", "effective_month": 10, "effective_year": 2025}

        enriched_emps, enriched_sals = apply_authoritative_employer_and_salary_wages(
            PUNJAB_CANDIDATE, employers, salaries, strict=False
        )

        # Emp 1 is detected as Punjab
        assert enriched_emps[0]["work_state"] == "PUNJAB"
        assert enriched_emps[0]["work_state_detection_status"] == "IDENTIFIED"

        # Emp 2 is detected as Tamil Nadu
        assert enriched_emps[1]["work_state"] == "TAMIL NADU"
        assert enriched_emps[1]["work_state_detection_status"] == "IDENTIFIED"

        # Sal 1 (Emp 1) uses Punjab wage
        assert enriched_sals[0]["minimum_wage"] == 16400.0
        assert enriched_sals[0]["minimum_wage_state"] == "PUNJAB"

        # Sal 2 (Emp 2) uses Tamil Nadu wage, NOT candidate's Punjab state!
        assert enriched_sals[1]["minimum_wage"] == 15800.0
        assert enriched_sals[1]["minimum_wage_state"] == "TAMIL NADU"


# -----------------------------------------------------------------------------
# 10: Draft Save and Reload with Work State
# -----------------------------------------------------------------------------

def test_draft_save_detects_and_persists_work_state():
    """Verify that draft saving identifies and stores work_state without manual selection."""
    saved_payload = {}
    def mock_save(payload):
        nonlocal saved_payload
        saved_payload = dict(payload)
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
                data=[{"id": "audit-uuid-1", "candidate_id": 88001, "audit_status": "DRAFT", "signoff_details": {}}]
            )
            m.insert.side_effect = mock_save
            def mock_update(payload):
                mock_save(payload)
                up_mock = MagicMock()
                up_mock.eq.return_value.execute.return_value = MagicMock(data=[{"id": "audit-uuid-1", **payload}])
                return up_mock
            m.update.side_effect = mock_update
        return m

    mock_db = MagicMock()
    mock_db.table.side_effect = table_mock

    draft_request = SaveAuditDraftRequest(
        candidate_snapshot={},
        employer_details=[
            EmployerEntry(id="emp_1", employer_name="Ludhiana Woolens", place_of_work="Ludhiana", appointment_date="2026-02-01"),
        ],
        salary_details=[
            SalaryEntry(employer_id="emp_1", month=2, year=2026, gross_salary=18000),
        ],
    )

    with patch("app.routers.audits.supabase", mock_db), \
         patch("app.services.min_wages.lookup_minimum_wage_for_date") as mock_date, \
         patch("app.services.min_wages.lookup_minimum_wage_for_period") as mock_period:

        mock_date.return_value = {"minimum_wage": 16400.0, "state": "PUNJAB", "effective_month": 10, "effective_year": 2025}
        mock_period.return_value = {"minimum_wage": 16400.0, "state": "PUNJAB", "effective_month": 10, "effective_year": 2025}

        save_audit_draft(candidate_id=88001, payload=draft_request, user=L1_PUNJAB_USER)

        assert saved_payload["employer_details"][0]["work_state"] == "PUNJAB"
        assert saved_payload["employer_details"][0]["work_state_detection_status"] == "IDENTIFIED"
        assert saved_payload["employer_details"][0]["minimum_wages"] == 16400.0


# -----------------------------------------------------------------------------
# 11: Final Submission Rejection of Unsupported / Ambiguous State
# -----------------------------------------------------------------------------

def test_final_submission_rejects_unsupported_state():
    """Verify that final submission raises 400 when an employer is in an unsupported state."""
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

    submit_request = SubmitAuditRequest(
        candidate_snapshot={},
        employer_details=[
            EmployerEntry(id="emp_1", employer_name="Bengaluru Systems", place_of_work="Whitefield, Bangalore", appointment_date="2026-02-01"),
        ],
        salary_details=[
            SalaryEntry(employer_id="emp_1", month=10, year=2026, gross_salary=20000),
            SalaryEntry(employer_id="emp_1", month=11, year=2026, gross_salary=20000),
            SalaryEntry(employer_id="emp_1", month=12, year=2026, gross_salary=20000),
        ],
    )

    with patch("app.routers.audits.supabase", mock_db):
        with pytest.raises(HTTPException) as exc_info:
            submit_audit(candidate_id=88001, payload=submit_request, user=L1_PUNJAB_USER)
        assert exc_info.value.status_code == 400
        assert "not supported in the 13-state minimum wage register" in str(exc_info.value.detail)


# -----------------------------------------------------------------------------
# 12: L2 Corrections Recalculation with Employer Work State
# -----------------------------------------------------------------------------

def test_l2_corrections_with_employer_work_state():
    """Verify L2 corrections recalculate minimum wage according to corrected place of work."""
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
            def mock_up(p):
                mock_save_update(p)
                up_mock = MagicMock()
                up_mock.eq.return_value.execute.return_value = MagicMock(data=[{"id": "audit-uuid-1", **p}])
                return up_mock
            m.update.side_effect = mock_up
        return m

    mock_db = MagicMock()
    mock_db.table.side_effect = table_mock

    corrections_payload = L2CorrectionsRequest(
        employer_details=[
            EmployerEntry(id="emp_1", employer_name="Chennai Textiles", place_of_work="Chennai", appointment_date="2026-05-01"),
        ],
        salary_details=[
            SalaryEntry(employer_id="emp_1", month=10, year=2026, gross_salary=20000),
            SalaryEntry(employer_id="emp_1", month=11, year=2026, gross_salary=20000),
            SalaryEntry(employer_id="emp_1", month=12, year=2026, gross_salary=20000),
        ],
        correction_notes="Corrected location to Chennai",
    )

    with patch("app.routers.audits.supabase", mock_db), \
         patch("app.services.min_wages.lookup_minimum_wage_for_date") as mock_date, \
         patch("app.services.min_wages.lookup_minimum_wage_for_period") as mock_period:

        mock_date.return_value = {"minimum_wage": 15800.0, "state": "TAMIL NADU", "effective_month": 4, "effective_year": 2026}
        mock_period.return_value = {"minimum_wage": 16000.0, "state": "TAMIL NADU", "effective_month": 10, "effective_year": 2026}

        save_l2_corrections(candidate_id=88001, payload=corrections_payload, user=L2_PUNJAB_USER)

        assert saved_update["employer_details"][0]["work_state"] == "TAMIL NADU"
        assert saved_update["salary_details"][0]["minimum_wage_state"] == "TAMIL NADU"
        assert saved_update["salary_details"][0]["minimum_wage"] == 16000.0


# -----------------------------------------------------------------------------
# 13: Tampered Employer State and Wages Overwritten
# -----------------------------------------------------------------------------

def test_tampered_employer_wage_and_state_overwritten():
    """Verify that forged employer work_state or minimum_wages in draft request are overwritten."""
    saved_payload = {}
    def mock_save(payload):
        nonlocal saved_payload
        saved_payload = dict(payload)
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
                data=[{"id": "audit-uuid-1", "candidate_id": 88001, "audit_status": "DRAFT", "signoff_details": {}}]
            )
            m.insert.side_effect = mock_save
            def mock_update(payload):
                mock_save(payload)
                up_mock = MagicMock()
                up_mock.eq.return_value.execute.return_value = MagicMock(data=[{"id": "audit-uuid-1", **payload}])
                return up_mock
            m.update.side_effect = mock_update
        return m

    mock_db = MagicMock()
    mock_db.table.side_effect = table_mock

    tampered_request = SaveAuditDraftRequest(
        candidate_snapshot={},
        employer_details=[
            EmployerEntry(
                id="emp_1",
                employer_name="Punjab Knitwear",
                place_of_work="Ludhiana",
                work_state="BIHAR",             # Fabricated state
                minimum_wages=99999.0,          # Fabricated wage
                appointment_date="2026-02-01",
            ),
        ],
        salary_details=[
            SalaryEntry(employer_id="emp_1", month=2, year=2026, gross_salary=18000),
        ],
    )

    with patch("app.routers.audits.supabase", mock_db), \
         patch("app.services.min_wages.lookup_minimum_wage_for_date") as mock_date, \
         patch("app.services.min_wages.lookup_minimum_wage_for_period") as mock_period:

        mock_date.return_value = {"minimum_wage": 16400.0, "state": "PUNJAB", "effective_month": 10, "effective_year": 2025}
        mock_period.return_value = {"minimum_wage": 16400.0, "state": "PUNJAB", "effective_month": 10, "effective_year": 2025}

        save_audit_draft(candidate_id=88001, payload=tampered_request, user=L1_PUNJAB_USER)

        # Overwritten authoritatively:
        assert saved_payload["employer_details"][0]["work_state"] == "PUNJAB"
        assert saved_payload["employer_details"][0]["minimum_wages"] == 16400.0
