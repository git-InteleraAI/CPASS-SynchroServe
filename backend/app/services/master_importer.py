"""Master data import engine for CPASS.

Supports CSV and Excel files, enforces strict validations, detects duplicate
candidate IDs and conflicting entity mappings without silent overrides,
preserves all source data in candidates.raw, and ensures safe dry-run operations.
"""

from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable
import json

import pandas as pd

REQUIRED_COLUMNS = [
    "Candidate_ID",
    "TC_id",
    "KB_Batch_ID",
]

RECOMMENDED_COLUMNS = [
    "TC_Name",
    "Candidate_First_Name",
    "DateOfBirth",
]

DEFAULT_STATE_COLUMN = "TC_State_Name"
CHUNK_SIZE = 500


@dataclass
class ValidationError:
    row: int
    field: str
    error_type: str
    message: str
    candidate_id: int | None = None
    raw_value: Any = None


@dataclass
class ValidationWarning:
    row: int
    field: str
    warning_type: str = "INVALID_DOB"
    message: str = ""
    candidate_id: int | None = None
    raw_value: Any = None
    reason: str | None = None
    error_type: str | None = None

    def __post_init__(self):
        if self.error_type and not self.warning_type:
            self.warning_type = self.error_type
        if self.reason is None:
            self.reason = self.message
        elif not self.message:
            self.message = self.reason
        if self.error_type is None:
            self.error_type = self.warning_type


@dataclass
class ValidationReport:
    total_rows_read: int = 0
    valid_rows_count: int = 0
    error_rows_count: int = 0
    warning_rows_count: int = 0
    errors_by_type: dict[str, int] = field(default_factory=dict)
    warnings_by_type: dict[str, int] = field(default_factory=dict)
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationWarning] = field(default_factory=list)
    unique_centres_count: int = 0
    unique_batches_count: int = 0
    unique_candidates_count: int = 0
    dry_run: bool = True
    database_written: bool = False

    @property
    def warnings_count(self) -> int:
        return len(self.warnings)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def clean_val(v: Any) -> str | None:
    """Normalize cell values to stripped string or None."""
    if v is None:
        return None
    if not isinstance(v, (list, dict)) and pd.isna(v):
        return None
    s = str(v).strip()
    return s if s != "" else None


def to_int(v: Any) -> int | None:
    """Parse integer from string/float representation safely."""
    cleaned = clean_val(v)
    if cleaned is None:
        return None
    try:
        # Handles "123", "123.0", etc.
        f = float(cleaned)
        if f.is_integer():
            return int(f)
        return None
    except (ValueError, TypeError):
        return None


def parse_and_validate_date(
    v: Any,
    field_name: str,
    min_year: int = 1940,
    max_year: int = 2035,
    required: bool = False,
) -> tuple[str | None, str | None]:
    """Parse date and validate year range.

    Returns:
        (iso_date_string or None, error_message or None)
    """
    cleaned = clean_val(v)
    if cleaned is None:
        if required:
            return None, f"Missing required date for {field_name}"
        return None, None

    try:
        parsed = pd.to_datetime(cleaned, errors="coerce", format="mixed", dayfirst=True)
    except Exception as e:
        return None, f"Failed to parse date for {field_name}: '{cleaned}' ({e})"

    if pd.isna(parsed):
        return None, f"Invalid date format for {field_name}: '{cleaned}'"

    d: date = parsed.date()
    if d.year < min_year or d.year > max_year:
        return (
            None,
            f"Date out of valid range ({min_year}-{max_year}) for {field_name}: '{cleaned}' (parsed as year {d.year})",
        )

    return d.isoformat(), None


def load_dataframe(file_path: Path | str) -> pd.DataFrame:
    """Read CSV or Excel into a pandas DataFrame with string types preserved."""
    p = Path(file_path)
    if not p.is_file():
        raise FileNotFoundError(f"Source file not found: {p}")

    suffix = p.suffix.lower()
    if suffix == ".csv":
        # Using utf-8 with replace to handle non-ascii or corrupted characters gracefully
        return pd.read_csv(
            p,
            dtype=object,
            keep_default_na=False,
            encoding_errors="replace",
        )
    elif suffix in {".xlsx", ".xls"}:
        return pd.read_excel(
            p,
            dtype=object,
            keep_default_na=False,
        )
    else:
        raise ValueError(f"Unsupported file format '{suffix}'. Use .csv, .xlsx, or .xls.")


