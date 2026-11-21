"""Undo what test accounts did on a project's records: each record goes back to the state it was in before their
first action, with the answer it had then (the one imported from Odoo, or none), and their events are removed.

    python -m app.scripts.revert_answers --project AAUP --by ceo@magcc.ps --by musaed@magcc.ps            # trial
    python -m app.scripts.revert_answers --project AAUP --by ceo@magcc.ps --by musaed@magcc.ps --commit   # back up first
"""
import argparse
import sys
from datetime import timedelta

from sqlalchemy import func, select, text

ANSWERED = ("draft", "submitted")  # an answer moves a record out of these


def main(argv=None):
    from app.core.db import session_scope
    from app.models.core import Project, User
    from app.models.lab import LabResult
    from app.models.records import Record, RecordEvent, WorkflowState
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--by", action="append", required=True, help="e-mail of a test account (repeat for several)")
    ap.add_argument("--commit", action="store_true")
    a = ap.parse_args(argv)

    class Trial(Exception):
        pass
    try:
        with session_scope(bypass=True) as db:
            p = db.scalar(select(Project).where(Project.code == a.project))
            if p is None:
                sys.exit(f"No project {a.project}")
            users = {u.id: u for u in db.scalars(select(User).where(func.lower(User.email).in_([e.lower() for e in a.by])))}
            if len(users) != len(a.by):
                sys.exit("Some of these accounts do not exist (nothing was changed)")
            states = {s.id: s for s in db.scalars(select(WorkflowState))}
            test = list(db.scalars(select(RecordEvent).join(Record, Record.id == RecordEvent.record_id)
                                   .where(Record.project_id == p.id, RecordEvent.actor_id.in_(users))
                                   .order_by(RecordEvent.record_id, RecordEvent.at, RecordEvent.id)))
            first = {}
            for e in test:
                first.setdefault(e.record_id, e)
            n_ev, done = 0, set()
            for rid, e0 in first.items():
                rec = db.get(Record, rid)
                before = list(db.scalars(select(RecordEvent).where(RecordEvent.record_id == rid, RecordEvent.id != e0.id,
                                                                  RecordEvent.actor_id.notin_(users), RecordEvent.at <= e0.at)
                                         .order_by(RecordEvent.at, RecordEvent.id)))
                later_other = db.scalar(select(func.count()).select_from(RecordEvent).where(
                    RecordEvent.record_id == rid, RecordEvent.actor_id.notin_(users), RecordEvent.at > e0.at))
                if later_other:
                    print(f"  SKIPPED {rec.number} R{rec.rev_no}: someone else acted on it after the test (check it by hand)")
                    continue
                done.add(rid)
                prior = states[e0.from_state_id]
                answer = next((x for x in reversed(before) if x.to_state_id and states[x.to_state_id].category not in ANSWERED
                               and x.from_state_id and states[x.from_state_id].category == "submitted"), None)
                if prior.category in ANSWERED:
                    answer = None
                print(f"  {rec.number} R{rec.rev_no}: {states[rec.state_id].code} -> {prior.code}"
                      f"{'  (keeps the Odoo answer of ' + answer.at.date().isoformat() + ')' if answer else ''}")
                rec.state_id, rec.state_category = prior.id, prior.category
                if answer:
                    rec.answered_by, rec.answered_on_behalf_of, rec.answered_at = answer.actor_id, answer.on_behalf_of, answer.at
                    rec.response_comment = answer.comment
                    if rec.performed_at and rec.performed_at > e0.at - timedelta(minutes=1):
                        rec.performed_at = answer.at
                else:
                    rec.answered_by = rec.answered_on_behalf_of = rec.answered_at = rec.response_comment = None
                    rec.performed_at = rec.resubmit_due_at = None
                rec.updated_at = before[-1].at if before else rec.created_at
                n_ev += db.execute(text("DELETE FROM record_events WHERE record_id = :r AND actor_id = ANY(:u)"),
                                   {"r": rid, "u": list(users)}).rowcount
            labs = list(db.scalars(select(LabResult).join(Record, Record.id == LabResult.record_id)
                                   .where(Record.project_id == p.id, LabResult.decision_by.in_(users))))
            for lab in labs:
                print(f"  lab decision removed: {db.get(Record, lab.record_id).number} ({lab.decision})")
                lab.decision = lab.decision_note = lab.decision_by = lab.decision_at = None
            db.flush()
            print(f"\n  records put back: {len(done)}   their events removed: {n_ev}   lab decisions removed: {len(labs)}")
            if n_ev != len([e for e in test if e.record_id in done]):
                sys.exit("Events could not be removed (database migration 0030 missing?). Nothing was changed.")
            if not a.commit:
                raise Trial
            print("\nDone.")
    except Trial:
        print("\nTRIAL RUN: nothing was written. Add --commit to apply (back up the database first).")


if __name__ == "__main__":
    main()
