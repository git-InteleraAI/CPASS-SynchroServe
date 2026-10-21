"""Read-only audit script for DDUGKY ALL STATES MASTER DATA.csv and Supabase database.
"""

import csv
import json
from collections import Counter
from pathlib import Path
import pandas as pd

CSV_PATH = Path("..") / "DDUGKY ALL STATES MASTER DATA.csv"

def audit_csv():
    print("=" * 60)
    print("PHASE 1: CSV FILE AUDIT")
    print("=" * 60)

    # 1. Raw header inspection
    with open(CSV_PATH, "r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.reader(f)
        raw_headers = next(reader)
        row_count = sum(1 for _ in reader)

    print(f"Total CSV Data Rows: {row_count}")
    print(f"Total Raw Header Columns: {len(raw_headers)}")

    # Duplicate headers
    header_counts = Counter(raw_headers)
    dups = {k: v for k, v in header_counts.items() if v > 1}
    print(f"\nDuplicate Header Names: {dups}")

    print("\nHeaders around PPS and Date (indices 66 to 75):")
    for i in range(66, min(76, len(raw_headers))):
        print(f"  Index {i:2d}: {repr(raw_headers[i])}")

    # 2. Pandas loading with keep_default_na=False to see exact raw strings
    df = pd.read_csv(CSV_PATH, dtype=str, encoding="utf-8-sig", keep_default_na=False)

    # Candidate identifier check
    cid_col = "Candidate_ID"
    if cid_col in df.columns:
        cids = df[cid_col].str.strip()
        print(f"\nCandidate_ID:")
        print(f"  Total non-empty: {(cids != '').sum()}")
        print(f"  Total unique:    {cids.nunique()}")
        print(f"  Blanks:          {(cids == '').sum()}")
        dup_cids = cids[cids.duplicated(keep=False)]
        print(f"  Duplicate Candidate_IDs: {len(dup_cids)}")

    # Training Centres
    tc_id_col = "TC_id"
    tc_name_col = "TC_Name"
    tc_mpr_col = "TC_MPR_ID"
    state_col = "TC_State_Name"

    print("\nTraining Centres Analysis:")
    if tc_id_col in df.columns:
        tc_ids = df[tc_id_col].str.strip()
        print(f"  Distinct {tc_id_col}: {tc_ids.nunique()} (Blanks: {(tc_ids == '').sum()})")
        print(f"  Unique values: {sorted([int(x) for x in tc_ids.unique() if x.isdigit()])}")

    if tc_name_col in df.columns:
        tc_names = df[tc_name_col].str.strip()
        print(f"  Distinct {tc_name_col}: {tc_names.nunique()} (Blanks: {(tc_names == '').sum()})")

    if tc_mpr_col in df.columns:
        tc_mprs = df[tc_mpr_col].str.strip()
        print(f"  Distinct {tc_mpr_col}: {tc_mprs.nunique()} (Blanks: {(tc_mprs == '').sum()})")

    if state_col in df.columns:
        states = df[state_col].str.strip()
        print(f"  Distinct {state_col}: {states.nunique()} (Blanks: {(states == '').sum()})")
        print(f"  State values: {sorted(states.unique())}")

    # Check mapping between TC_id and TC_Name
    tc_map = df[[tc_id_col, tc_name_col]].drop_duplicates()
    print(f"  Distinct ({tc_id_col}, {tc_name_col}) pairs: {len(tc_map)}")
    for _, r in tc_map.iterrows():
        print(f"    TC_id {r[tc_id_col]} -> {r[tc_name_col]}")

    # Batches
    kb_batch_col = "KB_Batch_ID"
    batch_code_col = "Batch_Code"

    print("\nBatches Analysis:")
    if kb_batch_col in df.columns:
        kb_batches = df[kb_batch_col].str.strip()
        print(f"  Distinct {kb_batch_col}: {kb_batches.nunique()} (Blanks: {(kb_batches == '').sum()})")

    if batch_code_col in df.columns:
        batch_codes = df[batch_code_col].str.strip()
        print(f"  Distinct {batch_code_col}: {batch_codes.nunique()} (Blanks: {(batch_codes == '').sum()})")

    # Combinations
    combos_tc_kb = df[[tc_id_col, kb_batch_col]].drop_duplicates()
    print(f"  Distinct ({tc_id_col}, {kb_batch_col}) combinations: {len(combos_tc_kb)}")

    combos_tc_code = df[[tc_id_col, batch_code_col]].drop_duplicates()
    print(f"  Distinct ({tc_id_col}, {batch_code_col}) combinations: {len(combos_tc_code)}")

    # Check if Batch_Code repeats across different KB_Batch_IDs or TCs
    batch_code_to_kb = df[[batch_code_col, kb_batch_col]].drop_duplicates()
    code_counts = batch_code_to_kb[batch_code_col].value_counts()
    reused_codes = code_counts[code_counts > 1]
    print(f"  Batch_Codes mapped to >1 KB_Batch_ID: {len(reused_codes)}")
    if len(reused_codes) > 0:
        print(f"    Sample reused Batch_Codes across different batches: {dict(reused_codes.head(5))}")

    # Check Sanction Orders
    so_col = "Sanction_order_Number"
    if so_col in df.columns:
        sos = df[so_col].str.strip()
        print(f"\nSanction Orders ({so_col}):")
        print(f"  Distinct: {sos.nunique()} (Blanks: {(sos == '').sum()})")
        print(f"  Values: {sorted(sos.unique())}")

    # Check Special / Sentinel / Malformed values across all columns
    print("\nSentinel Values & Nulls Analysis:")
    na_sentinels = ["#N/A", "N/A", "NA", "NULL", "NaN", "None", "-"]
    found_sentinels = {}
    for col in df.columns:
        counts = {}
        for s in na_sentinels:
            c = (df[col].str.upper() == s).sum()
            if c > 0:
                counts[s] = int(c)
        if counts:
            found_sentinels[col] = counts
    print(f"  Columns with explicit sentinel tokens (#N/A, NA, etc.): {len(found_sentinels)}")
    for col, counts in list(found_sentinels.items())[:10]:
        print(f"    {col}: {counts}")

    # State breakdown
    print("\n--- Breakdown by TC_State_Name ---")
    for state, g in df.groupby("TC_State_Name"):
        print(f"  State: {state:16s} | Rows: {len(g):4d} | Distinct TC_id: {g['TC_id'].nunique():2d} | Distinct KB_Batch_ID: {g['KB_Batch_ID'].nunique():3d}")

    # Check migration 0001 / legacy tables in Supabase
    print("\n--- Supabase Database State ---")
    try:
        from app.db import supabase
        for tbl in ["ddugky_candidates", "candidate_documents", "profiles", "training_centres", "batches", "candidates", "duplicate_cases", "duplicate_candidate_links"]:
            try:
                res = supabase.table(tbl).select("count", count="exact").execute()
                print(f"  Table '{tbl}': {res.count} rows")
            except Exception as e:
                print(f"  Table '{tbl}': Does not exist or error ({e})")
    except Exception as e:
        print(f"  Could not connect to Supabase: {e}")

if __name__ == "__main__":
    audit_csv()
