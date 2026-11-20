# Intelligent House Owner: DROW Client Platform
*An AYOK & AYOK Initiative*

**Live:** https://iho-drow-client-platform.vercel.app  ·  Team panel: https://iho-drow-client-platform.vercel.app/admin

A website where clients fill the **DROW discovery form** (Dream Home + Resources) from their phone.
Every submission is saved on **your server** and written into **Excel files** automatically.
Your team signs in to a private panel to read each client, write the **Options** and **Way Forward**, and download the Excel.

```
Client scans QR → fills form (4 short steps) → gets reference no. IHO-2026-0001
                                   │
                                   ▼
                    Saved to database + Excel on your server
                                   │
                                   ▼
        Team panel (/admin) → read details → write Options / Way Forward → Excel updates
```

---

## What's inside

| Part | What it does |
|---|---|
| **Client form** `/` | Mobile-first, 4 steps: About you → D Dream Home → R Resources → Review & send. Purple + gold brand colours from the DROW PDF, Poppins font. Checks answers before moving on, keeps a draft on the phone if the client closes the page, accepts up to 6 reference photos / PDFs. |
| **Thank-you page** | Shows the client their reference number and the "What happens next" steps. |
| **Team panel** `/admin` | Password login. List with search and status filters, full client view with photos, WhatsApp / call links, Options + Way Forward + notes, status tracking, delete. |
| **Excel (master)** `data/excel/DROW_Submissions.xlsx` | One row per client, every answer in its own column, filters on, plus a Summary sheet with counts per status. |
| **Excel (per client)** `data/excel/clients/IHO-2026-0001_Name.xlsx` | The same DROW layout as your sheet: Dream Home (Inside / Outer amenities, Designs), Resources (Land, Budget), Options, Way Forward. |
| **Uploads** `data/uploads/<ref>/` | Reference photos / PDFs each client attached. |

The Excel files are rebuilt from the database after every submission and every team update, so they are always current. They are written safely (temp file then swap), so a crash never leaves a broken file.

---

## Run it on your computer (5 minutes)

You need **Python 3.10+** ([python.org](https://www.python.org/downloads/)).

**Windows:** double-click `run.bat`
**Mac / Linux:** `./run.sh`

The first run installs the packages and creates a `.env` file. Open `.env` and set:

```
SECRET_KEY=any-long-random-text
ADMIN_PASSWORD=your-team-password
```

Then run again and open:
- Client form: http://localhost:5000
- Team panel: http://localhost:5000/admin (username `admin` unless you change `ADMIN_USERNAME`)

Manual way:
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then edit it
python app.py
```

---

## Put it online

Excel files and uploads are stored **on the server's disk**, so use hosting that keeps files:
a VPS, or a platform with a persistent disk. Vercel, Netlify and similar static or serverless hosts will **not** keep the data.

### Option A: VPS (Hostinger, DigitalOcean, AWS Lightsail…), recommended
```bash
git clone <your repo> drow && cd drow
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set SECRET_KEY, ADMIN_PASSWORD, COOKIE_SECURE=1, BEHIND_PROXY=1
gunicorn -w 2 -b 127.0.0.1:8000 app:app
```
Put Nginx in front with HTTPS (Let's Encrypt), and run gunicorn as a systemd service. Nginx: `client_max_body_size 60M;` so photo uploads work.

### Option B: Docker
```bash
docker build -t drow .
docker run -d -p 8000:8000 --env-file .env -v drow_data:/app/data --name drow drow
```

### Option C: Render / Railway
Start command `gunicorn -w 2 -b 0.0.0.0:$PORT app:app`, add the `.env` values as environment variables, attach a **persistent disk** and set `DATA_DIR` to its mount path (e.g. `/var/data`).

**After it's live:** point the QR code on the DROW PDF to your form URL (e.g. `https://drow.yourdomain.com`).

---

## Getting the Excel

- **Team panel:** "Download Excel" (all clients) or "Client Excel" (one client's DROW sheet).
- **On the server:** `data/excel/`. You can open it directly or sync the folder to Google Drive / OneDrive.
- **By email (optional):** fill the `SMTP_*` and `NOTIFY_EMAIL` values in `.env` and the team gets an email with the latest Excel attached on every new submission.

**Backups:** copy the whole `data/` folder. `data/drow.db` is the main record; the Excel files can always be rebuilt from it.

---

## Change things

| To change | Edit |
|---|---|
| Amenity lists, styles, timelines, currencies, statuses | `drow/choices.py` (form, checks and Excel all read from here) |
| Colours / fonts | top of `static/css/style.css` (`--purple`, `--gold` …) |
| Wording on the form | `templates/form.html` |
| Excel layout | `drow/excel.py` |
| Reference number prefix | `REF_PREFIX` in `.env` |
| Time zone for dates | `APP_TIMEZONE` in `.env` (default `Asia/Kolkata`) |

---

## Built-in protection

Security token on every form, hidden spam-trap field, rate limits on submissions and login, checks on every answer on the server (not just in the browser), upload type and size limits, safe file names, and a password-protected team panel with secure cookies.

## Project layout
```
app.py                 web app (routes, validation, admin)
drow/choices.py        all form options
drow/storage.py        SQLite database
drow/excel.py          Excel writers (master + per-client DROW sheet)
templates/             pages (form, thank-you, admin)
static/                CSS, JS, logo
data/                  created on first run: database, Excel, uploads  (keep private, back it up)
```

---

## Deploy free: GitHub + Vercel + Supabase

Vercel does not keep files on disk, so in the cloud the app stores everything in **Supabase** (free tier):

| Data | Local | Cloud |
|---|---|---|
| Submissions | `data/drow.db` (SQLite) | Supabase Postgres (`DATABASE_URL`) |
| Uploaded photos / PDFs | `data/uploads/` | Supabase Storage, private bucket `drow-uploads`. The browser uploads straight to Supabase, so Vercel's 4.5 MB request limit does not matter. |
| Excel files | `data/excel/` | Built fresh from the database each time you click download |

Cloud mode turns on by itself when `DATABASE_URL` and the `SUPABASE_*` variables are set.

1. **Supabase**: create a free project at [supabase.com](https://supabase.com).
   - *Connect* → **Transaction pooler** → copy the URI (put your database password in it) → `DATABASE_URL`
   - *Project Settings → API* → Project URL → `SUPABASE_URL`, `service_role` key → `SUPABASE_SERVICE_ROLE_KEY`
   - The table and the private storage bucket are created automatically on first use.
2. **GitHub**: push this folder to a repository.
3. **Vercel**: *Add New → Project* → import the repository (framework: Flask/Other, no build settings needed).
   Add Environment Variables: `SECRET_KEY`, `ADMIN_PASSWORD`, `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (optionally `ADMIN_USERNAME`, `APP_TIMEZONE`, `REF_PREFIX`, `SMTP_*`). Deploy.
   Every `git push` to `main` redeploys.

Note: free Supabase projects pause after 7 days with no activity; open the Supabase dashboard to resume.
