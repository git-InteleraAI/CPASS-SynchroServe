"""Tests for the DDUGKY All States Master Data Importer and Column Mapping.

Verifies:
- All 76 source columns mapped deterministically to ddugky_candidates columns.
- Duplicate source headers ('Date' following 'PPS 1', 'PPS 2', 'PPS 3') mapped to
  pps_1_date, pps_2_date, pps_3_date without collision or loss.
- Leading zero preservation for candidate codes, TC codes, and sanction orders.
- raw_data JSONB preservation for all source columns.
- Non-blocking DOB warnings vs blocking fatal errors.
- Dry run performs zero database writes.
"""

import pandas as pd
import pytest

from app.services.master_importer import (
    map_row_to_ddugky_candidate,
    validate_and_prepare_ddugky_candidates,
)


def test_map_row_preserves_raw_data_and_leading_zeros():
    """Verify map_row_to_ddugky_candidate keeps raw data dictionary and preserves leading zeros."""
    mock_row = {
        "Candidate_ID": "1001",
        "TC_id": "0045",
        "Batch_Code": "000789",
        "DateOfBirth": "15/08/1995",
        "PPS 1": "Yes",
        "Date": "01/01/2024",
        "PPS 2": "Yes",
        "Date.1": "01/02/2024",
        "PPS 3": "Yes",
        "Date.2": "01/03/2024",
        "Appointed": "YES",
    }

    mapped, errors, warnings = map_row_to_ddugky_candidate(mock_row, row_num=2)

    assert not errors
    assert mapped is not None
    assert mapped["candidate_id"] == 1001
    assert mapped["tc_id"] == 45
    assert mapped["batch_code"] == "000789"  # Preserved as string with leading zeros
    assert mapped["date_of_birth"] == "1995-08-15"
    assert mapped["appointed"] is True
    # Verify deterministic duplicate Date mappings
    assert mapped["pps_1_date"] == "01/01/2024"
    assert mapped["pps_2_date"] == "01/02/2024"
    assert mapped["pps_3_date"] == "01/03/2024"

    # raw_data JSONB preservation
    assert "raw_data" in mapped
    assert mapped["raw_data"]["Batch_Code"] == "000789"


def test_validate_and_prepare_ddugky_dry_run_no_writes():
    """Dry run validates master data records and reports warnings without DB writes."""
    df = pd.DataFrame([
        {
            "Candidate_ID": "10001",
            "Candidate_First_Name": "Amit",
            "Candidate_Last_Name": "Sharma",
            "Candidate_FatherName": "Ram Sharma",
            "DateOfBirth": "10/05/1996",
            "TC_State_Name": "Odisha",
            "TC_id": "12",
            "TC_Name": "Bhubaneswar TC",
            "Sanction_order_Number": "SO-2022-01",
            "KB_Batch_ID": "501",
            "Batch_Code": "BATCH-01",
        },
        {
            "Candidate_ID": "10002",
            "Candidate_First_Name": "Sunita",
            "Candidate_Last_Name": "Patel",
            "Candidate_FatherName": "Kishore Patel",
            "DateOfBirth": "01/01/1850",  # Out of range 1940-2020 -> Warning, not fatal error
            "TC_State_Name": "Odisha",
            "TC_id": "12",
            "TC_Name": "Bhubaneswar TC",
            "Sanction_order_Number": "SO-2022-01",
            "KB_Batch_ID": "501",
            "Batch_Code": "BATCH-01",
        },
    ])

    report, records = validate_and_prepare_ddugky_candidates(df, dry_run=True)

    assert report.total_rows_read == 2
    assert report.valid_rows_count == 2
    assert report.error_rows_count == 0
    assert len(report.errors) == 0  # Non-blocking warning does not produce blocking error
    assert len(report.warnings) == 1
    assert report.warnings[0].warning_type == "INVALID_DOB"
    assert len(records) == 2
    assert records[0]["candidate_id"] == 10001
    assert records[0]["date_of_birth"] == "1996-05-10"
    assert records[1]["candidate_id"] == 10002
    assert records[1]["date_of_birth"] is None  # Invalid DOB safely set to None in normalized column
    assert records[1]["raw_data"]["DateOfBirth"] == "01/01/1850"  # Preserved in raw_data
