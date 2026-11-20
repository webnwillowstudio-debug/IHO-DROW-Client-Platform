"""SQLite storage. The database is the source of truth; the Excel files are
rebuilt from it after every change, so a crash can never leave you with a
half-written spreadsheet and no record of the client."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS submissions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ref          TEXT UNIQUE,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'New',
    client_name  TEXT NOT NULL,
    phone        TEXT NOT NULL,
    data_json    TEXT NOT NULL,
    options      TEXT NOT NULL DEFAULT '',
    way_forward  TEXT NOT NULL DEFAULT '',
    team_notes   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sub_created ON submissions(created_at);
"""


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, db_path, ref_prefix="IHO"):
        self.db_path = db_path
        self.ref_prefix = ref_prefix
        with self.conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def conn(self):
        c = sqlite3.connect(self.db_path, timeout=15)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        try:
            yield c
            c.commit()
        finally:
            c.close()

    # ---- writes -----------------------------------------------------------
    def create(self, data):
        ts = now_iso()
        with self.conn() as c:
            cur = c.execute(
                "INSERT INTO submissions (created_at, updated_at, client_name, phone, data_json)"
                " VALUES (?, ?, ?, ?, ?)",
                (ts, ts, data["client_name"], data["phone"], json.dumps(data, ensure_ascii=False)),
            )
            sid = cur.lastrowid
            ref = f"{self.ref_prefix}-{datetime.now().year}-{sid:04d}"
            c.execute("UPDATE submissions SET ref=? WHERE id=?", (ref, sid))
        return self.get(sid)

    def set_files(self, sid, files):
        row = self.get(sid)
        data = row["data"]
        data["reference_files"] = files
        with self.conn() as c:
            c.execute(
                "UPDATE submissions SET data_json=? WHERE id=?",
                (json.dumps(data, ensure_ascii=False), sid),
            )

    def update_team(self, sid, status, options, way_forward, team_notes):
        with self.conn() as c:
            c.execute(
                "UPDATE submissions SET status=?, options=?, way_forward=?, team_notes=?, updated_at=?"
                " WHERE id=?",
                (status, options, way_forward, team_notes, now_iso(), sid),
            )

    def delete(self, sid):
        with self.conn() as c:
            c.execute("DELETE FROM submissions WHERE id=?", (sid,))

    # ---- reads ------------------------------------------------------------
    @staticmethod
    def _row(r):
        if r is None:
            return None
        d = dict(r)
        d["data"] = json.loads(d.pop("data_json"))
        return d

    def get(self, sid):
        with self.conn() as c:
            return self._row(c.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone())

    def get_by_ref(self, ref):
        with self.conn() as c:
            return self._row(c.execute("SELECT * FROM submissions WHERE ref=?", (ref,)).fetchone())

    def all(self, q=None, status=None):
        sql = "SELECT * FROM submissions WHERE 1=1"
        args = []
        if q:
            like = f"%{q}%"
            sql += " AND (client_name LIKE ? OR phone LIKE ? OR ref LIKE ? OR data_json LIKE ?)"
            args += [like, like, like, like]
        if status:
            sql += " AND status=?"
            args.append(status)
        sql += " ORDER BY id DESC"
        with self.conn() as c:
            return [self._row(r) for r in c.execute(sql, args).fetchall()]

    def counts(self):
        with self.conn() as c:
            rows = c.execute("SELECT status, COUNT(*) n FROM submissions GROUP BY status").fetchall()
        return {r["status"]: r["n"] for r in rows}


# ---------------------------------------------------------------- Postgres
PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS submissions (
    id           BIGSERIAL PRIMARY KEY,
    ref          TEXT UNIQUE,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'New',
    client_name  TEXT NOT NULL,
    phone        TEXT NOT NULL,
    data_json    TEXT NOT NULL,
    options      TEXT NOT NULL DEFAULT '',
    way_forward  TEXT NOT NULL DEFAULT '',
    team_notes   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sub_created ON submissions(created_at);
"""


class PgStore(Store):
    """Same interface as Store, backed by Postgres (Supabase, Neon, ...).
    Used when DATABASE_URL is set, e.g. on Vercel where the disk is not kept."""

    def __init__(self, url, ref_prefix="IHO"):
        import psycopg  # only needed in cloud mode
        from psycopg.rows import dict_row

        self._psycopg, self._dict_row = psycopg, dict_row
        self.url = url
        self.ref_prefix = ref_prefix
        with self.conn() as c:
            c.execute(PG_SCHEMA)

    @contextmanager
    def conn(self):
        # prepare_threshold=None keeps it working through pgbouncer / Supabase pooler
        c = self._psycopg.connect(self.url, row_factory=self._dict_row,
                                  prepare_threshold=None, connect_timeout=10)
        try:
            yield c
            c.commit()
        finally:
            c.close()

    def create(self, data):
        ts = now_iso()
        with self.conn() as c:
            sid = c.execute(
                "INSERT INTO submissions (created_at, updated_at, client_name, phone, data_json)"
                " VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (ts, ts, data["client_name"], data["phone"], json.dumps(data, ensure_ascii=False)),
            ).fetchone()["id"]
            ref = f"{self.ref_prefix}-{datetime.now().year}-{sid:04d}"
            c.execute("UPDATE submissions SET ref=%s WHERE id=%s", (ref, sid))
        return self.get(sid)

    def set_files(self, sid, files):
        data = self.get(sid)["data"]
        data["reference_files"] = files
        with self.conn() as c:
            c.execute("UPDATE submissions SET data_json=%s WHERE id=%s",
                      (json.dumps(data, ensure_ascii=False), sid))

    def update_team(self, sid, status, options, way_forward, team_notes):
        with self.conn() as c:
            c.execute(
                "UPDATE submissions SET status=%s, options=%s, way_forward=%s, team_notes=%s, updated_at=%s"
                " WHERE id=%s",
                (status, options, way_forward, team_notes, now_iso(), sid),
            )

    def delete(self, sid):
        with self.conn() as c:
            c.execute("DELETE FROM submissions WHERE id=%s", (sid,))

    def get(self, sid):
        with self.conn() as c:
            return self._row(c.execute("SELECT * FROM submissions WHERE id=%s", (sid,)).fetchone())

    def get_by_ref(self, ref):
        with self.conn() as c:
            return self._row(c.execute("SELECT * FROM submissions WHERE ref=%s", (ref,)).fetchone())

    def all(self, q=None, status=None):
        sql = "SELECT * FROM submissions WHERE TRUE"
        args = []
        if q:
            like = f"%{q}%"
            sql += " AND (client_name ILIKE %s OR phone ILIKE %s OR ref ILIKE %s OR data_json ILIKE %s)"
            args += [like, like, like, like]
        if status:
            sql += " AND status=%s"
            args.append(status)
        sql += " ORDER BY id DESC"
        with self.conn() as c:
            return [self._row(r) for r in c.execute(sql, args).fetchall()]

    def counts(self):
        with self.conn() as c:
            rows = c.execute("SELECT status, COUNT(*) AS n FROM submissions GROUP BY status").fetchall()
        return {r["status"]: r["n"] for r in rows}
