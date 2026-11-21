"""Remove the test accounts, keeping the ones named (and the placeholders of imported history).

    python -m app.scripts.cleanup_users --keep ceo@mccc.ps            # trial: lists what would happen
    python -m app.scripts.cleanup_users --keep ceo@mccc.ps --commit   # does it (back up the database first)

An account that wrote nothing is deleted. One that appears in the history of records (wrote, submitted, answered,
commented, uploaded) cannot be deleted without changing that history: it is switched off instead (cannot sign in,
leaves its organizations and project teams), and its name stays on what it did.
Organizations and projects are never deleted here: the ones left without members are listed for you to decide.
"""
import argparse
import sys

from sqlalchemy import delete, func, select, update

PLACEHOLDER = "@import.verqac.invalid"
# where an account is part of the history (deleting it would need these rows changed or removed)
HISTORY = [("records", "created_by"), ("records", "submitted_by"), ("records", "answered_by"), ("records", "assigned_to"),
           ("records", "answered_on_behalf_of"), ("record_events", "actor_id"), ("record_events", "on_behalf_of"),
           ("record_comments", "author_id"), ("files", "uploaded_by"), ("lab_results", "decision_by"),
           ("password_resets", "created_by")]


def plan(db, keep: set[str]) -> list[dict]:
    from sqlalchemy import text

    from app.models.core import OrgMember, Organization, ProjectMember, User
    out = []
    for u in db.scalars(select(User).order_by(User.created_at)):
        email = u.email.lower()
        if email in keep or email.endswith(PLACEHOLDER):
            continue
        refs = sum(db.scalar(text(f"SELECT count(*) FROM {t} WHERE {c} = :u"), {"u": u.id}) for t, c in HISTORY)
        orgs = [o.name_ar for o in db.scalars(select(Organization).join(OrgMember, OrgMember.org_id == Organization.id)
                                                .where(OrgMember.user_id == u.id))]
        projects = db.scalar(select(func.count()).select_from(ProjectMember).where(ProjectMember.user_id == u.id))
        out.append({"user": u, "refs": refs, "orgs": orgs, "projects": projects, "action": "deactivate" if refs else "delete"})
    return out


def apply(db, rows: list[dict]) -> None:
    from sqlalchemy import text

    from app.models.core import OrgMember, ProjectMember, User
    for r in rows:
        u = r["user"]
        db.execute(delete(OrgMember).where(OrgMember.user_id == u.id))
        if r["action"] == "delete":
            db.execute(delete(ProjectMember).where(ProjectMember.user_id == u.id))
            db.execute(text("DELETE FROM invitations WHERE created_by = :u"), {"u": u.id})
            res = db.execute(delete(User).where(User.id == u.id))  # sessions, notifications, push subscriptions follow
            if not res.rowcount:
                sys.exit("An account could not be deleted (database migration 0029 missing?). Nothing was changed.")
        else:
            db.execute(update(ProjectMember).where(ProjectMember.user_id == u.id).values(is_active=False))
            db.execute(text("DELETE FROM refresh_tokens WHERE user_id = :u"), {"u": u.id})
            u.is_active = False
    db.flush()


def orphans(db) -> list[tuple[str, list[str]]]:
    """Organizations with no member left, and their projects."""
    from app.models.core import OrgMember, Organization, Project
    out = []
    for o in db.scalars(select(Organization)):
        if db.scalar(select(func.count()).select_from(OrgMember).where(OrgMember.org_id == o.id)):
            continue
        out.append((o.name_ar, [f"{p.code} {p.name_ar}" for p in db.scalars(select(Project).where(Project.owner_org_id == o.id))]))
    return out


def main(argv=None):
    from app.core.db import session_scope
    from app.models.core import User
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keep", action="append", required=True, help="e-mail of an account to keep (repeat for several)")
    ap.add_argument("--commit", action="store_true", help="do it (without it: a trial that changes nothing)")
    a = ap.parse_args(argv)
    keep = {e.strip().lower() for e in a.keep}

    class Trial(Exception):
        pass
    try:
        with session_scope(bypass=True) as db:
            missing = [e for e in keep if not db.scalar(select(User.id).where(func.lower(User.email) == e))]
            if missing:
                sys.exit(f"No such account to keep: {', '.join(missing)} (nothing was changed)")
            rows = plan(db, keep)
            print(f"Kept: {', '.join(sorted(keep))} (and the placeholders of imported history)\n")
            for r in rows:
                u = r["user"]
                print(f"  {r['action']:10} {u.email:42} {u.full_name_ar[:28]:28} orgs: {', '.join(r['orgs']) or '-':30} "
                      f"projects: {r['projects']}  history rows: {r['refs']}")
            print(f"\n  to delete: {sum(r['action'] == 'delete' for r in rows)}   to switch off: {sum(r['action'] == 'deactivate' for r in rows)}")
            apply(db, rows)
            left = orphans(db)
            if left:
                print("\nOrganizations left with no member (not deleted; decide what to do with them):")
                for name, projects in left:
                    print(f"  {name}: {', '.join(projects) or 'no projects'}")
            if not a.commit:
                raise Trial
            print("\nDone.")
    except Trial:
        print("\nTRIAL RUN: nothing was written. Add --commit to apply (back up the database first).")


if __name__ == "__main__":
    main()
