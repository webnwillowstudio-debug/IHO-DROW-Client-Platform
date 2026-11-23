"""Intelligent House Owner - DROW client platform.

Clients fill the DROW discovery form on the website. Every submission is
saved to a database and written into Excel files on the server
(data/excel/). The team signs in at /admin to read submissions, fill in
Options and Way Forward, and download the Excel files.

Run locally:   python app.py
Production:    gunicorn -w 2 -b 0.0.0.0:8000 app:app
"""

import hmac
import os
import re
import secrets
import smtplib
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from functools import wraps

from flask import (Flask, abort, flash, jsonify, redirect, render_template, request,
                   send_file, send_from_directory, session, url_for)
from markupsafe import Markup, escape
from werkzeug.datastructures import MultiDict
from werkzeug.utils import secure_filename

from drow import choices as C
from drow.excel import build_client, build_master, client_file_name
from drow.cloud import SupabaseStorage
from drow.storage import PgStore, Store

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------- settings
def load_env_file(path):
    """Tiny .env reader so no extra package is needed."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env_file(os.path.join(BASE_DIR, ".env"))

ON_VERCEL = bool(os.environ.get("VERCEL"))
# Vercel's disk is read-only except /tmp (and /tmp is wiped). In cloud mode only
# throw-away files (the Excel built for a download) are written there.
DATA_DIR = os.path.abspath(os.environ.get(
    "DATA_DIR", "/tmp/drow" if ON_VERCEL else os.path.join(BASE_DIR, "data")))
EXCEL_DIR = os.path.join(DATA_DIR, "excel")
CLIENT_XLSX_DIR = os.path.join(EXCEL_DIR, "clients")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
MASTER_XLSX = os.path.join(EXCEL_DIR, "DROW_Submissions.xlsx")
for d in (DATA_DIR, EXCEL_DIR, CLIENT_XLSX_DIR, UPLOAD_DIR):
    os.makedirs(d, exist_ok=True)

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
APP_TIMEZONE = os.environ.get("APP_TIMEZONE", "Asia/Kolkata")
REF_PREFIX = os.environ.get("REF_PREFIX", "IHO")

ALLOWED_EXT = {"jpg", "jpeg", "png", "webp", "heic", "pdf"}
MAX_FILES = 6
MAX_FILE_MB = 8
TEAM_MAX_FILE_MB = 25  # site visit reports with photos can be big
CLIENT_LOGIN_DAYS = 180  # client stays signed in to the status page this long

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    MAX_CONTENT_LENGTH=(MAX_FILES * MAX_FILE_MB + 2) * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(days=CLIENT_LOGIN_DAYS),
    SESSION_COOKIE_SECURE=ON_VERCEL or os.environ.get("COOKIE_SECURE", "0") == "1",
)
if ON_VERCEL and not os.environ.get("SECRET_KEY"):
    raise RuntimeError("Set SECRET_KEY in the Vercel project's Environment Variables.")
if ON_VERCEL or os.environ.get("BEHIND_PROXY", "0") == "1":
    from werkzeug.middleware.proxy_fix import ProxyFix

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Cloud mode: submissions in Postgres (DATABASE_URL), uploads in Supabase Storage.
# Local mode (nothing set): SQLite file + uploads folder under DATA_DIR.
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
if ON_VERCEL and not DATABASE_URL:
    raise RuntimeError("Set DATABASE_URL in the Vercel project's Environment Variables.")
store = PgStore(DATABASE_URL, REF_PREFIX) if DATABASE_URL else Store(os.path.join(DATA_DIR, "drow.db"), REF_PREFIX)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
cloud_files = (SupabaseStorage(SUPABASE_URL, SUPABASE_KEY, os.environ.get("SUPABASE_BUCKET", "drow-uploads"))
               if SUPABASE_URL and SUPABASE_KEY else None)


# ---------------------------------------------------------------- template filters
def indian_group(n):
    s = str(int(round(n)))
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts) + "," + tail


@app.template_filter("money")
def money(amount, currency):
    if not isinstance(amount, (int, float)):
        return ""
    if currency == "INR":
        words = ""
        if amount >= 1e7:
            words = f" ({amount / 1e7:.2f}".rstrip("0").rstrip(".") + " Cr)"
        elif amount >= 1e5:
            words = f" ({amount / 1e5:.2f}".rstrip("0").rstrip(".") + " L)"
        return f"₹ {indian_group(amount)}{words}"
    return f"{currency or ''} {amount:,.0f}".strip()


_url_re = re.compile(r"(https?://[^\s<]+)")


@app.template_filter("linkify")
def linkify(text):
    safe = str(escape(text or ""))
    return Markup(_url_re.sub(r'<a href="\1" target="_blank" rel="noopener nofollow">\1</a>', safe))

try:
    from zoneinfo import ZoneInfo

    TZ = ZoneInfo(APP_TIMEZONE)
except Exception:  # missing tz database on some Windows installs
    TZ = None


def local_time(iso):
    dt = datetime.fromisoformat(iso)
    if TZ:
        dt = dt.astimezone(TZ)
    return dt.strftime("%d %b %Y, %I:%M %p")


app.add_template_filter(lambda iso: local_time(iso) if iso else "", "localtime")


def with_local(row):
    row["_created_local"] = local_time(row["created_at"])
    row["_updated_local"] = local_time(row["updated_at"])
    return row


# ---------------------------------------------------------------- excel sync
_excel_lock = threading.Lock()


def sync_excel(row_id=None):
    """Rebuild the master Excel (and one client's DROW sheet)."""
    with _excel_lock:
        rows = [with_local(r) for r in store.all()]
        build_master(list(reversed(rows)), MASTER_XLSX)  # oldest first in the sheet
        if row_id is not None:
            row = next((r for r in rows if r["id"] == row_id), None)
            if row:
                build_client(row, os.path.join(CLIENT_XLSX_DIR, client_file_name(row)))


# ---------------------------------------------------------------- security
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


def check_csrf():
    sent = request.form.get("_csrf", "") or request.headers.get("X-CSRF-Token", "")
    if not sent or not hmac.compare_digest(sent, session.get("_csrf", "")):
        abort(400, "Your session expired. Please reload the page and try again.")


_hits = defaultdict(deque)


def rate_limited(key, limit, window):
    now = time.time()
    q = _hits[key]
    while q and q[0] < now - window:
        q.popleft()
    if len(q) >= limit:
        return True
    q.append(now)
    return False


def client_ip():
    return request.remote_addr or "unknown"


@app.after_request
def security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return resp


# ---------------------------------------------------------------- validation
def clean(s, n=200):
    return (s or "").replace("\r\n", "\n").replace("\r", "\n").strip()[:n]


def pick(value, allowed):
    return value if value in allowed else ""


def number(s, lo=0, hi=None, integer=False):
    s = (s or "").replace(",", "").strip()
    if not s:
        return None
    try:
        v = int(s) if integer else float(s)
    except ValueError:
        return "bad"
    if v < lo or (hi is not None and v > hi):
        return "bad"
    if not integer and float(v).is_integer():
        v = int(v)
    return v


def multi(field, allowed, extra_field):
    chosen = [v for v in request.form.getlist(field) if v in allowed]
    extra = [clean(x, 60) for x in request.form.get(extra_field, "").split(",")]
    extra = [x for x in extra if x][:10]
    return chosen + [x for x in extra if x not in chosen]


def validate_form():
    f = request.form
    e = {}
    data = {
        "client_name": clean(f.get("client_name"), 120),
        "phone": clean(f.get("phone"), 30),
        "project_location": clean(f.get("project_location"), 200),
        # Dream home
        "inside_amenities": multi("inside_amenities", C.INSIDE_AMENITIES, "inside_other"),
        "outer_amenities": multi("outer_amenities", C.OUTER_AMENITIES, "outer_other"),
        "arch_style": pick(f.get("arch_style"), C.ARCH_STYLES),
        "design_notes": clean(f.get("design_notes"), 3000),
        # Resources
        "plot_area": number(f.get("plot_area"), 0, 10_000_000),
        "plot_unit": pick(f.get("plot_unit"), C.AREA_UNITS),
        "land_owner": pick(f.get("land_owner"), C.LAND_OWNERSHIP),
        "site_conditions": clean(f.get("site_conditions"), 3000),
        "budget_currency": pick(f.get("budget_currency"), C.CURRENCIES),
        "budget_amount": number(f.get("budget_amount"), 0, 1e13),
        "reference_files": [],
    }
    if data["arch_style"] == "Other" and clean(f.get("arch_style_other")):
        data["arch_style"] = "Other: " + clean(f.get("arch_style_other"), 80)

    if len(data["client_name"]) < 2:
        e["client_name"] = "Please enter your full name."
    digits = "".join(ch for ch in data["phone"] if ch.isdigit())
    if not 7 <= len(digits) <= 15:
        e["phone"] = "Please enter a valid phone / WhatsApp number with country code."
    if not data["project_location"]:
        e["project_location"] = "Please tell us where the house will be built."
    if not data["inside_amenities"] and not data["outer_amenities"]:
        e["amenities"] = "Please choose at least one amenity you want."
    if not data["arch_style"]:
        e["arch_style"] = "Please choose a design style (or 'Not sure')."
    if not data["land_owner"]:
        e["land_owner"] = "Please tell us whose name the land is in."
    if data["plot_area"] == "bad":
        e["plot_area"] = "Please enter the plot area as a number."
    if data["plot_area"] not in (None, "bad") and not data["plot_unit"]:
        e["plot_area"] = "Please choose the unit (Cent, Sq.ft ...)."
    if data["budget_amount"] in (None, "bad"):
        e["budget_amount"] = "Please enter your estimated total budget as a number."
    elif not data["budget_currency"]:
        e["budget_amount"] = "Please choose the currency."
    if not f.get("consent"):
        e["consent"] = "Please agree so our team can contact you."
    return data, e


def save_uploads(ref):
    files = [x for x in request.files.getlist("references") if x and x.filename]
    saved = []
    folder = os.path.join(UPLOAD_DIR, ref)
    for fs in files[:MAX_FILES]:
        name = secure_filename(fs.filename) or "file"
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in ALLOWED_EXT:
            continue
        fs.stream.seek(0, os.SEEK_END)
        size = fs.stream.tell()
        fs.stream.seek(0)
        if size > MAX_FILE_MB * 1024 * 1024:
            continue
        os.makedirs(folder, exist_ok=True)
        final = f"{uuid.uuid4().hex[:6]}_{name}"
        fs.save(os.path.join(folder, final))
        saved.append(final)
    return saved


def upload_name(filename):
    """Safe stored name with a short random prefix, or None if not allowed."""
    name = secure_filename(filename or "") or "file"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED_EXT:
        return None
    return f"{uuid.uuid4().hex[:6]}_{name}"[:120]


def cloud_uploaded_files():
    """Paths the browser uploaded to Supabase. Only paths this server signed
    for this visitor's session are accepted."""
    issued = set(session.pop("issued_uploads", []))
    sent = request.form.getlist("uploaded")
    return [p for p in dict.fromkeys(sent) if p in issued][:MAX_FILES]


def notify_team(row):
    """Optional email to the team on each new submission (set SMTP_* in .env)."""
    host, to = os.environ.get("SMTP_HOST"), os.environ.get("NOTIFY_EMAIL")
    if not host or not to:
        return

    def send():
        try:
            d = row["data"]
            msg = EmailMessage()
            msg["Subject"] = f"New DROW form: {row['ref']} - {d['client_name']}"
            msg["From"] = os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER", "")
            msg["To"] = to
            msg.set_content(
                f"New Intelligent House Owner enquiry\n\n"
                f"Ref: {row['ref']}\nName: {d['client_name']}\nPhone: {d['phone']}\n"
                f"Project location: {d['project_location']}\n"
                f"Budget: {d.get('budget_currency')} {d.get('budget_amount')}\n"
                f"Style: {d.get('arch_style')}\n\nOpen the admin panel to see everything."
            )
            with open(MASTER_XLSX, "rb") as fh:
                msg.add_attachment(fh.read(), maintype="application",
                                   subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                   filename="DROW_Submissions.xlsx")
            port = int(os.environ.get("SMTP_PORT", "587"))
            with smtplib.SMTP(host, port, timeout=20) as s:
                s.starttls()
                if os.environ.get("SMTP_USER"):
                    s.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
                s.send_message(msg)
        except Exception as exc:  # never break the client's submission
            app.logger.warning("Email notification failed: %s", exc)

    if ON_VERCEL:  # serverless functions stop after the response, so send now
        send()
    else:
        threading.Thread(target=send, daemon=True).start()


def notify_reply(row):
    """Optional email to the team when a client answers a message (needs SMTP_* set)."""
    host, to = os.environ.get("SMTP_HOST"), os.environ.get("NOTIFY_EMAIL")
    if not host or not to:
        return
    try:
        msg = EmailMessage()
        slots = row.get("ask_reply") == "slots"
        what = "sent meeting times" if slots else f"replied {row['client_reply']}"
        msg["Subject"] = f"Client {what}: {row['ref']} - {row['client_name']}"
        msg["From"] = os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER", "")
        msg["To"] = to
        body = f"{row['client_name']} ({row['phone']}) {what} on the status page."
        if slots:
            body += "\n\n" + row["client_reply"]
        msg.set_content(body + "\n\nOpen the admin panel to follow up.")
        with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=20) as s:
            s.starttls()
            if os.environ.get("SMTP_USER"):
                s.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
            s.send_message(msg)
    except Exception as exc:
        app.logger.warning("Reply email failed: %s", exc)


