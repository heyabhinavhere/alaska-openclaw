"""P18: SQLite connection robustness. connect() must set a busy_timeout (a writer
WAITS for the lock instead of failing 'database is locked') and WAL (readers don't
block the writer; also upgrades migration-created test DBs). Surfaced by the live
E2E test — draft-queue-interventions died on 'database is locked' while
run-cohort-day + judge-credgpt-reviews were writing concurrently."""

from __future__ import annotations

import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from pmf_os.store import PmfStore  # noqa: E402


def _store() -> PmfStore:
    db = str(Path(tempfile.mkdtemp(prefix="pmf_p18_")) / "a.db")
    store = PmfStore(db)
    store.connect().close()  # create the file (+ apply WAL)
    return store


def test_connect_sets_busy_timeout_and_wal():
    store = _store()
    with store.connect() as conn:
        busy = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert busy >= 30000  # writers wait, don't fail instantly
    assert str(journal).lower() == "wal"


def test_concurrent_writers_do_not_hit_database_is_locked():
    store = _store()
    with store.connect() as conn:
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, who TEXT)")
        conn.commit()

    errors: list[str] = []

    def writer(tag: str) -> None:
        try:
            for i in range(25):
                with store.connect() as c:
                    c.execute("INSERT INTO t (who) VALUES (?)", (f"{tag}-{i}",))
                    c.commit()
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))

    threads = [threading.Thread(target=writer, args=(t,)) for t in ("a", "b", "c")]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    assert errors == [], errors  # no "database is locked"
    with store.connect() as conn:
        assert conn.execute("SELECT count(*) FROM t").fetchone()[0] == 75  # 3×25, none lost


if __name__ == "__main__":
    import subprocess

    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-q"]))
