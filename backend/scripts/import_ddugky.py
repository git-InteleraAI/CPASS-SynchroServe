"""Import the master CSV into the ddugky_candidates Supabase table.

Preserves all 9,084 rows and 76 source columns + raw_data JSONB.
Handles invalid DOBs with non-blocking warnings setting date_of_birth to NULL.
Idempotent upsert on candidate_id with pre-import database conflict checks.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.services.master_importer import (
    load_dataframe,
    validate_and_prepare_ddugky_candidates,
    check_database_conflicts_ddugky,
    execute_upserts_ddugky,
)


def print_report_summary(report_dict: dict) -> None:
    print("\n" + "=" * 65)
    print("DDUGKY MASTER DATA IMPORT VALIDATION REPORT")
    print("=" * 65)
    print(f"Total Rows Read:         {report_dict['total_rows_read']}")
    print(f"Valid Rows:              {report_dict['valid_rows_count']}")
    print(f"Blocking Errors:         {report_dict['error_rows_count']}")
    print(f"Warnings (Non-blocking): {report_dict.get('warning_rows_count', len(report_dict.get('warnings', [])))}")
    print(f"Unique Centres:          {report_dict['unique_centres_count']}")
    print(f"Unique Batches:          {report_dict['unique_batches_count']}")
    print(f"Unique Candidates:       {report_dict['unique_candidates_count']}")
    print(f"Dry Run Mode:            {report_dict['dry_run']}")
    print(f"Database Writes:         {report_dict['database_written']}")

    if report_dict.get("errors_by_type"):
        print("\nErrors by Category (Blocking):")
        for err_type, count in sorted(report_dict["errors_by_type"].items()):
            print(f"  - {err_type}: {count}")

    if report_dict.get("errors"):
        print("\nSample Errors (first 10):")
        for err in report_dict["errors"][:10]:
            cid_str = f" [Candidate_ID: {err['candidate_id']}]" if err.get("candidate_id") else ""
            print(f"  Row {err['row']}{cid_str} ({err['field']}): {err['message']}")

    if report_dict.get("warnings_by_type"):
        print("\nWarnings by Category (Non-blocking):")
        for warn_type, count in sorted(report_dict["warnings_by_type"].items()):
            print(f"  - {warn_type}: {count}")

    if report_dict.get("warnings"):
        print("\nSample Warnings (first 10):")
        for warn in report_dict["warnings"][:10]:
            cid_str = f" [Candidate_ID: {warn['candidate_id']}]" if warn.get("candidate_id") else ""
            print(f"  Row {warn['row']}{cid_str} ({warn['field']}): {warn['message']}")
        if len(report_dict["warnings"]) > 10:
            print(f"  ... and {len(report_dict['warnings']) - 10} more.")


def main():
    parser = argparse.ArgumentParser(description="CPASS DDUGKY Master Data Importer")
    parser.add_argument("input_file", help="Path to the master CSV or Excel file")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate input data and print report without writing to database",
    )
    parser.add_argument(
        "--report-out",
        default="ddugky_validation_report.json",
        help="Path to write detailed JSON error/validation report",
    )
    args = parser.parse_args()

    input_path = Path(args.input_file)
    print(f"Loading master file: {input_path.name}...")

    try:
        df = load_dataframe(input_path)
    except Exception as e:
        print(f"Error loading file: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Processing {len(df)} rows across {len(df.columns)} columns...")
    report, candidates = validate_and_prepare_ddugky_candidates(df, dry_run=args.dry_run)

    report_dict = report.to_dict()
    print_report_summary(report_dict)

    if report.errors or report.warnings:
        out_path = Path(args.report_out)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report_dict, f, indent=2)
        print(f"\nDetailed validation findings written to: {out_path.name}")

    if args.dry_run:
        if report.warnings:
            print(
                f"\n[NOTICE] {len(report.warnings)} candidate(s) have invalid DateOfBirth values and will be imported with date_of_birth = NULL; original values are preserved in candidates.raw_data."
            )
        print("\n[DRY RUN COMPLETE] Zero database writes performed.")
        return

    # If live import requested but fatal conflicts/errors exist:
    if report.error_rows_count > 0:
        print(
            "\n[ABORTED] Live import refused due to validation errors in source file.",
            file=sys.stderr,
        )
        sys.exit(1)

    if report.warnings:
        print(
            f"\n[WARNING] {len(report.warnings)} candidate(s) have invalid DateOfBirth values and will be imported with date_of_birth = NULL. Original values are preserved in candidates.raw_data."
        )

    from app.db import supabase

    print("\nChecking for conflicts against existing ddugky_candidates records...")
    db_conflicts = check_database_conflicts_ddugky(candidates, supabase)
    if db_conflicts:
        print(
            "\n[ABORTED] Live import refused due to conflicts with existing database records:",
            file=sys.stderr,
        )
        for c in db_conflicts[:10]:
            print(f"  - {c}", file=sys.stderr)
        sys.exit(1)

    print(f"\nExecuting live upsert of {len(candidates)} candidates into ddugky_candidates...")

    def progress(table, count, total):
        print(f"  {table}: {count}/{total} candidates upserted")

    execute_upserts_ddugky(candidates, supabase, progress_callback=progress)
    report.database_written = True
    print("\n[IMPORT SUCCESSFUL] All ddugky_candidates data upserted successfully.")


if __name__ == "__main__":
    main()
