import json
import logging
import urllib.parse
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth import CurrentUser, get_current_user
from .config import settings
from .db import TRANSIENT_ERRORS, close_db_clients
from .routers import audits, auth, dashboard, documents, duplicates, lookups


logger = logging.getLogger("cpass.csrf")


def parse_origin(url_str: str) -> str | None:
    """Parse and normalize an HTTP/HTTPS serialized origin per RFC 6454.

    Rejects:
    - Non-string, empty, or 'null'
    - Non-HTTP/HTTPS schemes
    - Missing hostname
    - User information (username / password)
    - Paths (even '/'), query strings, fragments
    - Out-of-range ports (< 1 or > 65535) and port 0
    - Malformed hostnames or non-numeric port strings

    Normalizes:
    - Scheme to lowercase
    - Hostname to lowercase
    - Effective port (omits default ports: 80 for HTTP, 443 for HTTPS)
    """
    if not isinstance(url_str, str):
        return None
    url_str = url_str.strip()
    if not url_str or url_str.lower() == "null":
        return None
    try:
        parsed = urllib.parse.urlsplit(url_str)
    except ValueError:
        return None

    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        return None

    if parsed.username or parsed.password:
        return None

    if parsed.path != "":
        return None

    if parsed.query or parsed.fragment:
        return None

    hostname = parsed.hostname
    if not hostname:
        return None
    hostname = hostname.lower()

    try:
        port = parsed.port
    except ValueError:
        return None

    if port is not None:
        if port < 1 or port > 65535:
            return None
        if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
            return f"{scheme}://{hostname}"
        return f"{scheme}://{hostname}:{port}"

    return f"{scheme}://{hostname}"


def parse_referer(url_str: str) -> str | None:
    """Extract canonical HTTP/HTTPS origin from a Referer URL.

    Rejects:
    - Non-string, empty, or 'null'
    - Non-HTTP/HTTPS schemes
    - Missing hostname
    - User information (username / password)
    - Out-of-range ports (< 1 or > 65535) and port 0
    - Malformed URLs

    Normalizes:
    - Scheme to lowercase
    - Hostname to lowercase
    - Effective port (omits default ports: 80 for HTTP, 443 for HTTPS)
    """
    if not isinstance(url_str, str):
        return None
    url_str = url_str.strip()
    if not url_str or url_str.lower() == "null":
        return None
    try:
        parsed = urllib.parse.urlsplit(url_str)
    except ValueError:
        return None

    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        return None

    if parsed.username or parsed.password:
        return None

    hostname = parsed.hostname
    if not hostname:
        return None
    hostname = hostname.lower()

    try:
        port = parsed.port
    except ValueError:
        return None

    if port is not None:
        if port < 1 or port > 65535:
            return None
        if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
            return f"{scheme}://{hostname}"
        return f"{scheme}://{hostname}:{port}"

    return f"{scheme}://{hostname}"


def compute_trusted_origins(allowed_origins: list[str]) -> frozenset[str]:
    """Precompute normalized, immutable trusted origins allowlist."""
    trusted = set()
    for raw in allowed_origins:
        cleaned = raw.strip().rstrip("/")
        norm = parse_origin(cleaned)
        if norm:
            trusted.add(norm)
    return frozenset(trusted)


