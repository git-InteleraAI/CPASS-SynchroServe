"""Tests for Master Data Importer (Phase 1).

Covers CSV & Excel parsing, raw column preservation, duplicate ID detection,
conflicting entity mappings, date validation, missing fields, dry-run safety,
and dependency-ordered upserts.
"""

from unittest.mock import MagicMock
import tempfile
from pathlib import Path
import pandas as pd
import pytest

from app.services.master_importer import (
    load_dataframe,
    parse_and_validate_date,
    validate_and_prepare_master_data,
    execute_upserts,
)


@pytest.fixture
def sample_row():
    return {
        "Sl.No": "1",
        "Candidate_ID": "1001",
        "KaushalPanjee_ID": "KP1001",
        "State_Name": "Kerala",
        "District_Name": "Kottayam",
        "Sanction_order_Number": "SO-2023-01",
        "TC_Name": "Kottayam Centre",
        "TC_MPR_ID": "MPR-TC-1",
        "TC_id": "10",
        "TC_State_Name": "Kerala",
        "TC_District_Name": "Kottayam",
        "KB_Batch_ID": "200",
        "Batch_Code": "BATCH-KOT-01",
        "Batch_Startdate": "01-01-2023",
        "Batch_Enddate": "30-04-2023",
        "Candidate_First_Name": "Rahul",
        "Candidate_Last_Name": "Nair",
        "Candidate_FatherName": "Suresh Nair",
        "Gender": "Male",
        "DateOfBirth": "15-05-1998",
        "Mobile_Number": "9876543210",
        "Appointed": "YES",
        "EmployerName": "TechCorp",
        "Custom_Extra_Col": "ExtraData123",
    }


def test_csv_loading_and_raw_preservation(sample_row):
    """Verify that CSV reading preserves all original columns in candidates.raw."""
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
        df_src = pd.DataFrame([sample_row])
        df_src.to_csv(f.name, index=False)
        temp_path = f.name

    try:
        df = load_dataframe(temp_path)
        assert len(df) == 1
        assert "Custom_Extra_Col" in df.columns

        report, centres, batches, cands = validate_and_prepare_master_data(df, dry_run=True)
        assert report.error_rows_count == 0
        assert len(cands) == 1

        cand = cands[0]
        assert cand["candidate_id"] == 1001
        assert "Custom_Extra_Col" in cand["raw"]
        assert cand["raw"]["Custom_Extra_Col"] == "ExtraData123"
        assert cand["raw"]["Mobile_Number"] == "9876543210"
        assert cand["dob"] == "1998-05-15"
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_excel_loading(sample_row):
    """Verify that Excel (.xlsx) files are correctly loaded and parsed."""
    with tempfile.NamedTemporaryFile("wb", suffix=".xlsx", delete=False) as f:
        df_src = pd.DataFrame([sample_row])
        df_src.to_excel(f.name, index=False)
        temp_path = f.name

    try:
        df = load_dataframe(temp_path)
        assert len(df) == 1
        report, centres, batches, cands = validate_and_prepare_master_data(df, dry_run=True)
        assert report.error_rows_count == 0
        assert len(cands) == 1
        assert cands[0]["candidate_id"] == 1001
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_missing_required_columns(sample_row):
    """Missing required column must be caught and reported in report findings."""
    del sample_row["Candidate_ID"]
    df = pd.DataFrame([sample_row])
    report, centres, batches, cands = validate_and_prepare_master_data(df, dry_run=True)

    assert report.error_rows_count > 0
    assert "MISSING_REQUIRED_COLUMN" in report.errors_by_type
    assert len(cands) == 0


