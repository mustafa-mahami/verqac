from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import account, auth, daily, finance, kpi, programme, lab, push, invitations, meta, notifications, orgs, periodic, projects, records, structure, team, verify
from app.core.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(_app):
    if settings.reminders:  # deadline reminders in the background (see app/core/reminders.py)
        from app.core import reminders
        reminders.start()
    yield


app = FastAPI(
    title="Verqac API",
    version="0.1.0",
    docs_url="/api/docs" if settings.env != "prod" else None,
    openapi_url="/api/openapi.json" if settings.env != "prod" else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class JsonGzip:
    """Compress the API's JSON (a register of thousands of records is ~1 MB, ~10x smaller gzipped);
    files and PDFs go as they are (already compressed, and streamed)."""

    def __init__(self, app):
        from starlette.middleware.gzip import GZipMiddleware
        self.plain, self.gzip = app, GZipMiddleware(app, minimum_size=2048, compresslevel=5)

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "") if scope["type"] == "http" else ""
        skip = not path.startswith("/api/") or path.startswith("/api/v1/files/") or path.endswith("/pdf")
        await (self.plain if skip else self.gzip)(scope, receive, send)


app.add_middleware(JsonGzip)


class Timing:
    """How long each API call takes: a Server-Timing header (browser dev tools), and a SLOW line in the log
    for calls over half a second (docker compose logs api | grep SLOW)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/"):
            return await self.app(scope, receive, send)
        import logging
        import time
        t0 = time.perf_counter()

        async def timed(msg):
            if msg["type"] == "http.response.start":
                ms = (time.perf_counter() - t0) * 1000
                msg.setdefault("headers", []).append((b"server-timing", f"app;dur={ms:.0f}".encode()))
                if ms > 500:
                    logging.getLogger("uvicorn.error").warning("SLOW %s %s %.0f ms", scope["method"], scope["path"], ms)
            await send(msg)
        await self.app(scope, receive, timed)


app.add_middleware(Timing)

for r in (auth.router, account.router, push.router, projects.router, team.router, orgs.router, invitations.router, records.router, notifications.router, meta.router, verify.router, structure.router, lab.router, daily.router, programme.router, periodic.router, kpi.router, finance.router):
    app.include_router(r, prefix="/api/v1")


@app.get("/api/health")
def health():
    return {"status": "ok"}
