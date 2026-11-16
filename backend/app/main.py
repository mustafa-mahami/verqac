from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, invitations, meta, notifications, orgs, projects, records, team
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="Verqac API",
    version="0.1.0",
    docs_url="/api/docs" if settings.env != "prod" else None,
    openapi_url="/api/openapi.json" if settings.env != "prod" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (auth.router, projects.router, team.router, orgs.router, invitations.router, records.router, notifications.router, meta.router):
    app.include_router(r, prefix="/api/v1")


@app.get("/api/health")
def health():
    return {"status": "ok"}