# ---------------------------------------------------------------- client side
def form_context(values=None, errors=None):
    return dict(C=C, v=values if values is not None else MultiDict(), errors=errors or {}, max_files=MAX_FILES, max_mb=MAX_FILE_MB,
                direct_upload=bool(cloud_files))


@app.get("/")
def form():
    return render_template("form.html", **form_context())


@app.post("/submit")
def submit():
    check_csrf()
    if request.form.get("website"):  # honeypot field, humans never fill it
        return redirect(url_for("thanks"))
    if rate_limited(("submit", client_ip()), 5, 600):
        abort(429)
    data, errors = validate_form()
    if errors:
        return render_template("form.html", **form_context(request.form, errors)), 422
    row = store.create(data)
    files = cloud_uploaded_files() if cloud_files else save_uploads(row["ref"])
    if files:
        store.set_files(row["id"], files)
    sync_excel(row["id"])
    notify_team(store.get(row["id"]))
    session["last_ref"] = row["ref"]
    session["last_name"] = data["client_name"].split(" ")[0]
    client_sign_in(row["ref"])  # "Check my status" opens straight away
    return redirect(url_for("thanks"))


@app.post("/upload-urls")
def upload_urls():
    """Cloud mode: hand the browser one signed upload URL per file."""
    if not cloud_files:
        abort(404)
    check_csrf()
    if rate_limited(("upload", client_ip()), 10, 600):
        abort(429)
    files = (request.get_json(silent=True) or {}).get("files") or []
    out, issued = [], []
    for f in files[:MAX_FILES]:
        name = upload_name(str(f.get("name", "")))
        size = f.get("size") or 0
        if not name or not isinstance(size, int) or size > MAX_FILE_MB * 1024 * 1024:
            out.append(None)
            continue
        path = f"{datetime.now(timezone.utc):%Y-%m}/{uuid.uuid4().hex[:12]}/{name}"
        out.append({"path": path, "url": cloud_files.signed_upload_url(path)})
        issued.append(path)
    session["issued_uploads"] = (session.get("issued_uploads", []) + issued)[-MAX_FILES * 3:]
    return jsonify(files=out)


