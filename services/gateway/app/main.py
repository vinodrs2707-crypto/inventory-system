import asyncio
import json
import logging
import re
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import Optional

import httpx
import jwt
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("gateway")

# ---------- which path goes to which service ----------

SERVICES = {
    "auth": settings.AUTH_SERVICE_URL,
    "product": settings.PRODUCT_SERVICE_URL,
    "inventory": settings.INVENTORY_SERVICE_URL,
    "coupon": settings.COUPON_SERVICE_URL,
    "cart": settings.CART_SERVICE_URL,
    "order": settings.ORDER_SERVICE_URL,
    "payment": settings.PAYMENT_SERVICE_URL,
}

ROUTES = [
    (re.compile(r"^auth(/|$)"), "auth"),
    (re.compile(r"^(products|categories)(/|$)"), "product"),
    (re.compile(r"^inventory(/|$)"), "inventory"),
    (re.compile(r"^coupons(/|$)"), "coupon"),
    (re.compile(r"^(cart|wishlist)(/|$)"), "cart"),
    (re.compile(r"^orders(/|$)"), "order"),
    (re.compile(r"^payments(/|$)"), "payment"),
]

# These are only for services talking to each other. Never reachable from outside.
BLOCKED = [
    ("POST", re.compile(r"^coupons/redeem$")),
    ("POST", re.compile(r"^coupons/redemptions/[^/]+/release$")),
    ("POST", re.compile(r"^orders/\d+/payment-result$")),
]

PUBLIC_POSTS = {"auth/register", "auth/login", "auth/refresh"}
SENSITIVE = {("POST", "orders"), ("POST", "payments"), ("POST", "coupons/validate")}

# Only these headers are passed on. Everything else (like X-Internal-Key) is dropped.
FORWARD_REQUEST_HEADERS = (
    "authorization",
    "content-type",
    "accept",
    "accept-language",
    "idempotency-key",
    "user-agent",
)
FORWARD_RESPONSE_HEADERS = ("content-type", "content-disposition", "retry-after")

CID_PATTERN = re.compile(r"^[A-Za-z0-9-]{8,64}$")
ERROR_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    413: "payload_too_large",
    422: "validation_error",
    429: "rate_limited",
}


# ---------- consistent errors ----------

class GatewayError(Exception):
    def __init__(self, status, code, message, headers=None, details=None):
        self.status = status
        self.code = code
        self.message = message
        self.headers = headers or {}
        self.details = details


def correlation_id(request: Request) -> str:
    return getattr(request.state, "correlation_id", "unknown")


def error_response(cid, status, code, message, headers=None, details=None) -> JSONResponse:
    body = {"status": status, "code": code, "message": message, "correlation_id": cid}
    if details:
        body["details"] = details
    return JSONResponse(status_code=status, content={"error": body}, headers=headers or {})


def error_from_upstream(upstream: httpx.Response, cid: str) -> JSONResponse:
    status = upstream.status_code
    headers = {}
    if "retry-after" in upstream.headers:
        headers["Retry-After"] = upstream.headers["retry-after"]
    if status >= 500:
        # never show internal details of a failing service
        return error_response(cid, 502, "upstream_error", "The service returned an error", headers)

    message, details = "The request was not accepted", None
    try:
        detail = upstream.json().get("detail")
        if isinstance(detail, str):
            message = detail
        elif isinstance(detail, list):
            message = "Validation failed"
            details = [
                {
                    "field": ".".join(str(p) for p in item.get("loc", [])[1:]),
                    "message": item.get("msg", "Invalid value"),
                }
                for item in detail
                if isinstance(item, dict)
            ]
    except Exception:
        pass
    return error_response(
        cid, status, ERROR_CODES.get(status, "request_failed"), message, headers, details
    )


# ---------- rate limiting (in memory for now; Redis comes later) ----------

class RateLimiter:
    def __init__(self):
        self.hits = defaultdict(deque)

    def check(self, key: str, limit: int, window: int = 60) -> int:
        """Return 0 if allowed, otherwise the seconds to wait."""
        now = time.time()
        queue = self.hits[key]
        while queue and now - queue[0] >= window:
            queue.popleft()
        if len(queue) >= limit:
            return max(1, int(window - (now - queue[0])) + 1)
        queue.append(now)
        return 0


limiter = RateLimiter()


def enforce_limit(key: str, limit: int):
    wait = limiter.check(key, limit)
    if wait:
        raise GatewayError(
            429,
            "rate_limited",
            "Too many requests. Please try again later.",
            headers={"Retry-After": str(wait)},
        )


# ---------- helpers ----------

def find_service(path: str) -> Optional[str]:
    for pattern, name in ROUTES:
        if pattern.match(path):
            return name
    return None


