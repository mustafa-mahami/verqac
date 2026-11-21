"""Hand the history of an imported placeholder account (odoo-...@import.verqac.invalid) to the real person's account.

    python -m app.scripts.merge_users --list                                       # placeholders and what they did
    python -m app.scripts.merge_users --map odoo-x-u7@import.verqac.invalid=eng@mccc.ps   # trial
    python -m app.scripts.merge_users --map ...=... --map ...=... --commit         # do it (back up first)

Invite the person first (they accept and set their password), then merge. Everything the placeholder did (records,
events, comments, files, lab decisions) is shown under the real person; the placeholder's project roles go to them
when they do not already have a role in that project; the placeholder is then removed.
"""
import argparse
import sys

from sqlalchemy import func, select, text

from app.scripts.cleanup_users import HISTORY, PLACEHOLDER

MOVE = HISTORY + [("invitations", "created_by")]


def merge(db, src, dst) -> dict:
    from app.models.core import ProjectMember, User
    counts = {}
    for t, c in MOVE:
        n = db.execute(text(f"UPDATE {t} SET {c} = :d WHERE {c} = :s"), {"d": dst.id, "s": src.id}).rowcount
        if n:
            counts[f"{t}.{c}"] = n
    have = set(db.scalars(select(ProjectMember.project_id).where(ProjectMember.user_id == dst.id)))
    for m in db.scalars(select(ProjectMember).where(ProjectMember.user_id == src.id)).all():
        if m.project_id in have:
            db.delete(m)
        else:
            m.user_id, m.is_active = dst.id, True
            counts["project roles"] = counts.get("project roles", 0) + 1
    db.flush()
    if not db.execute(text("DELETE FROM users WHERE id = :s"), {"s": src.id}).rowcount:
        sys.exit("The placeholder could not be removed (database migration 0029 missing?). Nothing was changed.")
    return counts


def main(argv=None):
    from app.core.db import session_scope
    from app.models.core import User
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--map", action="append", default=[], help="placeholder-email=real-email")
    ap.add_argument("--commit", action="store_true")
    a = ap.parse_args(argv)

    class Trial(Exception):
        pass
    try:
        with session_scope(bypass=True) as db:
            if a.list or not a.map:
                for u in db.scalars(select(User).where(User.email.ilike(f"%{PLACEHOLDER}")).order_by(User.full_name_ar)):
                    n = sum(db.scalar(text(f"SELECT count(*) FROM {t} WHERE {c} = :u"), {"u": u.id}) for t, c in HISTORY)
                    print(f"  {u.email:48} {u.full_name_ar[:30]:30} {u.full_name_en[:30]:30} history rows: {n}")
                return
            for pair in a.map:
                s, _, d = pair.partition("=")
                src = db.scalar(select(User).where(func.lower(User.email) == s.strip().lower()))
                dst = db.scalar(select(User).where(func.lower(User.email) == d.strip().lower()))
                if not src or not src.email.endswith(PLACEHOLDER):
                    sys.exit(f"Not a placeholder account: {s} (nothing was changed)")
                if not dst or dst.email.endswith(PLACEHOLDER) or not dst.is_active:
                    sys.exit(f"No active real account: {d} (invite them first; nothing was changed)")
                print(f"  {src.full_name_ar} -> {dst.email}: {merge(db, src, dst)}")
            if not a.commit:
                raise Trial
            print("\nDone.")
    except Trial:
        print("\nTRIAL RUN: nothing was written. Add --commit to apply (back up the database first).")


if __name__ == "__main__":
    main()