@app.get("/thank-you")
def thanks():
    return render_template("thanks.html", ref=session.get("last_ref"), name=session.get("last_name"))


def phone_tail(phone, n=4):
    return "".join(ch for ch in (phone or "") if ch.isdigit())[-n:]


def client_sign_in(ref):
    """Remember the client in this browser so they don't type the ref + phone every visit."""
    session["status_ref"] = ref
    session.permanent = True


def signed_in_row():
    ref = session.get("status_ref")
    row = store.get_by_ref(ref) if ref else None
    if ref and not row:  # the submission was deleted
        session.pop("status_ref", None)
    return row


def has_answer(row):
    return bool(row.get("client_reply") and row.get("reply_for") == row.get("message_at"))


def local_now():
    return datetime.now(TZ).replace(tzinfo=None) if TZ else datetime.now()


def render_status(row=None, ref="", error=None, just_replied=False, reply_error=None):
    label, note = C.CLIENT_STATUS.get(row["status"], (row["status"], "")) if row else ("", "")
    replied = bool(row and has_answer(row))
    can_reply = bool(row and row.get("ask_reply") and row.get("client_message") and not replied)
    return render_template("status.html", ref=ref, row=row, error=error, label=label, note=note,
                           steps=C.STATUSES[:4], C=C, replied=replied, can_reply=can_reply,
                           just_replied=just_replied, reply_error=reply_error,
                           team_files=(row["data"].get("team_files") or []) if row else [],
                           min_slot=local_now().strftime("%Y-%m-%dT00:00"))


