from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth import CurrentUser, get_current_user
from .config import settings
from .db import TRANSIENT_ERRORS, close_db_clients
from .routers import audits, auth, dashboard, documents, duplicates, lookups


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    close_db_clients()


app = FastAPI(title="CPASS API", version="0.1.0", lifespan=lifespan)

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
