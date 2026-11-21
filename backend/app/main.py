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

for r in (auth.router, account.router, push.router, projects.router, team.router, orgs.router, invitations.router, records.router, notifications.router, meta.router, verify.router, structure.router, lab.router, daily.router, programme.router, periodic.router, kpi.router, finance.router):
    app.include_router(r, prefix="/api/v1")


@app.get("/api/health")
def health():
    return {"status": "ok"}
