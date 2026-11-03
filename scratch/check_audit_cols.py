import sys, os
sys.path.insert(0, os.path.abspath('.'))
from app.db import supabase

res = supabase.table("placement_audits").select("*").limit(1).execute()
if res.data:
    print("Columns:", list(res.data[0].keys()))
else:
    print("No rows found in placement_audits")

