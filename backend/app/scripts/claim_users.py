"""Turn imported Odoo people into working Verqac accounts: the placeholder becomes the person's account (their e-mail,
their history, their project role and party), joins the organization of that party, and gets a link to set a password.

    python -m app.scripts.claim_users /data/files/odoo-import/50 --person u1618 --person u1609+p5325+p5593 --person u1602=fadi@x.ps
    ... --commit            # do it (back up first); prints each person's link (valid 72 hours)
    ... --commit --mail     # also e-mail the links

KEY is the part of the placeholder e-mail after the database name: odoo-magcc-u1618@... -> u1618. Several keys joined
with + are the same person (an Odoo user and Odoo contacts): their history goes to the first one. The e-mail is the
Odoo login unless given after =.
"""
import argparse
import json
import os
import sys

from sqlalchemy import func, select

from app.scripts.cleanup_users import PLACEHOLDER

LINK_HOURS = 72


def main(argv=None):
    from app.core.db import session_scope
    from app.models.core import OrgMember, ProjectMember, ProjectParty, User
    from app.scripts.merge_users import merge
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", help="the import folder (with data.json)")
    ap.add_argument("--person", action="append", required=True, help="KEY[+KEY...][=e-mail]")
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--mail", action="store_true", help="e-mail the links (otherwise send them yourself)")
    a = ap.parse_args(argv)
    data = json.load(open(os.path.join(a.folder, "data.json"), encoding="utf-8"))
    logins = {f"u{u['id']}": (u.get("login") or u.get("email") or "").strip().lower() for u in data.get("users", [])}

    class Trial(Exception):
        pass
    claimed = []
    try:
        with session_scope(bypass=True) as db:
            seen = set()
            for spec in a.person:
                keys, _, email = spec.partition("=")
                keys = [k.strip() for k in keys.split("+") if k.strip()]
                email = (email.strip() or logins.get(keys[0], "")).lower()
                if "@" not in email:
                    sys.exit(f"{spec}: no e-mail in Odoo for {keys[0]}; give it as {keys[0]}=name@example.com (nothing was changed)")
                if email in seen:
                    sys.exit(f"{email} is given twice (nothing was changed)")
                seen.add(email)
                people = []
                for k in keys:
                    u = db.scalar(select(User).where(User.email.ilike(f"odoo-%-{k}{PLACEHOLDER}")))
                    if u is None:
                        sys.exit(f"No placeholder {k} (see merge_users --list; nothing was changed)")
                    people.append(u)
                main_u = people[0]
                taken = db.scalar(select(User).where(func.lower(User.email) == email))
                if taken is not None:
                    sys.exit(f"{email} already has an account: merge into it instead (merge_users --map ...; nothing was changed)")
                for other in people[1:]:
                    merge(db, other, main_u)
                old = main_u.email
                main_u.email, main_u.is_active = email, True
                parties, orgs = [], set()
                for m in db.scalars(select(ProjectMember).where(ProjectMember.user_id == main_u.id)):
                    m.is_active = True
                    pt = db.get(ProjectParty, m.party_id)
                    parties.append(pt.kind)
                    if pt.org_id and not db.scalar(select(OrgMember.id).where(OrgMember.org_id == pt.org_id,
                                                                            OrgMember.user_id == main_u.id)):
                        db.add(OrgMember(org_id=pt.org_id, user_id=main_u.id, org_role="member"))
                        orgs.add(pt.org_id)
                db.flush()
                print(f"  {main_u.full_name_ar[:28]:28} {old.split('@')[0]:22} -> {email:32} side: {', '.join(parties) or '-'}"
                      f"{'  (+' + str(len(people) - 1) + ' merged)' if len(people) > 1 else ''}")
                claimed.append(main_u.id)
            if not a.commit:
                raise Trial
    except Trial:
        print("\nTRIAL RUN: nothing was written. Add --commit to apply (back up the database first).")
        return
    # the links, once the accounts exist (each link is its own small transaction)
    from app.api.account import _mail, _new_link
    print(f"\nLinks to set a password (valid {LINK_HOURS} hours; an org admin can make a new one from the members list):")
    with session_scope(bypass=True) as db:
        users = [db.get(User, i) for i in claimed]
        for u in users:
            db.expunge(u)
    for u in users:
        link, _ = _new_link(u.id, LINK_HOURS, None)
        if a.mail:
            _mail(u, link, LINK_HOURS)
        print(f"  {u.full_name_ar[:28]:28} {u.email:32} {link}")
    print("\nDone.")


if __name__ == "__main__":
    main()
