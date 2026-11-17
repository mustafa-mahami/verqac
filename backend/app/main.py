from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import account, auth, lab, push, invitations, meta, notifications, orgs, projects, records, structure, team, verify
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

for r in (auth.router, account.router, push.router, projects.router, team.router, orgs.router, invitations.router, records.router, notifications.router, meta.router, verify.router, structure.router, lab.router):
    app.include_router(r, prefix="/api/v1")


@app.get("/api/health")
def health():
    return {"status": "ok"}
