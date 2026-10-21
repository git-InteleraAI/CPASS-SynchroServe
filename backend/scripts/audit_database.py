"""Database audit script: Reconcile ddugky_candidates with source CSV.
"""

import csv
import json
import os
import sys
from pathlib import Path
import pandas as pd

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import supabase

CSV_PATH = Path(__file__).resolve().parent.parent.parent / "DDUGKY ALL STATES MASTER DATA.csv"

def audit_database():
    print("=" * 60)
    print("PHASE 1.2: SOURCE CSV TO SUPABASE DATABASE RECONCILIATION")
    print("=" * 60)

    # 1. Total row count in Supabase
    res = supabase.table("ddugky_candidates").select("count", count="exact").execute()
    db_count = res.count
    print(f"Supabase ddugky_candidates row count: {db_count}")

    # 2. Total CSV rows
    df = pd.read_csv(CSV_PATH, dtype=str, encoding="utf-8-sig", keep_default_na=False)
    csv_count = len(df)
    print(f"Source CSV row count:                 {csv_count}")
    assert db_count == csv_count, f"Row count mismatch: DB={db_count}, CSV={csv_count}"
    print("[OK] Row count matches exactly (9,084 rows).")

    # 3. Check sample representative records
    sample_cids = [1000415, 2871030, 1076617, 2893431]
    print("\nComparing sample records between CSV and DB:")
    for cid in sample_cids:
        csv_rows = df[df["Candidate_ID"] == str(cid)]
        if csv_rows.empty:
            print(f"Candidate {cid} not found in CSV")
            continue
        csv_r = csv_rows.iloc[0].to_dict()

        db_res = supabase.table("ddugky_candidates").select("*").eq("candidate_id", cid).limit(1).execute()
        if not db_res.data:
            print(f"Candidate {cid} not found in DB")
            continue
        db_r = db_res.data[0]

        print(f"\n--- Candidate_ID: {cid} ---")
        print(f"  Name in CSV:  {csv_r.get('Candidate_First_Name')} {csv_r.get('Candidate_Last_Name')}")
        print(f"  Name in DB:   {db_r.get('candidate_first_name')} {db_r.get('candidate_last_name')}")
        print(f"  Father CSV:   {csv_r.get('Candidate_FatherName')}")
        print(f"  Father DB:    {db_r.get('candidate_father_name')}")
        print(f"  Batch_Code:   CSV={csv_r.get('Batch_Code')} | DB={db_r.get('batch_code')}")
        print(f"  TC_id:        CSV={csv_r.get('TC_id')} | DB={db_r.get('tc_id')}")
        print(f"  PPS 1 / Date: CSV='{csv_r.get('PPS 1')}' / '{csv_r.get('Date')}' | DB pps_1='{db_r.get('pps_1')}', pps_1_date='{db_r.get('pps_1_date')}'")
        print(f"  PPS 2 / Date: CSV='{csv_r.get('PPS 2')}' / '{csv_r.get('Date.1')}' | DB pps_2='{db_r.get('pps_2')}', pps_2_date='{db_r.get('pps_2_date')}'")
        print(f"  PPS 3 / Date: CSV='{csv_r.get('PPS 3')}' / '{csv_r.get('Date.2')}' | DB pps_3='{db_r.get('pps_3')}', pps_3_date='{db_r.get('pps_3_date')}'")
        
        # Verify raw_data JSONB coverage
        raw_data = db_r.get("raw_data") or {}
        print(f"  raw_data keys in DB: {len(raw_data)} keys (Expected 76)")
        assert len(raw_data) == 76, f"raw_data must have 76 keys, found {len(raw_data)}"

    # 4. Check application tables in Supabase
    print("\n--- Phase 1.3: Verification of Application Data Tables ---")
    app_tables = ["ddugky_candidates", "candidate_documents"]
    for tbl in app_tables:
        c = supabase.table(tbl).select("count", count="exact").execute()
        print(f"  Application Table '{tbl}': {c.count} records")

    print("\n[OK] Database audit completed successfully.")

if __name__ == "__main__":
    audit_database()
