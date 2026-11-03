import sys, os
sys.path.insert(0, os.path.abspath('.'))

from app.db import supabase
from datetime import datetime, timezone

def test_sync():
    # Let's inspect a candidate in ddugky_candidates
    res = supabase.table("ddugky_candidates").select("candidate_id, tc_name, tc_state_name").limit(1).execute()
    print("Candidate sample:", res.data)

test_sync()