class CSRFProtectionASGIMiddleware:
    """Pure ASGI middleware for stateless CSRF protection.

    Enforces:
    1. Safe HTTP methods (GET, HEAD, OPTIONS) pass through unconditionally.
    2. Pure Bearer API clients (Authorization: Bearer ... with NO ambient session cookies)
       bypass CSRF validation.
    3. Mandatory X-Requested-With: XMLHttpRequest custom header on all browser mutations.
    4. Strict Origin validation against immutable precomputed trusted origins.
    5. Safe Referer fallback ONLY when Origin header is genuinely absent.
    6. Rejection of duplicate Origin/Referer/XHR headers, Origin: null, and malformed values.
    7. Early 403 Forbidden rejection without consuming or buffering request bodies.
    """

    def __init__(self, app, allowed_origins: frozenset[str] | list[str] | None = None):
        self.app = app
        if allowed_origins is not None:
            if isinstance(allowed_origins, frozenset):
                self._trusted_origins = allowed_origins
            else:
                self._trusted_origins = compute_trusted_origins(allowed_origins)
        else:
            self._trusted_origins = None

    @property
    def trusted_origins(self) -> frozenset[str]:
        if self._trusted_origins is not None:
            return self._trusted_origins
        return compute_trusted_origins(settings.allowed_origins)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET").upper()
        if method in ("GET", "HEAD", "OPTIONS"):
            await self.app(scope, receive, send)
            return

        # Extract headers from ASGI scope without consuming the request body
        origin_headers: list[str] = []
        referer_headers: list[str] = []
        xhr_headers: list[str] = []
        cookie_headers: list[str] = []
        auth_headers: list[str] = []

        for raw_name, raw_val in scope.get("headers", []):
            name = raw_name.lower()
            val = raw_val.decode("latin-1", errors="replace").strip()
            if name == b"origin":
                origin_headers.append(val)
            elif name == b"referer":
                referer_headers.append(val)
            elif name == b"x-requested-with":
                xhr_headers.append(val)
            elif name == b"cookie":
                cookie_headers.append(val)
            elif name == b"authorization":
                auth_headers.append(val)

        # Check for ambient CPASS authentication cookies
        combined_cookies = "; ".join(cookie_headers)
        has_session_cookie = bool(
            "cpass_access_token" in combined_cookies
            or "cpass_refresh_token" in combined_cookies
        )

        # Check for Pure Bearer API client (NO ambient session cookies attached)
        auth_header = auth_headers[0] if auth_headers else ""
        is_bearer_only = (
            not has_session_cookie
            and auth_header.lower().startswith("bearer ")
            and len(auth_header.split(None, 1)) == 2
            and bool(auth_header.split(None, 1)[1].strip())
        )

        if is_bearer_only:
            await self.app(scope, receive, send)
            return

        # 1. Custom Header validation: X-Requested-With: XMLHttpRequest
        if not xhr_headers or not xhr_headers[0]:
            await self._reject(send, "CSRF verification failed: missing or invalid X-Requested-With header.")
            return

        if len(xhr_headers) > 1:
            await self._reject(send, "CSRF verification failed: duplicate X-Requested-With header.")
            return

        if xhr_headers[0].lower() != "xmlhttprequest":
            await self._reject(send, "CSRF verification failed: missing or invalid X-Requested-With header.")
            return

        # 2. Origin / Referer validation
        trusted = self.trusted_origins

        if len(origin_headers) > 1:
            await self._reject(send, "CSRF verification failed: duplicate Origin header.")
            return

        if len(origin_headers) == 1:
            raw_origin = origin_headers[0]
            if raw_origin.lower() == "null":
                await self._reject(send, "CSRF verification failed: invalid Origin header.")
                return

            canonical_origin = parse_origin(raw_origin)
            if not canonical_origin:
                await self._reject(send, "CSRF verification failed: invalid Origin header.")
                return

            if canonical_origin not in trusted:
                await self._reject(send, "CSRF verification failed: untrusted Origin.")
                return

        else:
            # Origin header is genuinely absent -> Safe Referer fallback
            if not referer_headers or not referer_headers[0]:
                await self._reject(send, "CSRF verification failed: missing Origin and Referer headers.")
                return

            if len(referer_headers) > 1:
                await self._reject(send, "CSRF verification failed: duplicate Referer header.")
                return

            raw_referer = referer_headers[0]
            if raw_referer.lower() == "null":
                await self._reject(send, "CSRF verification failed: invalid Referer header.")
                return

            canonical_referer = parse_referer(raw_referer)
            if not canonical_referer:
                await self._reject(send, "CSRF verification failed: invalid Referer header.")
                return

            if canonical_referer not in trusted:
                await self._reject(send, "CSRF verification failed: untrusted Referer origin.")
                return

        # All CSRF checks passed; proceed to the next ASGI handler
        await self.app(scope, receive, send)

    async def _reject(self, send, detail: str):
        body = json.dumps({"detail": detail}).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": 403,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    close_db_clients()


app = FastAPI(title="CPASS API", version="0.1.0", lifespan=lifespan)

# Register CSRF Protection first, then CORSMiddleware.
# In Starlette, the last-added middleware executes outermost.
# This ensures CORSMiddleware handles preflight (OPTIONS) requests
# and attaches CORS headers to all responses, including CSRF 403 rejections.
app.add_middleware(CSRFProtectionASGIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(lookups.router)
app.include_router(duplicates.router)
app.include_router(documents.router)
app.include_router(audits.router)
app.add_api_route("/candidates/{candidate_id}", lookups.candidate_detail, methods=["GET"], tags=["candidates"])


async def _handle_transient_error(request: Request, exc: Exception) -> JSONResponse:
    import logging
    logging.getLogger("cpass.main").warning(
        "Transient transport/database error on %s %s: %s",
        request.method,
        request.url.path,
        exc,
    )
    origin = request.headers.get("origin")
    headers = {"Retry-After": "1"}
    if origin:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"

    return JSONResponse(
        status_code=503,
        content={"detail": "Database service temporarily unreachable. Please retry."},
        headers=headers,
    )


for exc_cls in TRANSIENT_ERRORS:
    app.add_exception_handler(exc_cls, _handle_transient_error)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, TRANSIENT_ERRORS):
        return await _handle_transient_error(request, exc)

    err_str = str(exc)
    if "Errno 11" in err_str or "UNEXPECTED_EOF" in err_str or "10035" in err_str:
        return await _handle_transient_error(request, exc)

    import logging
    logging.getLogger("cpass.main").exception("Unhandled server error: %s", exc)
    origin = request.headers.get("origin")
    headers = {}
    if origin:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"

    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected server error occurred. Please try again."},
        headers=headers,
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/me")
def me(user: CurrentUser = Depends(get_current_user)):
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "assigned_state": user.assigned_state,
    }
