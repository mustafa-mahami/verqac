"""Results that take long to work out (a register of thousands of rows, the KPI scorecard), kept per worker process
and served again while the data they come from is unchanged.

The check is a fingerprint the database computes over the rows the result is made of (cheap: one scan in C, no
rows travel), so a kept result is never stale: any change to those rows changes the fingerprint."""
import threading
from collections import OrderedDict

from sqlalchemy import text

_MAX = 300
_lock = threading.Lock()
_store: "OrderedDict[tuple, tuple[str, object]]" = OrderedDict()


def fingerprint(db, sql: str, params: dict) -> str:
    return db.execute(text(sql), params).scalar() or ""


def get(key: tuple, fp: str):
    with _lock:
        hit = _store.get(key)
        if hit and hit[0] == fp:
            _store.move_to_end(key)
            return hit[1]
    return None


def put(key: tuple, fp: str, value) -> None:
    with _lock:
        _store[key] = (fp, value)
        _store.move_to_end(key)
        while len(_store) > _MAX:
            _store.popitem(last=False)


# what a project's records look like now: every column of every record of the type (as the user may see them),
# with the details the register shows beside them, and the project's settings (kind names, periods)
RECORDS_FP = """
SELECT md5(coalesce((SELECT string_agg(md5(r::text), '' ORDER BY r.id) FROM records r
                      WHERE r.project_id = :p AND r.record_type_id = :t), '')
        || coalesce((SELECT string_agg(md5(d::text), '' ORDER BY d.record_id) FROM submittal_details d
                      JOIN records r ON r.id = d.record_id WHERE r.project_id = :p AND r.record_type_id = :t), '')
        || coalesce((SELECT string_agg(md5(l::text), '' ORDER BY l.record_id) FROM lab_results l
                      JOIN records r ON r.id = l.record_id WHERE r.project_id = :p AND r.record_type_id = :t), '')
        || coalesce((SELECT md5(settings::text) FROM projects WHERE id = :p), ''))
"""

PROJECT_FP = """
SELECT md5(coalesce((SELECT string_agg(md5(r::text), '' ORDER BY r.id) FROM records r WHERE r.project_id = :p), '')
        || coalesce((SELECT string_agg(md5(l::text), '' ORDER BY l.record_id) FROM lab_results l
                      JOIN records r ON r.id = l.record_id WHERE r.project_id = :p), '')
        || coalesce((SELECT count(*)::text || '/' || coalesce(max(e.id), 0)::text FROM record_events e
                      JOIN records r ON r.id = e.record_id WHERE r.project_id = :p), '')
        || coalesce((SELECT string_agg(md5(k::text), '' ORDER BY k.id) FROM concrete_classes k WHERE k.project_id = :p), '')
        || coalesce((SELECT md5(settings::text) FROM projects WHERE id = :p), ''))
"""


def time_slot(minutes: int = 5) -> int:
    """Overdue flags move with the clock: a kept result is good for a few minutes at most."""
    import time
    return int(time.time() // (60 * minutes))