@app.route("/status", methods=["GET", "POST"])
def status():
    """Client looks up their DROW: reference number + last 4 digits of their phone.
    Refs are sequential, so the phone check stops people reading each other's updates.
    After one successful lookup this browser stays signed in (client_sign_in)."""
    ref = clean(request.values.get("ref"), 40).upper().replace(" ", "")
    if request.method == "GET":
        row = signed_in_row()
        if row and (not ref or ref == row["ref"]):
            return render_status(row, row["ref"], just_replied=bool(session.pop("just_replied", False)))
        return render_status(ref=ref)
    check_csrf()
    if rate_limited(("status", client_ip()), 10, 600):
        abort(429)
    tail = "".join(ch for ch in request.form.get("phone4", "") if ch.isdigit())
    if re.fullmatch(r"\d{1,6}", ref):  # typed only the number part
        ref = f"{REF_PREFIX}-{datetime.now().year}-{int(ref):04d}"
    found = store.get_by_ref(ref) if ref else None
    if found and len(tail) == 4 and hmac.compare_digest(tail, phone_tail(found["phone"])):
        client_sign_in(found["ref"])
        return redirect(url_for("status"))  # a refresh won't re-send the form
    return render_status(ref=ref, error="We could not find a DROW with that reference number and phone. "
                                        "Please check both and try again.")


