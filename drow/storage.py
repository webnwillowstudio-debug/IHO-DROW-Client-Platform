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


def now_iso_precise():
    # message_at also identifies *which* message a client reply answers, so two
    # edits in the same second must still get different values
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class Store:
    def __init__(self, db_path, ref_prefix="IHO"):
        self.db_path = db_path
        self.ref_prefix = ref_prefix
        with self.conn() as c:
            c.executescript(SCHEMA)
            have = {r["name"] for r in c.execute("PRAGMA table_info(submissions)")}
            for col in ('client_message', 'message_at', 'ask_reply', 'client_reply', 'reply_at', 'reply_for'):
                if col not in have:
                    c.execute(f"ALTER TABLE submissions ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")

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
        self.set_data(sid, "reference_files", files)

    def set_data(self, sid, key, value):
        """Change one key inside the stored form data (e.g. team_files)."""
        data = self.get(sid)["data"]
        data[key] = value
        with self.conn() as c:
            c.execute(
                "UPDATE submissions SET data_json=? WHERE id=?",
                (json.dumps(data, ensure_ascii=False), sid),
            )

    def update_team(self, sid, status, options, way_forward, team_notes, client_message=None, ask_reply=None):
        ts = now_iso()
        with self.conn() as c:
            c.execute(
                "UPDATE submissions SET status=?, options=?, way_forward=?, team_notes=?, updated_at=?"
                " WHERE id=?",
                (status, options, way_forward, team_notes, ts, sid),
            )
            if ask_reply is not None:
                # "" / "1" (YES-No) / "slots". A new kind of question means an
                # old answer no longer counts, so message_at moves too.
                c.execute(
                    "UPDATE submissions SET message_at = CASE WHEN ask_reply <> ? THEN ? ELSE message_at END,"
                    " ask_reply=? WHERE id=?",
                    (ask_reply, now_iso_precise(), ask_reply, sid),
                )
            if client_message is not None:
                # message_at only moves when the text actually changes
                c.execute(
                    "UPDATE submissions SET message_at = CASE WHEN client_message <> ? THEN ? ELSE message_at END,"
                    " client_message=? WHERE id=?",
                    (client_message, now_iso_precise(), client_message, sid),
                )

    def delete(self, sid):
        with self.conn() as c:
            c.execute("DELETE FROM submissions WHERE id=?", (sid,))

    def set_reply(self, sid, reply):
        """Client's answer to the current message (YES / NO / time slots), stamped with which message it answers."""
        with self.conn() as c:
            c.execute(
                "UPDATE submissions SET client_reply=?, reply_at=?, reply_for=message_at WHERE id=?",
                (reply, now_iso(), sid),
            )

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
ALTER TABLE submissions ADD COLUMN IF NOT EXISTS client_message TEXT NOT NULL DEFAULT '';
ALTER TABLE submissions ADD COLUMN IF NOT EXISTS message_at TEXT NOT NULL DEFAULT '';
ALTER TABLE submissions ADD COLUMN IF NOT EXISTS ask_reply TEXT NOT NULL DEFAULT '';
ALTER TABLE submissions ADD COLUMN IF NOT EXISTS client_reply TEXT NOT NULL DEFAULT '';
ALTER TABLE submissions ADD COLUMN IF NOT EXISTS reply_at TEXT NOT NULL DEFAULT '';
ALTER TABLE submissions ADD COLUMN IF NOT EXISTS reply_for TEXT NOT NULL DEFAULT '';
-- Keep the table private: no access through Supabase's public Data API.
-- The app connects as the database owner, which RLS does not restrict.
ALTER TABLE submissions ENABLE ROW LEVEL SECURITY;
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

    def set_data(self, sid, key, value):
        data = self.get(sid)["data"]
        data[key] = value
        with self.conn() as c:
            c.execute("UPDATE submissions SET data_json=%s WHERE id=%s",
                      (json.dumps(data, ensure_ascii=False), sid))

    def update_team(self, sid, status, options, way_forward, team_notes, client_message=None, ask_reply=None):
        ts = now_iso()
        with self.conn() as c:
            c.execute(
                "UPDATE submissions SET status=%s, options=%s, way_forward=%s, team_notes=%s, updated_at=%s"
                " WHERE id=%s",
                (status, options, way_forward, team_notes, ts, sid),
            )
            if ask_reply is not None:
                c.execute(
                    "UPDATE submissions SET message_at = CASE WHEN ask_reply <> %s THEN %s ELSE message_at END,"
                    " ask_reply=%s WHERE id=%s",
                    (ask_reply, now_iso_precise(), ask_reply, sid),
                )
            if client_message is not None:
                c.execute(
                    "UPDATE submissions SET message_at = CASE WHEN client_message <> %s THEN %s ELSE message_at END,"
                    " client_message=%s WHERE id=%s",
                    (client_message, now_iso_precise(), client_message, sid),
                )

    def delete(self, sid):
        with self.conn() as c:
            c.execute("DELETE FROM submissions WHERE id=%s", (sid,))

    def set_reply(self, sid, reply):
        """Client's answer to the current message (YES / NO / time slots), stamped with which message it answers."""
        with self.conn() as c:
            c.execute(
                "UPDATE submissions SET client_reply=%s, reply_at=%s, reply_for=message_at WHERE id=%s",
                (reply, now_iso(), sid),
            )

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
