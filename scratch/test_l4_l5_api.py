import httpx

for role, email, pw in [
    ("L4_LEADER", "sowbhagya.bl@synchroserve.com", "Hz^wdeeZnuBhr@=Z*2"),
    ("L5_CEO", "ceo@synchroserve.com", "Kxfzu6*^@BzpRPKH!V")
]:
    r = httpx.post(
        "http://127.0.0.1:8000/auth/login",
        json={"email": email, "password": pw, "expected_role": role}
    )
    print(f"{role} ({email}) -> Status: {r.status_code}")

