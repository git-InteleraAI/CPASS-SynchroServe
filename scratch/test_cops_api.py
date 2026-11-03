import httpx

r = httpx.post(
    "http://127.0.0.1:8000/auth/login",
    json={
        "email": "cops@synchroserve.com",
        "password": "jsubWTVkgGo9&_xuq0",
        "expected_role": "L3_COPS"
    }
)
print("Status code:", r.status_code)
print("Response:", r.text)

