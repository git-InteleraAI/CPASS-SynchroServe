import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from app.db import supabase

res = supabase.table("profiles").select("id, email, full_name, role, assigned_state").execute()
for r in res.data:
    print(r)
