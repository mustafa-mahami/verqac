# Verqac

منصة سحابية لإدارة الجودة في مشاريع البناء، مستقلة عن Odoo وعن مهامي. وثيقة التصميم: https://claude.ai/artifact/JTfyJxCyJ5AKzGfDLtmhKb

Quality management SaaS for construction projects: submittals, inspections, RFIs, lab tests, NCRs, daily reports and QA/QC KPIs, shared by contractor, consultant and owner. It rebuilds the Odoo `dr` module (v3.28.4) as an independent platform.

## Status: phase 0 (foundation)

| Done | |
| --- | --- |
| Organizations, users, org admins, disciplines | `backend/app/models/core.py` |
| Roles and permissions as data (8 platform roles, design doc section 3) | `backend/app/core/seed.py` |
| Projects and parties (contractor owns, consultant/owner invited) | `backend/app/api/projects.py` |
| Row-Level Security in PostgreSQL, append-only audit log | `backend/alembic/versions/0001_core.py` |
| Sign-up, login, rotating refresh tokens with reuse detection | `backend/app/api/auth.py` |
| Web shell: Arabic RTL / English LTR, login, sign-up, projects | `frontend/src` |
| Arabic PDF through Chromium | `backend/app/reports`, `python -m scripts.sample_pdf` |

Next (phase 1): invitations, project team screen, record engine (types, workflow states with the 7 `dr` status categories, numbering, revisions), submittals, inspections, RFI.

## Layout

```
backend/    FastAPI + SQLAlchemy 2 + Alembic (Python 3.12)
frontend/   React + TypeScript + Vite + Mantine 7 + i18next
deploy/     host Nginx site, database init script
docs/       deployment guide
```

## Database roles

| Role | Used by | Rights |
| --- | --- | --- |
| `verqac_owner` | migrations | owns the schema |
| `verqac_app` | the API | data only; RLS applies; `audit_log` is INSERT/SELECT only |

Each request sets `app.user_id` (and `app.bypass` only for sign-up, login and refresh). The policies use these settings, so a missing `WHERE` clause in the code cannot leak another organization's data.

## Local development

```bash
# PostgreSQL 16 with the two roles and databases verqac / verqac_test (see deploy/db-init/01-roles.sh)
cd backend
pip install -r requirements-dev.txt && playwright install chromium
alembic upgrade head
uvicorn app.main:app --reload          # http://localhost:8000/api/docs
pytest                                 # 11 tests, incl. cross-organization leak tests

cd ../frontend
npm install && npm run dev             # http://localhost:5173 (proxies /api to :8000)
```

## Deployment

See [docs/DEPLOY.md](docs/DEPLOY.md).
