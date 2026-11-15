"""Tests run against a real PostgreSQL (RLS cannot be tested on SQLite).

Needs a server with roles verqac_owner and verqac_app and a database verqac_test
owned by verqac_owner. The schema is rebuilt from the migrations at the start.
"""
import os

os.environ.setdefault("VERQAC_DATABASE_URL", "postgresql+psycopg://verqac_app:verqac_app@localhost:5432/verqac_test")
os.environ.setdefault("VERQAC_MIGRATION_DATABASE_URL",
                      "postgresql+psycopg://verqac_owner:verqac_owner@localhost:5432/verqac_test")
os.environ.setdefault("VERQAC_JWT_SECRET", "test-secret-test-secret-test-secret-32")

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

HERE = os.path.dirname(os.path.dirname(__file__))


@pytest.fixture(scope="session", autouse=True)
def schema():
    owner = create_engine(os.environ["VERQAC_MIGRATION_DATABASE_URL"])
    with owner.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    owner.dispose()
    cfg = Config(os.path.join(HERE, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(HERE, "alembic"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


_n = 0


def register(client, kind="contractor", name="Org"):
    global _n
    _n += 1
    r = client.post("/api/v1/auth/register-org", json={
        "org_kind": kind, "org_name_ar": f"جهة {name}", "org_name_en": f"{name} {_n}",
        "full_name_ar": "مستخدم", "full_name_en": "User", "email": f"user{_n}@{name.lower()}.example.com",
        "password": "a-strong-password", "locale": "ar",
    })
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    me = client.get("/api/v1/auth/me", headers=headers).json()
    return headers, me["orgs"][0]["org"]["id"], me["user"]["email"]