def validate_and_prepare_master_data(
    df: pd.DataFrame,
    state_column: str = DEFAULT_STATE_COLUMN,
    dry_run: bool = True,
) -> tuple[ValidationReport, list[dict], list[dict], list[dict]]:
    """Validate master data, detect duplicate IDs and conflicting mappings,

    and prepare records for training_centres, batches, and candidates.

    Returns:
        (report, centres_list, batches_list, candidates_list)
    """
    report = ValidationReport(
        total_rows_read=len(df),
        dry_run=dry_run,
        database_written=False,
    )

    # 1. Validate required columns
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        for col in missing_cols:
            err = ValidationError(
                row=1,
                field=col,
                error_type="MISSING_REQUIRED_COLUMN",
                message=f"Required column '{col}' is missing from the input file.",
            )
            report.errors.append(err)
            report.errors_by_type["MISSING_REQUIRED_COLUMN"] = (
                report.errors_by_type.get("MISSING_REQUIRED_COLUMN", 0) + 1
            )
        report.error_rows_count = len(report.errors)
        return report, [], [], []

    # Choose state column fallback if configured column is missing
    actual_state_col = state_column if state_column in df.columns else "State_Name"

    seen_candidate_rows: dict[int, int] = {}
    seen_candidate_data: dict[int, dict] = {}
    centres_by_id: dict[int, dict[str, Any]] = {}
    centre_first_row: dict[int, int] = {}
    batches_by_id: dict[int, dict[str, Any]] = {}
    batch_first_row: dict[int, int] = {}
    candidates_list: list[dict[str, Any]] = []

    for idx, r in df.iterrows():
        # Source row index (1-based row in CSV/Excel, where row 1 is header, row 2 is first data row)
        row_num = int(idx) + 2
        row_errors: list[ValidationError] = []

        raw_cid = r.get("Candidate_ID")
        raw_tcid = r.get("TC_id")
        raw_kbid = r.get("KB_Batch_ID")

        cid = to_int(raw_cid)
        tcid = to_int(raw_tcid)
        kbid = to_int(raw_kbid)

        # Validate required identifiers
        if cid is None:
            row_errors.append(
                ValidationError(
                    row=row_num,
                    field="Candidate_ID",
                    error_type="MISSING_REQUIRED_VALUE",
                    message="Missing or invalid integer Candidate_ID.",
                    raw_value=raw_cid,
                )
            )
        if tcid is None:
            row_errors.append(
                ValidationError(
                    row=row_num,
                    field="TC_id",
                    error_type="MISSING_REQUIRED_VALUE",
                    message="Missing or invalid integer TC_id.",
                    raw_value=raw_tcid,
                    candidate_id=cid,
                )
            )
        if kbid is None:
            row_errors.append(
                ValidationError(
                    row=row_num,
                    field="KB_Batch_ID",
                    error_type="MISSING_REQUIRED_VALUE",
                    message="Missing or invalid integer KB_Batch_ID.",
                    raw_value=raw_kbid,
                    candidate_id=cid,
                )
            )

        # Validate dates
        dob_iso, dob_err = parse_and_validate_date(
            r.get("DateOfBirth"),
            "DateOfBirth",
            min_year=1940,
            max_year=2020,
            required=False,
        )
        if dob_err:
            dob_iso = None
            warn = ValidationWarning(
                row=row_num,
                field="DateOfBirth",
                warning_type="INVALID_DOB",
                message=dob_err,
                candidate_id=cid,
                raw_value=r.get("DateOfBirth"),
                reason=dob_err,
            )
            report.warnings.append(warn)
            report.warnings_by_type[warn.warning_type] = (
                report.warnings_by_type.get(warn.warning_type, 0) + 1
            )

        start_date_iso, start_date_err = parse_and_validate_date(
            r.get("Batch_Startdate"),
            "Batch_Startdate",
            min_year=2000,
            max_year=2050,
            required=False,
        )
        if start_date_err:
            row_errors.append(
                ValidationError(
                    row=row_num,
                    field="Batch_Startdate",
                    error_type="INVALID_DATE",
                    message=start_date_err,
                    candidate_id=cid,
                    raw_value=r.get("Batch_Startdate"),
                )
            )

        end_date_iso, end_date_err = parse_and_validate_date(
            r.get("Batch_Enddate"),
            "Batch_Enddate",
            min_year=2000,
            max_year=2050,
            required=False,
        )
        if end_date_err:
            row_errors.append(
                ValidationError(
                    row=row_num,
                    field="Batch_Enddate",
                    error_type="INVALID_DATE",
                    message=end_date_err,
                    candidate_id=cid,
                    raw_value=r.get("Batch_Enddate"),
                )
            )

        # If any fatal row error occurred so far, record and skip entity aggregation for this row
        if row_errors:
            for err in row_errors:
                report.errors.append(err)
                report.errors_by_type[err.error_type] = (
                    report.errors_by_type.get(err.error_type, 0) + 1
                )
            continue

        # Check duplicate Candidate_ID
        assert cid is not None
        if cid in seen_candidate_rows:
            prev_row = seen_candidate_rows[cid]
            err = ValidationError(
                row=row_num,
                field="Candidate_ID",
                error_type="DUPLICATE_CANDIDATE_ID",
                message=f"Duplicate Candidate_ID {cid} at row {row_num} (first seen at row {prev_row}).",
                candidate_id=cid,
                raw_value=raw_cid,
            )
            report.errors.append(err)
            report.errors_by_type["DUPLICATE_CANDIDATE_ID"] = (
                report.errors_by_type.get("DUPLICATE_CANDIDATE_ID", 0) + 1
            )
            continue
        seen_candidate_rows[cid] = row_num

        # Check TC mapping conflicts
        assert tcid is not None
        tc_entry = {
            "tc_id": tcid,
            "name": clean_val(r.get("TC_Name")) or f"TC {tcid}",
            "state_name": clean_val(r.get(actual_state_col)),
            "district_name": clean_val(r.get("TC_District_Name")),
            "mpr_id": clean_val(r.get("TC_MPR_ID")),
        }
        if tcid in centres_by_id:
            existing = centres_by_id[tcid]
            # Check for conflict in attributes
            conflicts = []
            for k in ["name", "state_name", "district_name", "mpr_id"]:
                if existing[k] != tc_entry[k]:
                    conflicts.append(f"{k} ('{existing[k]}' vs '{tc_entry[k]}')")
            if conflicts:
                err = ValidationError(
                    row=row_num,
                    field="TC_id",
                    error_type="CONFLICTING_TC_MAPPING",
                    message=f"Conflicting TC mapping for TC_id {tcid} at row {row_num} (first defined at row {centre_first_row[tcid]}): {', '.join(conflicts)}",
                    candidate_id=cid,
                    raw_value=raw_tcid,
                )
                report.errors.append(err)
                report.errors_by_type["CONFLICTING_TC_MAPPING"] = (
                    report.errors_by_type.get("CONFLICTING_TC_MAPPING", 0) + 1
                )
                continue
        else:
            centres_by_id[tcid] = tc_entry
            centre_first_row[tcid] = row_num

        # Check KB_Batch mapping conflicts
        assert kbid is not None
        batch_entry = {
            "kb_batch_id": kbid,
            "batch_code": clean_val(r.get("Batch_Code")),
            "tc_id": tcid,
            "sanction_order": clean_val(r.get("Sanction_order_Number")),
            "trade_name": clean_val(r.get("Trade_Name")),
            "start_date": start_date_iso,
            "end_date": end_date_iso,
        }
        if kbid in batches_by_id:
            existing_b = batches_by_id[kbid]
            b_conflicts = []
            for k in [
                "tc_id",
                "batch_code",
                "sanction_order",
                "trade_name",
                "start_date",
                "end_date",
            ]:
                if existing_b[k] != batch_entry[k]:
                    b_conflicts.append(
                        f"{k} ('{existing_b[k]}' vs '{batch_entry[k]}')"
                    )
            if b_conflicts:
                err = ValidationError(
                    row=row_num,
                    field="KB_Batch_ID",
                    error_type="CONFLICTING_BATCH_MAPPING",
                    message=f"Conflicting batch mapping for KB_Batch_ID {kbid} at row {row_num} (first defined at row {batch_first_row[kbid]}): {', '.join(b_conflicts)}",
                    candidate_id=cid,
                    raw_value=raw_kbid,
                )
                report.errors.append(err)
                report.errors_by_type["CONFLICTING_BATCH_MAPPING"] = (
                    report.errors_by_type.get("CONFLICTING_BATCH_MAPPING", 0) + 1
                )
                continue
        else:
            batches_by_id[kbid] = batch_entry
            batch_first_row[kbid] = row_num

        # Candidate record - preserving ALL original source columns in raw
        raw_row_data = {str(k): clean_val(v) for k, v in r.items()}
        cand_entry = {
            "candidate_id": cid,
            "kb_batch_id": kbid,
            "state_name": clean_val(r.get("State_Name")),
            "first_name": clean_val(r.get("Candidate_First_Name")),
            "last_name": clean_val(r.get("Candidate_Last_Name")),
            "father_name": clean_val(r.get("Candidate_FatherName")),
            "gender": clean_val(r.get("Gender")),
            "dob": dob_iso,
            "mobile": clean_val(r.get("Mobile_Number")),
            "appointed": (clean_val(r.get("Appointed")) or "").upper() == "YES",
            "employer_name": clean_val(r.get("EmployerName")),
            "raw": raw_row_data,
        }
        candidates_list.append(cand_entry)

    report.valid_rows_count = len(candidates_list)
    report.error_rows_count = len(report.errors)
    report.warning_rows_count = len(report.warnings)
    report.unique_centres_count = len(centres_by_id)
    report.unique_batches_count = len(batches_by_id)
    report.unique_candidates_count = len(candidates_list)

    return (
        report,
        list(centres_by_id.values()),
        list(batches_by_id.values()),
        candidates_list,
    )


