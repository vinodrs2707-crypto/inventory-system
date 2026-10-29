import sys
from pathlib import Path

import httpx

GATEWAY = "http://127.0.0.1:8000"
CUSTOMER = {"email": "test@example.com", "password": "Test@12345"}
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS  " if ok else "FAIL  ") + name + ("" if ok or not detail else f"   -> {detail}"))


def internal_key():
    env = Path(".env")
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("INTERNAL_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


def login():
    r = httpx.post(f"{GATEWAY}/auth/login", json=CUSTOMER, timeout=10)
    if r.status_code == 429:
        print("Login is rate limited. Wait one minute and run the script again.")
        sys.exit(1)
    if r.status_code != 200:
        print(f"Login failed ({r.status_code}). Are all services running?")
        sys.exit(1)
    return r.json()["access_token"]


def error_code(r):
    try:
        return r.json()["error"]["code"]
    except Exception:
        return None


if len(sys.argv) > 1 and sys.argv[1] == "down":
    token = login()
    r = httpx.get(f"{GATEWAY}/cart", headers={"Authorization": f"Bearer {token}"}, timeout=10)
    check("Cart service stopped -> clean 503 error", r.status_code == 503 and error_code(r) == "service_unavailable", f"{r.status_code} {r.text[:120]}")
    sys.exit(0)

r = httpx.get(f"{GATEWAY}/health", timeout=10)
check("Gateway health works", r.status_code == 200)
check("Response has an X-Correlation-ID header", bool(r.headers.get("x-correlation-id")))

r = httpx.get(f"{GATEWAY}/health", headers={"X-Correlation-ID": "my-test-id-12345"}, timeout=10)
check("Your own correlation ID is passed back", r.headers.get("x-correlation-id") == "my-test-id-12345")

r = httpx.get(f"{GATEWAY}/products", timeout=10)
check("Browsing products works without login", r.status_code == 200 and "items" in r.json(), f"{r.status_code}")

r = httpx.get(f"{GATEWAY}/cart", timeout=10)
check("Cart without a token gives 401 in the standard error format", r.status_code == 401 and error_code(r) == "unauthorized", f"{r.status_code} {r.text[:120]}")

r = httpx.get(f"{GATEWAY}/nothing-here", timeout=10)
check("Unknown route gives 404", r.status_code == 404 and error_code(r) == "not_found")

token = login()
auth = {"Authorization": f"Bearer {token}"}

r = httpx.get(f"{GATEWAY}/auth/me", headers=auth, timeout=10)
check("Login token works through the gateway", r.status_code == 200 and r.json().get("email") == CUSTOMER["email"], f"{r.status_code}")

r = httpx.get(f"{GATEWAY}/cart", headers=auth, timeout=10)
check("Cart works with a token", r.status_code == 200, f"{r.status_code} {r.text[:120]}")

r = httpx.post(f"{GATEWAY}/coupons/redeem", headers=auth, json={}, timeout=10)
check("Service-only API /coupons/redeem is blocked", r.status_code == 404)

r = httpx.post(f"{GATEWAY}/orders/1/payment-result", headers=auth, json={}, timeout=10)
check("Service-only API /payment-result is blocked", r.status_code == 404)

key = internal_key()
r = httpx.get(f"{GATEWAY}/inventory/1", headers={"X-Internal-Key": key}, timeout=10)
check("A fake X-Internal-Key cannot skip the login check", r.status_code == 401, f"{r.status_code}")

restock = {"reference": "GATEWAY-TEST-1", "reason": "gateway test", "items": [{"product_id": 1, "quantity": 1}]}
r = httpx.post(f"{GATEWAY}/inventory/restock", headers={**auth, "X-Internal-Key": key}, json=restock, timeout=10)
check("Internal key sent with a customer token is ignored (still 403)", r.status_code == 403, f"{r.status_code} {r.text[:120]}")

r = httpx.post(f"{GATEWAY}/auth/login", json={"email": "not-an-email"}, timeout=10)
check("Bad input gives 422 with field details", r.status_code == 422 and error_code(r) == "validation_error" and "details" in r.json()["error"], f"{r.status_code} {r.text[:150]}")

limited = None
for _ in range(12):
    r = httpx.post(f"{GATEWAY}/auth/login", json={"email": "test@example.com", "password": "WrongPass1"}, timeout=10)
    if r.status_code == 429:
        limited = r
        break
check("Too many login attempts gives 429 with Retry-After", limited is not None and "retry-after" in limited.headers and error_code(limited) == "rate_limited")

print()
print(f"{sum(results)} of {len(results)} checks passed")