from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import CurrentUser, get_current_user
from .config import settings
from .routers import audits, auth, documents, duplicates, lookups

app = FastAPI(title="CPASS API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(lookups.router)
app.include_router(duplicates.router)
app.include_router(documents.router)
app.include_router(audits.router)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    import logging
    logging.getLogger("cpass.main").exception("Unhandled server error: %s", exc)
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"},
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/me")
def me(user: CurrentUser = Depends(get_current_user)):
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role}