def execute_upserts(
    centres: list[dict],
    batches: list[dict],
    candidates: list[dict],
    supabase_client: Any,
    chunk_size: int = CHUNK_SIZE,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> None:
    """Execute upserts in dependency order:

    1. training_centres
    2. batches
    3. candidates
    """

    def _chunked_upsert(table: str, rows: list[dict], on_conflict: str):
        total = len(rows)
        for i in range(0, total, chunk_size):
            chunk = rows[i : i + chunk_size]
            supabase_client.table(table).upsert(chunk, on_conflict=on_conflict).execute()
            if progress_callback:
                progress_callback(table, min(i + chunk_size, total), total)

    # 1. training centres
    _chunked_upsert("training_centres", centres, "tc_id")
    # 2. batches
    _chunked_upsert("batches", batches, "kb_batch_id")
    # 3. candidates
    _chunked_upsert("candidates", candidates, "candidate_id")


def check_database_conflicts(
    centres: list[dict],
    batches: list[dict],
    candidates: list[dict],
    supabase_client: Any,
    chunk_size: int = CHUNK_SIZE,
) -> list[str]:
    """Check incoming records against existing database records to prevent silent overwrites.

    Allows identical or complementary repeat imports, but reports conflicts if incoming records
    attempt to overwrite existing primary entities with conflicting data.
    """
    conflicts: list[str] = []

    # 1. Check existing training centres
    tc_map = {c["tc_id"]: c for c in centres}
    tc_ids = list(tc_map.keys())
    for i in range(0, len(tc_ids), chunk_size):
        chunk_ids = tc_ids[i : i + chunk_size]
        res = supabase_client.table("training_centres").select("tc_id,name,state_name,district_name,mpr_id").in_("tc_id", chunk_ids).execute()
        for db_tc in (res.data or []):
            inc = tc_map.get(db_tc["tc_id"])
            if inc:
                diffs = []
                for k in ["name", "state_name", "district_name"]:
                    if inc.get(k) and db_tc.get(k) and str(inc[k]).strip().lower() != str(db_tc[k]).strip().lower():
                        diffs.append(f"{k} (DB='{db_tc[k]}' vs incoming='{inc[k]}')")
                if diffs:
                    conflicts.append(f"Training centre TC_id {db_tc['tc_id']} conflicts with existing database record: {', '.join(diffs)}")

    # 2. Check existing batches
    b_map = {b["kb_batch_id"]: b for b in batches}
    b_ids = list(b_map.keys())
    for i in range(0, len(b_ids), chunk_size):
        chunk_ids = b_ids[i : i + chunk_size]
        res = supabase_client.table("batches").select("kb_batch_id,tc_id,batch_code,sanction_order").in_("kb_batch_id", chunk_ids).execute()
        for db_b in (res.data or []):
            inc = b_map.get(db_b["kb_batch_id"])
            if inc:
                diffs = []
                if inc.get("tc_id") != db_b.get("tc_id"):
                    diffs.append(f"tc_id (DB={db_b.get('tc_id')} vs incoming={inc.get('tc_id')})")
                if inc.get("batch_code") and db_b.get("batch_code") and str(inc["batch_code"]).strip().lower() != str(db_b["batch_code"]).strip().lower():
                    diffs.append(f"batch_code (DB='{db_b.get('batch_code')}' vs incoming='{inc.get('batch_code')}')")
                if diffs:
                    conflicts.append(f"Batch KB_Batch_ID {db_b['kb_batch_id']} conflicts with existing database record: {', '.join(diffs)}")

    # 3. Check existing candidates
    cand_map = {c["candidate_id"]: c for c in candidates}
    c_ids = list(cand_map.keys())
    for i in range(0, len(c_ids), chunk_size):
        chunk_ids = c_ids[i : i + chunk_size]
        res = supabase_client.table("candidates").select("candidate_id,first_name,last_name,dob,father_name").in_("candidate_id", chunk_ids).execute()
        for db_c in (res.data or []):
            inc = cand_map.get(db_c["candidate_id"])
            if inc:
                diffs = []
                for k in ["first_name", "last_name", "father_name"]:
                    if inc.get(k) and db_c.get(k) and str(inc[k]).strip().lower() != str(db_c[k]).strip().lower():
                        diffs.append(f"{k} (DB='{db_c.get(k)}' vs incoming='{inc.get(k)}')")
                if inc.get("dob") and db_c.get("dob") and str(inc["dob"]) != str(db_c["dob"]):
                    diffs.append(f"dob (DB='{db_c.get('dob')}' vs incoming='{inc.get('dob')}')")
                if diffs:
                    conflicts.append(f"Candidate Candidate_ID {db_c['candidate_id']} conflicts with existing database record: {', '.join(diffs)}")

    return conflicts


# ==============================================================================
# Two-Table Model: ddugky_candidates mappings & import functions
# ==============================================================================

DDUGKY_COLUMN_MAP: dict[str, str] = {
    "Sl.No": "sl_no",
    "Candidate_ID": "candidate_id",
    "KaushalPanjee_ID": "kaushal_panjee_id",
    "State_Name": "state_name",
    "District_Name": "district_name",
    "Block_Name": "block_name",
    "Sanction_order_Number": "sanction_order_number",
    "KB_Project_ID": "kb_project_id",
    "Permenent_Address_village": "permanent_address_village",
    "Permenent_Pincode": "permanent_pincode",
    "Candidate_Email": "candidate_email",
    "Candidate_Qualification": "candidate_qualification",
    "Candidate_FatherName": "candidate_father_name",
    "MPR_ProjectID": "mpr_project_id",
    "TC_Name": "tc_name",
    "TC_MPR_ID": "tc_mpr_id",
    "TC_id": "tc_id",
    "TC_State_Name": "tc_state_name",
    "TC_District_Name": "tc_district_name",
    "Parliamentary_Constituency_Name": "parliamentary_constituency_name",
    "Assembly_Constituency_Name": "assembly_constituency_name",
    "KB_Batch_ID": "kb_batch_id",
    "Batch_MPR_ID": "batch_mpr_id",
    "Batch_Code": "batch_code",
    "Batch_Startdate": "batch_start_date",
    "Batch_Enddate": "batch_end_date",
    "Candidate_MPR_ID": "candidate_mpr_id",
    "Candidate_First_Name": "candidate_first_name",
    "Candidate_Last_Name": "candidate_last_name",
    "Gender": "gender",
    "Category": "category",
    "PWD": "pwd",
    "Minority": "minority",
    "Trade_Name": "trade_name",
    "Trade_Code": "trade_code",
    "sector": "sector",
    "Religion": "religion",
    "DateOfBirth": "date_of_birth",
    "Mobile_Number": "mobile_number",
    "NatureofTraining": "nature_of_training",
    "Aadhar": "aadhar",
    "Bank_Account": "bank_account",
    "house_number": "house_number",
    "Permenant_address": "permanent_address",
    "Trained": "trained",
    "Dropout Status": "dropout_status",
    "Assessed_Date": "assessed_date",
    "Certified Status": "certified_status",
    "Certified_Date": "certified_date",
    "Appointed": "appointed",
    "EmployerName": "employer_name",
    "EmployerWorkplacelocation": "employer_workplace_location",
    "Workplacecontactdetails": "workplace_contact_details",
    "monthly_ctc": "monthly_ctc",
    "gross_salary": "gross_salary",
    "net_salary": "net_salary",
    "joining_date": "joining_date",
    "EmployerState": "employer_state",
    "EmployerDistrict": "employer_district",
    "Work place State": "work_place_state",
    "Work place District": "work_place_district",
    "Appointment Letter": "appointment_letter_ref",
    "BS1": "bs1",
    "BS2": "bs2",
    "BS3": "bs3",
    "PS1": "ps1",
    "PS2": "ps2",
    "PS3": "ps3",
    "PPS 1": "pps_1",
    "Date": "pps_1_date",
    "PPS 2": "pps_2",
    "Date.1": "pps_2_date",
    "PPS 3": "pps_3",
    "Date.2": "pps_3_date",
    "TP3 Uploaded": "tp3_uploaded",
    "Verified in KB": "verified_in_kb",
}


def to_float(v: Any) -> float | None:
    """Safely convert numeric string/number to float or None."""
    cleaned = clean_val(v)
    if cleaned is None:
        return None
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def map_row_to_ddugky_candidate(r: dict[str, Any], row_num: int) -> tuple[dict[str, Any] | None, list[ValidationError], list[ValidationWarning]]:
    """Map a single row from pandas DataFrame into ddugky_candidates format.

    Preserves all 76 columns, stores full row in raw_data, and preserves leading zeros.
    """
    errors: list[ValidationError] = []
    warnings: list[ValidationWarning] = []

    raw_cid = r.get("Candidate_ID")
    cid = to_int(raw_cid)
    if cid is None:
        errors.append(
            ValidationError(
                row=row_num,
                field="Candidate_ID",
                error_type="MISSING_REQUIRED_VALUE",
                message="Missing or invalid integer Candidate_ID.",
                raw_value=raw_cid,
            )
        )
        return None, errors, warnings

    dob_iso, dob_err = parse_and_validate_date(
        r.get("DateOfBirth"),
        "DateOfBirth",
        min_year=1940,
        max_year=2020,
        required=False,
    )
    if dob_err:
        dob_iso = None
        warnings.append(
            ValidationWarning(
                row=row_num,
                field="DateOfBirth",
                warning_type="INVALID_DOB",
                message=dob_err,
                candidate_id=cid,
                raw_value=r.get("DateOfBirth"),
                reason=dob_err,
            )
        )

    start_date_iso, _ = parse_and_validate_date(
        r.get("Batch_Startdate"),
        "Batch_Startdate",
        min_year=2000,
        max_year=2050,
        required=False,
    )
    end_date_iso, _ = parse_and_validate_date(
        r.get("Batch_Enddate"),
        "Batch_Enddate",
        min_year=2000,
        max_year=2050,
        required=False,
    )

    raw_dict = {str(k): clean_val(v) for k, v in r.items()}

    record: dict[str, Any] = {
        "candidate_id": cid,
        "sl_no": clean_val(r.get("Sl.No")),
        "kaushal_panjee_id": clean_val(r.get("KaushalPanjee_ID")),
        "state_name": clean_val(r.get("State_Name")),
        "district_name": clean_val(r.get("District_Name")),
        "block_name": clean_val(r.get("Block_Name")),
        "sanction_order_number": clean_val(r.get("Sanction_order_Number")),
        "kb_project_id": clean_val(r.get("KB_Project_ID")),
        "permanent_address_village": clean_val(r.get("Permenent_Address_village")),
        "permanent_pincode": clean_val(r.get("Permenent_Pincode")),
        "candidate_email": clean_val(r.get("Candidate_Email")),
        "candidate_qualification": clean_val(r.get("Candidate_Qualification")),
        "candidate_father_name": clean_val(r.get("Candidate_FatherName")),
        "mpr_project_id": clean_val(r.get("MPR_ProjectID")),
        "tc_name": clean_val(r.get("TC_Name")),
        "tc_mpr_id": clean_val(r.get("TC_MPR_ID")),
        "tc_id": to_int(r.get("TC_id")),
        "tc_state_name": clean_val(r.get("TC_State_Name")),
        "tc_district_name": clean_val(r.get("TC_District_Name")),
        "parliamentary_constituency_name": clean_val(r.get("Parliamentary_Constituency_Name")),
        "assembly_constituency_name": clean_val(r.get("Assembly_Constituency_Name")),
        "kb_batch_id": to_int(r.get("KB_Batch_ID")),
        "batch_mpr_id": clean_val(r.get("Batch_MPR_ID")),
        "batch_code": clean_val(r.get("Batch_Code")),
        "batch_start_date": start_date_iso,
        "batch_end_date": end_date_iso,
        "candidate_mpr_id": clean_val(r.get("Candidate_MPR_ID")),
        "candidate_first_name": clean_val(r.get("Candidate_First_Name")),
        "candidate_last_name": clean_val(r.get("Candidate_Last_Name")),
        "gender": clean_val(r.get("Gender")),
        "category": clean_val(r.get("Category")),
        "pwd": clean_val(r.get("PWD")),
        "minority": clean_val(r.get("Minority")),
        "trade_name": clean_val(r.get("Trade_Name")),
        "trade_code": clean_val(r.get("Trade_Code")),
        "sector": clean_val(r.get("sector")),
        "religion": clean_val(r.get("Religion")),
        "date_of_birth": dob_iso,
        "mobile_number": clean_val(r.get("Mobile_Number")),
        "nature_of_training": clean_val(r.get("NatureofTraining")),
        "aadhar": clean_val(r.get("Aadhar")),
        "bank_account": clean_val(r.get("Bank_Account")),
        "house_number": clean_val(r.get("house_number")),
        "permanent_address": clean_val(r.get("Permenant_address")),
        "trained": clean_val(r.get("Trained")),
        "dropout_status": clean_val(r.get("Dropout Status")),
        "assessed_date": clean_val(r.get("Assessed_Date")),
        "certified_status": clean_val(r.get("Certified Status")),
        "certified_date": clean_val(r.get("Certified_Date")),
        "appointed": (clean_val(r.get("Appointed")) or "").upper() == "YES",
        "employer_name": clean_val(r.get("EmployerName")),
        "employer_workplace_location": clean_val(r.get("EmployerWorkplacelocation")),
        "workplace_contact_details": clean_val(r.get("Workplacecontactdetails")),
        "monthly_ctc": to_float(r.get("monthly_ctc")),
        "gross_salary": to_float(r.get("gross_salary")),
        "net_salary": to_float(r.get("net_salary")),
        "joining_date": clean_val(r.get("joining_date")),
        "employer_state": clean_val(r.get("EmployerState")),
        "employer_district": clean_val(r.get("EmployerDistrict")),
        "work_place_state": clean_val(r.get("Work place State")),
        "work_place_district": clean_val(r.get("Work place District")),
        "appointment_letter_ref": clean_val(r.get("Appointment Letter")),
        "bs1": clean_val(r.get("BS1")),
        "bs2": clean_val(r.get("BS2")),
        "bs3": clean_val(r.get("BS3")),
        "ps1": clean_val(r.get("PS1")),
        "ps2": clean_val(r.get("PS2")),
        "ps3": clean_val(r.get("PS3")),
        "pps_1": clean_val(r.get("PPS 1")),
        "pps_1_date": clean_val(r.get("Date")),
        "pps_2": clean_val(r.get("PPS 2")),
        "pps_2_date": clean_val(r.get("Date.1")),
        "pps_3": clean_val(r.get("PPS 3")),
        "pps_3_date": clean_val(r.get("Date.2")),
        "tp3_uploaded": clean_val(r.get("TP3 Uploaded")),
        "verified_in_kb": clean_val(r.get("Verified in KB")),
        "raw_data": raw_dict,
    }
    return record, errors, warnings


def validate_and_prepare_ddugky_candidates(
    df: pd.DataFrame,
    dry_run: bool = True,
) -> tuple[ValidationReport, list[dict[str, Any]]]:
    """Validate all rows and prepare ddugky_candidates records.

    Preserves all 76 columns, handles duplicate Candidate_IDs with blocking error,
    and records invalid DOBs as warnings setting date_of_birth to None.
    """
    report = ValidationReport(
        total_rows_read=len(df),
        dry_run=dry_run,
        database_written=False,
    )

    if "Candidate_ID" not in df.columns:
        err = ValidationError(
            row=1,
            field="Candidate_ID",
            error_type="MISSING_REQUIRED_COLUMN",
            message="Required column 'Candidate_ID' is missing from the input file.",
        )
        report.errors.append(err)
        report.errors_by_type["MISSING_REQUIRED_COLUMN"] = 1
        report.error_rows_count = 1
        return report, []

    candidates: list[dict[str, Any]] = []
    seen_ids: dict[int, int] = {}
    unique_centres: set[int] = set()
    unique_batches: set[int] = set()

    for idx, r in df.iterrows():
        row_num = int(idx) + 2
        cand, errs, warns = map_row_to_ddugky_candidate(r.to_dict(), row_num)

        for w in warns:
            report.warnings.append(w)
            report.warnings_by_type[w.warning_type] = (
                report.warnings_by_type.get(w.warning_type, 0) + 1
            )

        if errs:
            for e in errs:
                report.errors.append(e)
                report.errors_by_type[e.error_type] = (
                    report.errors_by_type.get(e.error_type, 0) + 1
                )
            continue

        assert cand is not None
        cid = cand["candidate_id"]
        if cid in seen_ids:
            dup_err = ValidationError(
                row=row_num,
                field="Candidate_ID",
                error_type="DUPLICATE_CANDIDATE_ID",
                message=f"Duplicate Candidate_ID {cid} at row {row_num} (first seen at row {seen_ids[cid]}).",
                candidate_id=cid,
                raw_value=cid,
            )
            report.errors.append(dup_err)
            report.errors_by_type["DUPLICATE_CANDIDATE_ID"] = (
                report.errors_by_type.get("DUPLICATE_CANDIDATE_ID", 0) + 1
            )
            continue

        seen_ids[cid] = row_num
        if cand.get("tc_id"):
            unique_centres.add(cand["tc_id"])
        if cand.get("kb_batch_id"):
            unique_batches.add(cand["kb_batch_id"])

        candidates.append(cand)

    report.valid_rows_count = len(candidates)
    report.error_rows_count = len(report.errors)
    report.warning_rows_count = len(report.warnings)
    report.unique_centres_count = len(unique_centres)
    report.unique_batches_count = len(unique_batches)
    report.unique_candidates_count = len(candidates)

    return report, candidates


def execute_upserts_ddugky(
    candidates: list[dict[str, Any]],
    supabase_client: Any,
    chunk_size: int = CHUNK_SIZE,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> None:
    """Execute chunked upsert into ddugky_candidates table."""
    total = len(candidates)
    for i in range(0, total, chunk_size):
        chunk = candidates[i : i + chunk_size]
        supabase_client.table("ddugky_candidates").upsert(
            chunk, on_conflict="candidate_id"
        ).execute()
        if progress_callback:
            progress_callback("ddugky_candidates", min(i + chunk_size, total), total)


def check_database_conflicts_ddugky(
    candidates: list[dict[str, Any]],
    supabase_client: Any,
    chunk_size: int = CHUNK_SIZE,
) -> list[str]:
    """Check incoming candidate records against existing ddugky_candidates in Supabase.

    Detects conflicts if existing candidate has different name or DOB.
    """
    conflicts: list[str] = []
    cand_map = {c["candidate_id"]: c for c in candidates}
    c_ids = list(cand_map.keys())

    for i in range(0, len(c_ids), chunk_size):
        chunk_ids = c_ids[i : i + chunk_size]
        res = (
            supabase_client.table("ddugky_candidates")
            .select("candidate_id,candidate_first_name,candidate_last_name,date_of_birth,candidate_father_name")
            .in_("candidate_id", chunk_ids)
            .execute()
        )
        for db_c in (res.data or []):
            inc = cand_map.get(db_c["candidate_id"])
            if inc:
                diffs = []
                for k, db_k in [
                    ("candidate_first_name", "candidate_first_name"),
                    ("candidate_last_name", "candidate_last_name"),
                    ("candidate_father_name", "candidate_father_name"),
                ]:
                    if inc.get(k) and db_c.get(db_k) and str(inc[k]).strip().lower() != str(db_c[db_k]).strip().lower():
                        diffs.append(f"{k} (DB='{db_c[db_k]}' vs incoming='{inc[k]}')")
                if inc.get("date_of_birth") and db_c.get("date_of_birth") and str(inc["date_of_birth"]) != str(db_c["date_of_birth"]):
                    diffs.append(f"date_of_birth (DB='{db_c.get('date_of_birth')}' vs incoming='{inc.get('date_of_birth')}')")
                if diffs:
                    conflicts.append(f"Candidate {db_c['candidate_id']} conflicts with existing database record: {', '.join(diffs)}")

    return conflicts