def test_duplicate_candidate_id_detection(sample_row):
    """Duplicate Candidate_ID across rows must be flagged with source row numbers."""
    row1 = dict(sample_row)
    row2 = dict(sample_row)  # Identical candidate ID 1001
    row2["Candidate_First_Name"] = "Different Name"

    df = pd.DataFrame([row1, row2])
    report, centres, batches, cands = validate_and_prepare_master_data(df, dry_run=True)

    assert report.errors_by_type.get("DUPLICATE_CANDIDATE_ID") == 1
    dup_error = next(e for e in report.errors if e.error_type == "DUPLICATE_CANDIDATE_ID")
    assert dup_error.row == 3  # Header is row 1, row1 is row 2, row2 is row 3
    assert dup_error.candidate_id == 1001
    assert "first seen at row 2" in dup_error.message
    # Only valid rows are accepted, duplicate row was not silently added
    assert len(cands) == 1


def test_conflicting_tc_id_mapping(sample_row):
    """Same TC_id with different names or states must be flagged as conflicting."""
    row1 = dict(sample_row)
    row2 = dict(sample_row)
    row2["Candidate_ID"] = "1002"
    row2["TC_Name"] = "Completely Different Training Centre Name"

    df = pd.DataFrame([row1, row2])
    report, centres, batches, cands = validate_and_prepare_master_data(df, dry_run=True)

    assert report.errors_by_type.get("CONFLICTING_TC_MAPPING") == 1
    conflict_err = next(e for e in report.errors if e.error_type == "CONFLICTING_TC_MAPPING")
    assert conflict_err.row == 3
    assert "Conflicting TC mapping for TC_id 10" in conflict_err.message


def test_conflicting_batch_mapping(sample_row):
    """Same KB_Batch_ID with different batch codes or dates must be flagged."""
    row1 = dict(sample_row)
    row2 = dict(sample_row)
    row2["Candidate_ID"] = "1002"
    row2["Batch_Code"] = "DIFFERENT-BATCH-CODE"

    df = pd.DataFrame([row1, row2])
    report, centres, batches, cands = validate_and_prepare_master_data(df, dry_run=True)

    assert report.errors_by_type.get("CONFLICTING_BATCH_MAPPING") == 1
    b_err = next(e for e in report.errors if e.error_type == "CONFLICTING_BATCH_MAPPING")
    assert b_err.row == 3
    assert "Conflicting batch mapping for KB_Batch_ID 200" in b_err.message


def test_invalid_date_detection(sample_row):
    """DOB findings are recorded as warnings with dob=None, while batch date errors remain blocking."""
    row_bad_year = dict(sample_row)
    row_bad_year["DateOfBirth"] = "1196-02-14"

    row_malformed = dict(sample_row)
    row_malformed["Candidate_ID"] = "1002"
    row_malformed["DateOfBirth"] = "not-a-valid-date"

    # Row with invalid batch date (must still be a blocking error)
    row_bad_batch = dict(sample_row)
    row_bad_batch["Candidate_ID"] = "1003"
    row_bad_batch["Batch_Startdate"] = "not-a-batch-date"

    df = pd.DataFrame([row_bad_year, row_malformed, row_bad_batch])
    report, centres, batches, cands = validate_and_prepare_master_data(df, dry_run=True)

    # DOB findings are warnings
    assert report.warnings_by_type.get("INVALID_DOB") == 2
    assert report.warning_rows_count == 2
    warn_msgs = [w.message for w in report.warnings if w.warning_type == "INVALID_DOB"]
    assert any("out of valid range" in m for m in warn_msgs)
    assert any("Invalid date format" in m for m in warn_msgs)

    # Batch date error is a blocking error
    assert report.errors_by_type.get("INVALID_DATE") == 1
    assert report.error_rows_count == 1

    # Candidates 1001 and 1002 are retained with dob=None; 1003 was rejected due to blocking batch date error
    assert len(cands) == 2
    c1001 = next(c for c in cands if c["candidate_id"] == 1001)
    assert c1001["dob"] is None
    assert c1001["raw"]["DateOfBirth"] == "1196-02-14"


def test_missing_required_relationships(sample_row):
    """Rows with missing required keys (e.g. empty TC_id) must be rejected."""
    row = dict(sample_row)
    row["TC_id"] = ""

    df = pd.DataFrame([row])
    report, centres, batches, cands = validate_and_prepare_master_data(df, dry_run=True)

    assert report.errors_by_type.get("MISSING_REQUIRED_VALUE") == 1
    assert len(cands) == 0


