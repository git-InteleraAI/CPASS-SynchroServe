import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from app.db import supabase

users = supabase.auth.admin.list_users()
for u in users:
    print(f"ID: {u.id} | Email: {u.email}")

