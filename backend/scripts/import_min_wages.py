"""Import and validate statutory semi-skilled minimum wage revisions (2010-2026) into Supabase min_wages table.

Source: Minimum_Wages_Semi_Skilled_2010_2026.xlsx (Sheet: 'Semi-Skilled Wages (2010-2026)')
Total: 455 records (13 states x 35 effective periods).
Idempotent upsert on (state, effective_date, skill_category).
"""

from __future__ import annotations

import argparse
from datetime import date
import logging
from pathlib import Path
import sys
from typing import Any

import openpyxl

# Add backend directory to sys.path if not present
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.auth import resolve_state
from app.db import supabase

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cpass.min_wages_importer")

MONTH_NAME_TO_INT: dict[str, int] = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def parse_workbook(file_path: str | Path) -> list[dict[str, Any]]:
    """Parse main register in Excel workbook into structured, validated dictionaries."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Workbook not found at {path.resolve()}")

    wb = openpyxl.load_workbook(path, data_only=True)
    sheet_name = "Semi-Skilled Wages (2010-2026)"
    if sheet_name not in wb.sheetnames:
        raise ValueError(f"Required worksheet '{sheet_name}' not found. Available sheets: {wb.sheetnames}")

    ws = wb[sheet_name]
    records: list[dict[str, Any]] = []

    # Row 1 is header title, Row 2 is column labels: Sl.No., Month, Year, State, Minimum Wages (₹/Month)
    for r in range(3, ws.max_row + 1):
        sl_val = ws.cell(r, 1).value
        month_val = ws.cell(r, 2).value
        year_val = ws.cell(r, 3).value
        state_val = ws.cell(r, 4).value
        wage_val = ws.cell(r, 5).value

        if sl_val is None and month_val is None and state_val is None:
            continue

        if not month_val or not year_val or not state_val or wage_val is None:
            raise ValueError(f"Row {r} has missing mandatory fields: {sl_val}, {month_val}, {year_val}, {state_val}, {wage_val}")

        m_str = str(month_val).strip().lower()
        if m_str not in MONTH_NAME_TO_INT:
            raise ValueError(f"Row {r} has invalid month name: '{month_val}'")
        month_int = MONTH_NAME_TO_INT[m_str]

        try:
            year_int = int(year_val)
        except (ValueError, TypeError):
            raise ValueError(f"Row {r} has invalid year: '{year_val}'")

        try:
            wage_float = round(float(wage_val), 2)
        except (ValueError, TypeError):
            raise ValueError(f"Row {r} has non-numeric wage: '{wage_val}'")

        if wage_float <= 0:
            raise ValueError(f"Row {r} has non-positive wage: {wage_float}")

        raw_state = str(state_val).strip()
        canon_state = resolve_state(raw_state)
        if not canon_state:
            raise ValueError(f"Row {r} has unresolvable state name: '{raw_state}'")

        eff_date = f"{year_int:04d}-{month_int:02d}-01"

        record = {
            "state": canon_state,
            "month": month_int,
            "year": year_int,
            "effective_date": eff_date,
            "skill_category": "SEMI-SKILLED",
            "minimum_wage": wage_float,
            "source": "Minimum Wages Semi-Skilled Register (2010-2026)",
        }
        records.append(record)

    return records


def validate_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate completeness, uniqueness, and consistency of parsed wage records."""
    total_count = len(records)
    if total_count != 455:
        raise ValueError(f"Expected exactly 455 records, got {total_count}")

    states = sorted(list(set(r["state"] for r in records)))
    if len(states) != 13:
        raise ValueError(f"Expected exactly 13 distinct states, got {len(states)}: {states}")

    periods = sorted(list(set(r["effective_date"] for r in records)))
    if len(periods) != 35:
        raise ValueError(f"Expected exactly 35 distinct effective periods, got {len(periods)}")

    keys = set()
    for idx, r in enumerate(records):
        k = (r["state"], r["effective_date"], r["skill_category"])
        if k in keys:
            raise ValueError(f"Duplicate record detected at row index {idx}: {k}")
        keys.add(k)

    min_wage = min(r["minimum_wage"] for r in records)
    max_wage = max(r["minimum_wage"] for r in records)

    return {
        "total_records": total_count,
        "distinct_states": len(states),
        "states": states,
        "distinct_periods": len(periods),
        "earliest_date": periods[0],
        "latest_date": periods[-1],
        "min_wage": min_wage,
        "max_wage": max_wage,
    }


def execute_import(records: list[dict[str, Any]], batch_size: int = 100) -> int:
    """Upsert records into Supabase min_wages table in batches."""
    inserted = 0
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        res = (
            supabase.table("min_wages")
            .upsert(batch, on_conflict="state,effective_date,skill_category")
            .execute()
        )
        batch_written = len(res.data) if res and res.data else len(batch)
        inserted += batch_written
        logger.info("Upserted batch %d-%d (%d rows)", i + 1, min(i + batch_size, len(records)), batch_written)

    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Import semi-skilled minimum wages into Supabase")
    parser.add_argument(
        "--file",
        "-f",
        default="Minimum_Wages_Semi_Skilled_2010_2026.xlsx",
        help="Path to Minimum Wages Excel workbook",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate data without writing to database",
    )
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.is_file():
        # Try from repository root
        root_path = Path(__file__).resolve().parent.parent.parent / args.file
        if root_path.is_file():
            file_path = root_path

    logger.info("Parsing workbook: %s", file_path)
    records = parse_workbook(file_path)
    summary = validate_records(records)

    print("\n" + "=" * 60)
    print("MINIMUM WAGES REGISTER VALIDATION SUMMARY")
    print("=" * 60)
    print(f"Total Records:      {summary['total_records']}")
    print(f"Distinct States:    {summary['distinct_states']}")
    print(f"States:             {', '.join(summary['states'])}")
    print(f"Distinct Periods:   {summary['distinct_periods']}")
    print(f"Period Range:       {summary['earliest_date']} to {summary['latest_date']}")
    print(f"Minimum Wage:       ₹{summary['min_wage']:,.2f}")
    print(f"Maximum Wage:       ₹{summary['max_wage']:,.2f}")
    print("=" * 60 + "\n")

    if args.dry_run:
        logger.info("Dry-run mode enabled. Database writes skipped.")
        return

    logger.info("Writing %d records to Supabase min_wages table...", len(records))
    count = execute_import(records)
    logger.info("Successfully imported %d minimum wage records.", count)


if __name__ == "__main__":
    main()