def test_dry_run_performs_zero_database_writes(sample_row):
    """Dry run should validate data and never call DB write operations."""
    df = pd.DataFrame([sample_row])
    report, centres, batches, cands = validate_and_prepare_master_data(df, dry_run=True)

    assert report.dry_run is True
    assert report.database_written is False

    mock_supabase = MagicMock()
    # In dry-run mode, execute_upserts is never called
    assert mock_supabase.table.call_count == 0


def test_dependency_ordered_upsert():
    """Verify upserts occur in strict dependency order: centres -> batches -> candidates."""
    mock_supabase = MagicMock()
    call_order = []

    def mock_table(table_name):
        mock_tbl = MagicMock()
        def mock_upsert(data, on_conflict=None):
            call_order.append((table_name, on_conflict))
            return MagicMock()
        mock_tbl.upsert = mock_upsert
        return mock_tbl

    mock_supabase.table.side_effect = mock_table

    centres = [{"tc_id": 1, "name": "TC 1"}]
    batches = [{"kb_batch_id": 10, "tc_id": 1, "batch_code": "B1"}]
    candidates = [{"candidate_id": 100, "kb_batch_id": 10, "first_name": "Test"}]

    execute_upserts(centres, batches, candidates, mock_supabase)

    assert len(call_order) == 3
    assert call_order[0] == ("training_centres", "tc_id")
    assert call_order[1] == ("batches", "kb_batch_id")
    assert call_order[2] == ("candidates", "candidate_id")


def test_repeat_import_identical_data_is_safe():
    """Identical repeat import against existing DB records passes with zero conflicts."""
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.in_.return_value.execute.return_value.data = [
        {"candidate_id": 100, "first_name": "Rahul", "last_name": "Nair", "dob": "1998-05-15", "father_name": "Suresh"}
    ]

    from app.services.master_importer import check_database_conflicts

    centres = []
    batches = []
    candidates = [{"candidate_id": 100, "first_name": "Rahul", "last_name": "Nair", "dob": "1998-05-15", "father_name": "Suresh"}]

    conflicts = check_database_conflicts(centres, batches, candidates, mock_supabase)
    assert len(conflicts) == 0


def test_repeat_import_conflicting_db_records_blocked():
    """Incoming record conflicting with existing DB record is detected and blocked."""
    mock_supabase = MagicMock()
    # Existing candidate in DB has different first name and DOB
    mock_supabase.table.return_value.select.return_value.in_.return_value.execute.return_value.data = [
        {"candidate_id": 100, "first_name": "Vikram", "last_name": "Joshi", "dob": "1992-01-01", "father_name": "Ramesh"}
    ]

    from app.services.master_importer import check_database_conflicts

    centres = []
    batches = []
    candidates = [{"candidate_id": 100, "first_name": "Rahul", "last_name": "Nair", "dob": "1998-05-15", "father_name": "Suresh"}]

    conflicts = check_database_conflicts(centres, batches, candidates, mock_supabase)
    assert len(conflicts) > 0
    assert "Candidate Candidate_ID 100 conflicts with existing database record" in conflicts[0]


def test_dob_year_1196_retained_with_dob_none_and_raw_preserved(sample_row):
    """Candidate with DOB 1196-02-14 is retained with dob=None, raw preserved, and warning logged."""
    row = dict(sample_row)
    row["DateOfBirth"] = "1196-02-14"

    df = pd.DataFrame([row])
    report, centres, batches, cands = validate_and_prepare_master_data(df, dry_run=True)

    assert report.error_rows_count == 0
    assert len(report.errors) == 0
    assert report.warning_rows_count == 1
    assert len(report.warnings) == 1

    warning = report.warnings[0]
    assert warning.warning_type == "INVALID_DOB"
    assert warning.field == "DateOfBirth"
    assert warning.candidate_id == 1001
    assert warning.row == 2
    assert warning.raw_value == "1196-02-14"
    assert "1196" in warning.message

    assert len(cands) == 1
    cand = cands[0]
    assert cand["candidate_id"] == 1001
    assert cand["dob"] is None
    assert cand["raw"]["DateOfBirth"] == "1196-02-14"


