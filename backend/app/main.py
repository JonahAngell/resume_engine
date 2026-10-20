"""FastAPI app: lifespan, request guard, a few top-level routes, and the API routers."""






from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from urllib.parse import urlparse
from fastapi.staticfiles import StaticFiles
from .database import (
    close_database,
    connection,
    database_health,
    migrate,
    open_database,
)
# Relationship resources retained for Phase 2C contract: 'bullets','bullet_variants'
from .ai_client import close_shared_client, providers as ai_providers
from .identity import CurrentUser, check_local_auth_safety, resolve_current_user
from .library_schemas import (
    CurrentUserResponse,
)
from .schemas import Resume
from .api_common import MAX_IMPORT_BYTES, ROOT, SEED, owner
from .routers import ai, compositions, defaults, jobs, library

FRONTEND = ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app):
    check_local_auth_safety()
    await open_database()
    await migrate()
    yield
    await close_shared_client()
    await close_database()


app = FastAPI(title="Resume Engine Phase 2", version="0.5.0", lifespan=lifespan)


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
MAX_JSON_BYTES = 2 * 1024 * 1024
UPLOAD_PATH = "/api/library/import/preview"


@app.middleware("http")
async def request_guard(request, call_next):
    """Reject cross-site writes and oversized bodies before any handler runs."""
    if request.method not in SAFE_METHODS:
        site = request.headers.get("sec-fetch-site")
        origin = request.headers.get("origin")
        cross_site = False
        if site is not None:
            cross_site = site not in {"same-origin", "none"}
        elif origin is not None:
            cross_site = urlparse(origin).netloc != request.headers.get("host", "")
        if cross_site:
            return JSONResponse({"detail": "Cross-site request blocked."}, status_code=403)
        limit = MAX_IMPORT_BYTES + 64 * 1024 if request.url.path == UPLOAD_PATH else MAX_JSON_BYTES
        length = request.headers.get("content-length", "")
        if length.isdigit() and int(length) > limit:
            return JSONResponse({"detail": "Request body is too large."}, status_code=413)
    return await call_next(request)


@app.get("/health")
async def health():
    if not await database_health():
        raise HTTPException(503, "Database unavailable")
    return {"status": "ok", "database": "ok"}


@app.get("/api/seed", response_model=Resume)
def seed(identity: CurrentUser = Depends(resolve_current_user)):
    return Resume.model_validate_json(SEED.read_text())


@app.get("/api/me", response_model=CurrentUserResponse)
async def me(identity: CurrentUser = Depends(resolve_current_user)):
    async with connection() as c:
        return await owner(identity, c)


@app.get("/api/ai/status")
def ai_status(identity: CurrentUser = Depends(resolve_current_user)):
    chain = ai_providers()
    return {
        "available": bool(chain),
        "providers": [{"name": p.name, "models": list(p.models)} for p in chain],
    }


for _router in (library.router, compositions.router, defaults.router, jobs.router, ai.router):
    app.include_router(_router)


if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