@app.get("/status/logout")
def status_logout():
    for k in ("status_ref", "just_replied", "last_ref", "last_name"):
        session.pop(k, None)
    if not session.get("admin"):
        session.permanent = False
    return redirect(url_for("status"))


def read_slots():
    """Up to 3 'YYYY-MM-DDTHH:MM' values from the form -> readable lines, or an error."""
    out = []
    for i in (1, 2, 3):
        raw = clean(request.form.get(f"slot{i}"), 20)
        if not raw:
            continue
        try:
            dt = datetime.strptime(raw, "%Y-%m-%dT%H:%M")
        except ValueError:
            return None, "Please pick a date and time for each option."
        if dt < local_now() - timedelta(hours=1):
            return None, "Please pick times in the coming days, not in the past."
        out.append(f"Option {len(out) + 1}: {dt.strftime('%a %d %b %Y, %I:%M %p')}")
    if not out:
        return None, "Please pick at least one date and time."
    return "\n".join(out), None


@app.post("/status/reply")
def status_reply():
    """Client answers the team's message: YES / NO, or their preferred meeting times.
    Only for the DROW this browser is signed in to."""
    check_csrf()
    if rate_limited(("reply", client_ip()), 10, 600):
        abort(429)
    row = signed_in_row()
    if not row:
        return redirect(url_for("status"))
    if row.get("ask_reply") and row.get("client_message") and not has_answer(row):
        if row["ask_reply"] == "slots":
            answer, err = read_slots()
            if err:
                return render_status(row, row["ref"], reply_error=err), 422
        else:
            answer = {"yes": "YES", "no": "NO"}.get(request.form.get("answer", "").lower())
        if answer:
            store.set_reply(row["id"], answer)
            notify_reply(store.get(row["id"]))
            session["just_replied"] = True
    return redirect(url_for("status"))


@app.get("/status/file/<path:name>")
def status_file(name):
    """A document the team shared with this client (e.g. the site visit report)."""
    row = signed_in_row()
    f = next((f for f in row["data"].get("team_files") or [] if f["path"] == name), None) if row else None
    if not f:
        abort(404)
    return serve_stored(row, name, download_as=f["name"] if request.args.get("download") else None)