def test_dob_year_0001_not_automatically_converted(sample_row):
    """A DOB of 0001-01-01 is not converted to another year; preserved in raw and sets dob=None."""
    row = dict(sample_row)
    row["DateOfBirth"] = "0001-01-01"

    df = pd.DataFrame([row])
    report, centres, batches, cands = validate_and_prepare_master_data(df, dry_run=True)

    assert report.error_rows_count == 0
    assert report.warning_rows_count == 1
    assert len(cands) == 1
    assert cands[0]["dob"] is None
    assert cands[0]["raw"]["DateOfBirth"] == "0001-01-01"
    assert report.warnings[0].raw_value == "0001-01-01"


def test_dobs_in_2023_2024_not_silently_accepted(sample_row):
    """DOBs in 2023-2024 (outside 1940-2020) are not silently accepted; dob=None with warning."""
    row1 = dict(sample_row)
    row1["Candidate_ID"] = "1001"
    row1["DateOfBirth"] = "19-04-2023"

    row2 = dict(sample_row)
    row2["Candidate_ID"] = "1002"
    row2["DateOfBirth"] = "15-06-2024"

    df = pd.DataFrame([row1, row2])
    report, centres, batches, cands = validate_and_prepare_master_data(df, dry_run=True)

    assert report.error_rows_count == 0
    assert report.warning_rows_count == 2
    assert len(cands) == 2
    for cand in cands:
        assert cand["dob"] is None
    c1 = next(c for c in cands if c["candidate_id"] == 1001)
    c2 = next(c for c in cands if c["candidate_id"] == 1002)
    assert c1["raw"]["DateOfBirth"] == "19-04-2023"
    assert c2["raw"]["DateOfBirth"] == "15-06-2024"


def test_row_with_invalid_dob_and_missing_tc_id_still_rejected(sample_row):
    """Row with invalid DOB and missing required TC_id is still rejected by blocking error."""
    row = dict(sample_row)
    row["DateOfBirth"] = "1196-02-14"
    row["TC_id"] = ""

    df = pd.DataFrame([row])
    report, centres, batches, cands = validate_and_prepare_master_data(df, dry_run=True)

    assert report.error_rows_count == 1
    assert report.errors_by_type.get("MISSING_REQUIRED_VALUE") == 1
    assert report.warning_rows_count == 1
    assert len(cands) == 0


def test_live_import_gate_allows_dob_warnings_but_blocks_errors(sample_row):
    """Live import gate allows DOB warnings to proceed to conflict check, but blocks on errors."""
    mock_supabase = MagicMock()
    # No DB conflicts
    mock_supabase.table.return_value.select.return_value.in_.return_value.execute.return_value.data = []

    # Case A: Only DOB warnings -> reaches conflict check and succeeds
    row_dob_warn = dict(sample_row)
    row_dob_warn["DateOfBirth"] = "1196-02-14"
    df_warn = pd.DataFrame([row_dob_warn])

    report, centres, batches, candidates = validate_and_prepare_master_data(df_warn, dry_run=False)
    assert report.error_rows_count == 0
    assert report.warning_rows_count == 1

    # Conflict check is reached without blocking
    from app.services.master_importer import check_database_conflicts
    conflicts = check_database_conflicts(centres, batches, candidates, mock_supabase)
    assert len(conflicts) == 0

    # Case B: Blocking error present (missing Candidate_ID) -> gate must abort before live writes
    row_bad = dict(sample_row)
    del row_bad["Candidate_ID"]
    df_err = pd.DataFrame([row_bad])

    report_err, _, _, _ = validate_and_prepare_master_data(df_err, dry_run=False)
    assert report_err.error_rows_count > 0

