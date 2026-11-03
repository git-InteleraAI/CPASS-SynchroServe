import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from app.db import supabase

supabase.auth.admin.update_user_by_id(
    "260a53a9-408a-4949-8acb-ce480fe3d330",
    {"password": "Hz^wdeeZnuBhr@=Z*2"}
)
print("Updated L4 password")

supabase.auth.admin.update_user_by_id(
    "529d19cb-9cab-4273-b0fe-613d230467e1",
    {"password": "Kxfzu6*^@BzpRPKH!V"}
)
print("Updated L5 password")

