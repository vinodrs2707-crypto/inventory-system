import random
import sys

import httpx

PRODUCT = "http://127.0.0.1:8002"
AUTH = "http://127.0.0.1:8001"
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS  " if ok else "FAIL  ") + name + ("" if ok or not detail else f"   -> {detail}"))


query = f"?search=cache-test-{random.randint(100000, 999999)}"

r = httpx.get(f"{PRODUCT}/products{query}", timeout=15)
check("First request is a MISS", r.headers.get("x-cache") == "MISS", f"X-Cache = {r.headers.get('x-cache')}")
if r.headers.get("x-cache") == "BYPASS":
    print("Redis is not reachable from the Product service. Check REDIS_URL in .env and restart it.")
    sys.exit(1)

r = httpx.get(f"{PRODUCT}/products{query}", timeout=15)
check("Second identical request is a HIT", r.headers.get("x-cache") == "HIT", f"X-Cache = {r.headers.get('x-cache')}")

login = httpx.post(f"{AUTH}/auth/login", json={"email": "admin@example.com", "password": "Admin@12345"}, timeout=15)
if login.status_code != 200:
    sys.exit(f"Admin login failed ({login.status_code})")
headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

product = httpx.get(f"{PRODUCT}/products/1", timeout=15).json()
r = httpx.put(f"{PRODUCT}/products/1", json={"name": product["name"]}, headers=headers, timeout=15)
check("A product update works", r.status_code == 200, f"{r.status_code}")

r = httpx.get(f"{PRODUCT}/products{query}", timeout=15)
check("After an update the cache is cleared (MISS)", r.headers.get("x-cache") == "MISS", f"X-Cache = {r.headers.get('x-cache')}")

r = httpx.get(f"{PRODUCT}/products{query}", timeout=15)
check("And it is cached again (HIT)", r.headers.get("x-cache") == "HIT", f"X-Cache = {r.headers.get('x-cache')}")

print()
print(f"{sum(results)} of {len(results)} checks passed")