def serve_stored(row, name, download_as=None):
    if cloud_files:
        return redirect(cloud_files.signed_download_url(name, download_as=download_as))
    return send_from_directory(os.path.join(UPLOAD_DIR, row["ref"]), name,
                               as_attachment=bool(download_as), download_name=download_as)


@app.get("/healthz")
def healthz():
    return {"ok": True}


# ---------------------------------------------------------------- admin
def admin_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not session.get("admin"):
            return redirect(url_for("admin_login", next=request.path))
        return fn(*a, **kw)

    return wrapper


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        check_csrf()
        if rate_limited(("login", client_ip()), 8, 900):
            abort(429)
        u, p = request.form.get("username", ""), request.form.get("password", "")
        if not ADMIN_PASSWORD:
            error = "ADMIN_PASSWORD is not set on the server. Add it to the .env file."
        elif hmac.compare_digest(u, ADMIN_USERNAME) and hmac.compare_digest(p, ADMIN_PASSWORD):
            session.clear()
            session["admin"] = True
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/admin") else url_for("admin_list"))
        else:
            error = "Wrong username or password."
    return render_template("admin_login.html", error=error)


@app.get("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))


@app.get("/admin")
@admin_required
def admin_list():
    q = clean(request.args.get("q"), 80)
    st = pick(request.args.get("status"), C.STATUSES)
    rows = [with_local(r) for r in store.all(q or None, st or None)]
    return render_template("admin_list.html", rows=rows, q=q, status=st,
                           counts=store.counts(), C=C, total=sum(store.counts().values()))


@app.route("/admin/c/<int:sid>", methods=["GET", "POST"])
@admin_required
def admin_detail(sid):
    row = store.get(sid)
    if not row:
        abort(404)
    if request.method == "POST":
        check_csrf()
        store.update_team(
            sid,
            pick(request.form.get("status"), C.STATUSES) or row["status"],
            clean(request.form.get("options"), 8000),
            clean(request.form.get("way_forward"), 8000),
            clean(request.form.get("team_notes"), 4000),
            clean(request.form.get("client_message"), 6000),
            pick(request.form.get("ask_reply", ""), C.REPLY_KINDS),
        )
        sync_excel(sid)
        flash("Saved. The Excel files are updated.")
        return redirect(url_for("admin_detail", sid=sid))
    return render_template("admin_detail.html", r=with_local(row), d=row["data"], C=C,
                           direct_upload=bool(cloud_files), team_max_mb=TEAM_MAX_FILE_MB)


@app.post("/admin/c/<int:sid>/delete")
@admin_required
def admin_delete(sid):
    check_csrf()
    row = store.get(sid)
    if row:
        store.delete(sid)
        if cloud_files:
            try:
                cloud_files.delete((row["data"].get("reference_files") or [])
                                   + [f["path"] for f in row["data"].get("team_files") or []])
            except Exception as exc:
                app.logger.warning("Could not delete stored files: %s", exc)
        p = os.path.join(CLIENT_XLSX_DIR, client_file_name(row))
        if os.path.exists(p):
            os.remove(p)
        sync_excel()
        flash(f"Deleted {row['ref']}.")
    return redirect(url_for("admin_list"))


@app.get("/admin/excel")
@admin_required
def admin_excel():
    sync_excel()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return send_file(MASTER_XLSX, as_attachment=True, download_name=f"DROW_Submissions_{stamp}.xlsx")


@app.get("/admin/c/<int:sid>/excel")
@admin_required
def admin_client_excel(sid):
    row = store.get(sid)
    if not row:
        abort(404)
    sync_excel(sid)
    name = client_file_name(row)
    return send_file(os.path.join(CLIENT_XLSX_DIR, name), as_attachment=True, download_name=name)


@app.get("/admin/c/<int:sid>/file/<path:name>")
@admin_required
def admin_file(sid, name):
    row = store.get(sid)
    team = [f["path"] for f in row["data"].get("team_files") or []] if row else []
    if not row or name not in (row["data"].get("reference_files") or []) + team:
        abort(404)
    return serve_stored(row, name)


# ---- documents the team shares with the client (site visit report, plans ...)
@app.post("/admin/c/<int:sid>/upload-urls")
@admin_required
def admin_upload_urls(sid):
    """Cloud mode: signed URLs so the browser uploads straight to storage
    (Vercel refuses requests over 4.5 MB through the server)."""
    row = store.get(sid)
    if not cloud_files or not row:
        abort(404)
    check_csrf()
    out, issued = [], []
    for f in ((request.get_json(silent=True) or {}).get("files") or [])[:MAX_FILES]:
        name = upload_name(str(f.get("name", "")))
        size = f.get("size") or 0
        if not name or not isinstance(size, int) or size > TEAM_MAX_FILE_MB * 1024 * 1024:
            out.append(None)
            continue
        path = f"team/{row['ref']}/{uuid.uuid4().hex[:12]}/{name}"
        out.append({"path": path, "url": cloud_files.signed_upload_url(path)})
        issued.append(path)
    session["issued_team_uploads"] = (session.get("issued_team_uploads", []) + issued)[-30:]
    return jsonify(files=out)


@app.post("/admin/c/<int:sid>/files")
@admin_required
def admin_add_files(sid):
    check_csrf()
    row = store.get(sid)
    if not row:
        abort(404)
    added = []
    if cloud_files:  # already in storage; only accept paths this server signed
        issued = session.get("issued_team_uploads", [])
        added = [p for p in dict.fromkeys(request.form.getlist("uploaded")) if p in issued]
        session["issued_team_uploads"] = [p for p in issued if p not in added]
    else:
        folder = os.path.join(UPLOAD_DIR, row["ref"], "team")
        for fs in [x for x in request.files.getlist("files") if x and x.filename][:MAX_FILES]:
            name = upload_name(fs.filename)
            fs.stream.seek(0, os.SEEK_END)
            size = fs.stream.tell()
            fs.stream.seek(0)
            if not name or size > TEAM_MAX_FILE_MB * 1024 * 1024:
                continue
            os.makedirs(folder, exist_ok=True)
            fs.save(os.path.join(folder, name))
            added.append(f"team/{name}")
    if added:
        at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        files = (row["data"].get("team_files") or []) + [
            {"path": p, "name": p.rsplit("/", 1)[-1][7:], "at": at} for p in added]
        store.set_data(sid, "team_files", files)
        flash(f"Uploaded {len(added)} file(s). The client can open them on the status page.")
    else:
        flash(f"No file was uploaded. Use photos or PDF, up to {TEAM_MAX_FILE_MB} MB each.")
    return redirect(url_for("admin_detail", sid=sid) + "#client-files")


@app.post("/admin/c/<int:sid>/files/delete")
@admin_required
def admin_delete_file(sid):
    check_csrf()
    row = store.get(sid)
    if not row:
        abort(404)
    path = request.form.get("path", "")
    files = row["data"].get("team_files") or []
    if path in [f["path"] for f in files]:
        store.set_data(sid, "team_files", [f for f in files if f["path"] != path])
        try:
            if cloud_files:
                cloud_files.delete([path])
            else:
                full = os.path.join(UPLOAD_DIR, row["ref"], path)
                if os.path.isfile(full):
                    os.remove(full)
        except Exception as exc:
            app.logger.warning("Could not delete stored file: %s", exc)
        flash("File removed.")
    return redirect(url_for("admin_detail", sid=sid) + "#client-files")


@app.errorhandler(413)
def too_big(_):
    return render_template("message.html", title="Files too large",
                           text=f"Please upload up to {MAX_FILES} files, max {MAX_FILE_MB} MB each."), 413


@app.errorhandler(429)
def too_many(_):
    return render_template("message.html", title="Please wait a moment",
                           text="Too many attempts from this connection. Please try again in a few minutes."), 429


@app.errorhandler(400)
def bad_request(e):
    return render_template("message.html", title="Something went wrong",
                           text=getattr(e, "description", "Please reload the page and try again.")), 400


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    print(f"\n  DROW platform running:  http://localhost:{port}\n  Admin panel:            http://localhost:{port}/admin\n")
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