def is_public(method: str, path: str) -> bool:
    if method == "POST" and path in PUBLIC_POSTS:
        return True
    if method == "GET":
        if path == "categories":
            return True
        if path == "products" or path.startswith("products/"):
            return path != "products/recently-viewed"
    return False


def authenticate(request: Request) -> int:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise GatewayError(401, "unauthorized", "Authentication required")
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "access":
            raise jwt.InvalidTokenError("Wrong token type")
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise GatewayError(401, "unauthorized", "Invalid or expired token")


# ---------- the app ----------

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=3.0))
    yield
    await app.state.client.aclose()


app = FastAPI(title="API Gateway", lifespan=lifespan)


@app.exception_handler(GatewayError)
async def gateway_error_handler(request: Request, exc: GatewayError):
    return error_response(
        correlation_id(request), exc.status, exc.code, exc.message, exc.headers, exc.details
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    logger.exception("Unexpected gateway error")
    return error_response(
        correlation_id(request), 500, "internal_error", "Something went wrong on our side"
    )


@app.middleware("http")
async def correlation_middleware(request: Request, call_next):
    incoming = request.headers.get("x-correlation-id", "")
    cid = incoming if CID_PATTERN.match(incoming) else str(uuid.uuid4())
    request.state.correlation_id = cid
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = cid
    # structured log line (no query string, no tokens)
    logger.info(
        json.dumps(
            {
                "correlation_id": cid,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                "client": request.client.host if request.client else None,
            }
        )
    )
    return response


# CORS is added last so that it wraps everything else
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Correlation-ID"],
    expose_headers=["X-Correlation-ID", "Retry-After", "Content-Disposition"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "gateway"}


@app.get("/health/services")
async def health_of_services(request: Request):
    client: httpx.AsyncClient = request.app.state.client

    async def probe(name: str, base: str):
        try:
            response = await client.get(f"{base}/health", timeout=2.0)
            return name, "ok" if response.status_code == 200 else f"error {response.status_code}"
        except httpx.RequestError:
            return name, "down"

    results = await asyncio.gather(*(probe(n, b) for n, b in SERVICES.items()))
    return {"gateway": "ok", "services": dict(results)}


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy(path: str, request: Request):
    cid = correlation_id(request)
    path = path.strip("/")
    method = request.method
    ip = request.client.host if request.client else "unknown"

    # 1. is this a known, allowed route?
    service = find_service(path)
    blocked = any(m == method and pattern.match(path) for m, pattern in BLOCKED)
    if service is None or blocked:
        raise GatewayError(404, "not_found", "This route does not exist")

    # 2. login check
    user_id = None
    if not is_public(method, path):
        user_id = authenticate(request)

    # 3. rate limits
    who = f"user:{user_id}" if user_id else f"ip:{ip}"
    if method == "POST" and path in PUBLIC_POSTS:
        enforce_limit(f"auth:{ip}", settings.AUTH_RATE_LIMIT_PER_MINUTE)
    if (method, path) in SENSITIVE:
        enforce_limit(f"sensitive:{who}", settings.SENSITIVE_RATE_LIMIT_PER_MINUTE)
    enforce_limit(f"general:{who}", settings.GENERAL_RATE_LIMIT_PER_MINUTE)

    # 4. body size
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > settings.MAX_BODY_BYTES:
        raise GatewayError(413, "payload_too_large", "The request body is too large")
    body = await request.body()
    if len(body) > settings.MAX_BODY_BYTES:
        raise GatewayError(413, "payload_too_large", "The request body is too large")

    # 5. pass it on (only the safe headers)
    headers = {
        name: request.headers[name] for name in FORWARD_REQUEST_HEADERS if name in request.headers
    }
    headers["X-Correlation-ID"] = cid
    headers["X-Forwarded-For"] = ip

    client: httpx.AsyncClient = request.app.state.client
    try:
        upstream = await client.request(
            method,
            f"{SERVICES[service]}/{path}",
            params=list(request.query_params.multi_items()),
            content=body,
            headers=headers,
        )
    except httpx.ConnectError:
        raise GatewayError(503, "service_unavailable", f"The {service} service is not available right now")
    except httpx.TimeoutException:
        raise GatewayError(504, "gateway_timeout", f"The {service} service took too long to answer")
    except httpx.RequestError:
        raise GatewayError(502, "bad_gateway", f"Could not reach the {service} service")

    # 6. answer
    if upstream.status_code >= 400:
        return error_from_upstream(upstream, cid)
    response_headers = {
        name: upstream.headers[name] for name in FORWARD_RESPONSE_HEADERS if name in upstream.headers
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
    )