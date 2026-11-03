import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from app.db import supabase

res = supabase.auth.admin.update_user_by_id(
    "5500b258-95b5-41fd-9705-76642b58bcc7",
    {"password": "jsubWTVkgGo9&_xuq0"}
)
print("Updated user:", res.user.email)

