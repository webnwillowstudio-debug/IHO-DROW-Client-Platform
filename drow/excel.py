"""Excel output.

Two kinds of file are written to data/excel/:

* DROW_Submissions.xlsx      - one row per client, every answer in its own
                               column. Filter / sort it like any sheet.
* clients/<REF>_<name>.xlsx  - one DROW sheet per client, laid out like the
                               paper DROW form (Dream Home, Resources,
                               Options, Way Forward).

Both are rebuilt from the database, written to a temp file and then swapped
in, so the file on disk is never half-written.
"""

import os
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

try:  # file lock so two server workers never write the same file at once
    import fcntl
except ImportError:  # Windows dev machine
    fcntl = None

PURPLE = "4B2A7B"
LAVENDER = "F6F1FB"
LAVENDER_2 = "EDE5F7"
GOLD = "B8902F"
WHITE = "FFFFFF"
INK = "2E2347"

thin = Side(style="thin", color="D9CCEA")
BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)
FONT = "Poppins"  # falls back to the default font if Poppins isn't installed


def fill(hex_):
    return PatternFill("solid", start_color=hex_, end_color=hex_)


@contextmanager
def file_lock(path):
    lock_dir = os.path.join(os.path.dirname(path), ".locks")
    os.makedirs(lock_dir, exist_ok=True)
    with open(os.path.join(lock_dir, os.path.basename(path) + ".lock"), "w") as fh:
        if fcntl:
            fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl:
                fcntl.flock(fh, fcntl.LOCK_UN)


def atomic_save(wb, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".xlsx", dir=os.path.dirname(path))
    os.close(fd)
    try:
        wb.save(tmp)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def safe_name(s):
    s = re.sub(r"[^A-Za-z0-9]+", "_", s or "").strip("_")
    return s[:40] or "client"


def client_file_name(row):
    return f"{row['ref']}_{safe_name(row['client_name'])}.xlsx"


def j(items):
    return ", ".join(items) if items else ""


# --------------------------------------------------------------------------
# Master sheet: one row per client
# --------------------------------------------------------------------------
COLUMNS = [
    # (header, width, getter)
    ("Ref No.", 16, lambda r, d: r["ref"]),
    ("Submitted", 18, lambda r, d: r["_created_local"]),
    ("Status", 16, lambda r, d: r["status"]),
    ("Client Name", 24, lambda r, d: d.get("client_name")),
    ("Phone / WhatsApp", 18, lambda r, d: d.get("phone")),
    ("Project Location", 24, lambda r, d: d.get("project_location")),
    # D - Dream Home
    ("Inside Amenities", 45, lambda r, d: j(d.get("inside_amenities"))),
    ("Outer Amenities", 45, lambda r, d: j(d.get("outer_amenities"))),
    ("Architectural Style", 20, lambda r, d: d.get("arch_style")),
    ("Design References & Notes", 45, lambda r, d: d.get("design_notes")),
    ("Reference Files", 30, lambda r, d: j(d.get("reference_files"))),
    # R - Resources
    ("Plot Area", 10, lambda r, d: d.get("plot_area")),
    ("Area Unit", 9, lambda r, d: d.get("plot_unit")),
    ("Plot Details & Site Conditions", 45, lambda r, d: d.get("site_conditions")),
    ("Currency", 9, lambda r, d: d.get("budget_currency")),
    ("Estimated Total Budget", 18, lambda r, d: d.get("budget_amount")),
    # O / W - team
    ("O - Options (team)", 45, lambda r, d: r.get("options")),
    ("W - Way Forward (team)", 45, lambda r, d: r.get("way_forward")),
    ("Team Notes", 35, lambda r, d: r.get("team_notes")),
    ("Message to Client", 50, lambda r, d: r.get("client_message")),
    ("Client Reply", 14, lambda r, d: r.get("client_reply") if r.get("client_reply") and r.get("reply_for") == r.get("message_at") else ""),
    ("Last Updated", 18, lambda r, d: r["_updated_local"]),
]

# group bands shown above the headers
BANDS = [
    ("CLIENT", 1, 6, PURPLE),
    ("D - DREAM HOME", 7, 11, PURPLE),
    ("R - RESOURCES", 12, 16, PURPLE),
    ("O / W - OUR TEAM", 17, 22, GOLD),
]


def build_master(rows, path, title="Intelligent House Owner - DROW Submissions"):
    wb = Workbook()
    ws = wb.active
    ws.title = "Submissions"
    ncol = len(COLUMNS)

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncol)
    c = ws.cell(1, 1, title)
    c.font = Font(name=FONT, bold=True, size=14, color=WHITE)
    c.fill = fill(PURPLE)
    c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[1].height = 30

    for label, a, b, col in BANDS:
        ws.merge_cells(start_row=2, start_column=a, end_row=2, end_column=b)
        cell = ws.cell(2, a, label)
        cell.font = Font(name=FONT, bold=True, size=9, color=WHITE)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        for k in range(a, b + 1):
            ws.cell(2, k).fill = fill(col)
    ws.row_dimensions[2].height = 18

    for i, (h, w, _) in enumerate(COLUMNS, start=1):
        cell = ws.cell(3, i, h)
        cell.font = Font(name=FONT, bold=True, size=10, color=PURPLE)
        cell.fill = fill(LAVENDER_2)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[3].height = 32

    for rix, row in enumerate(rows, start=4):
        d = row["data"]
        for cix, (h, _, get) in enumerate(COLUMNS, start=1):
            v = get(row, d)
            if v is None:
                v = ""
            cell = ws.cell(rix, cix, v)
            cell.font = Font(name=FONT, size=10, color=INK)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = BORDER
            if rix % 2 == 1:
                cell.fill = fill("FBF9FE")
            if h == "Estimated Total Budget" and isinstance(v, (int, float)):
                cell.number_format = "#,##0"

    last = max(3, 3 + len(rows))
    ws.auto_filter.ref = f"A3:{get_column_letter(ncol)}{last}"
    ws.freeze_panes = "E4"
    ws.sheet_view.zoomScale = 90

    # small status summary sheet
    s = wb.create_sheet("Summary")
    s.column_dimensions["A"].width = 26
    s.column_dimensions["B"].width = 12
    s["A1"] = "DROW Summary"
    s["A1"].font = Font(name=FONT, bold=True, size=14, color=PURPLE)
    s["A2"] = f"Generated {datetime.now().strftime('%d %b %Y, %I:%M %p')}"
    s["A2"].font = Font(name=FONT, size=9, color="7C748E")
    s["A4"], s["B4"] = "Status", "Clients"
    for k in ("A4", "B4"):
        s[k].font = Font(name=FONT, bold=True, color=WHITE)
        s[k].fill = fill(PURPLE)
    from .choices import STATUSES

    for i, st in enumerate(STATUSES, start=5):
        s.cell(i, 1, st).font = Font(name=FONT)
        s.cell(i, 2, f'=COUNTIF(Submissions!C:C,"{st}")').font = Font(name=FONT)
    t = 5 + len(STATUSES)
    s.cell(t, 1, "Total").font = Font(name=FONT, bold=True)
    s.cell(t, 2, f"=SUM(B5:B{t-1})").font = Font(name=FONT, bold=True)

    with file_lock(path):
        atomic_save(wb, path)


# --------------------------------------------------------------------------
# Per-client DROW sheet (same layout as the paper form)
# --------------------------------------------------------------------------
def build_client(row, path):
    d = row["data"]
    wb = Workbook()
    ws = wb.active
    ws.title = "DROW"
    ws.column_dimensions["A"].width = 46
    ws.column_dimensions["B"].width = 46
    ws.sheet_view.showGridLines = False
    r = 1

    def band(text, color=PURPLE, size=12, height=26):
        nonlocal r
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
        c = ws.cell(r, 1, text)
        c.font = Font(name=FONT, bold=True, size=size, color=WHITE)
        c.fill = fill(color)
        c.alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(r, 2).fill = fill(color)
        ws.row_dimensions[r].height = height
        r += 1

    def sub(text):
        nonlocal r
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
        c = ws.cell(r, 1, text)
        c.font = Font(name=FONT, bold=True, size=10, color=PURPLE)
        c.fill = fill(LAVENDER_2)
        c.alignment = Alignment(horizontal="center", vertical="center")
        ws.cell(r, 2).fill = fill(LAVENDER_2)
        ws.row_dimensions[r].height = 20
        r += 1

    def kv(k, v):
        nonlocal r
        a = ws.cell(r, 1, k)
        a.font = Font(name=FONT, bold=True, size=10, color=INK)
        a.fill = fill(LAVENDER)
        b = ws.cell(r, 2, "" if v is None else v)
        b.font = Font(name=FONT, size=10, color=INK)
        for c in (a, b):
            c.border = BORDER
            c.alignment = Alignment(vertical="center", wrap_text=True, indent=1)
        lines = max(1, len(str(v or "")) // 48 + str(v or "").count("\n") + 1)
        ws.row_dimensions[r].height = max(20, 15 * lines)
        r += 1

    def block(text):
        nonlocal r
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
        c = ws.cell(r, 1, text or "")
        c.font = Font(name=FONT, size=10, color=INK)
        c.alignment = Alignment(vertical="top", wrap_text=True, indent=1)
        for k in (1, 2):
            ws.cell(r, k).border = BORDER
        lines = max(3, len(text or "") // 95 + (text or "").count("\n") + 1)
        ws.row_dimensions[r].height = 15 * lines
        r += 1

    def gap():
        nonlocal r
        ws.row_dimensions[r].height = 8
        r += 1

    band("DROW", size=18, height=34)
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
    c = ws.cell(r, 1, "D: DREAM HOME  |  R: RESOURCES  |  O: OPTIONS  |  W: WAY FORWARD")
    c.font = Font(name=FONT, size=9, color=WHITE)
    c.fill = fill(PURPLE)
    ws.cell(r, 2).fill = fill(PURPLE)
    c.alignment = Alignment(horizontal="center")
    r += 1
    gap()

    kv("Ref No.", row["ref"])
    kv("Client Name", d.get("client_name"))
    kv("Phone / WhatsApp", d.get("phone"))
    kv("Project Location", d.get("project_location"))
    kv("Date", row["_created_local"])
    gap()

    band("D - DREAM HOME")
    sub("1. AMENITIES")
    hdr_a = ws.cell(r, 1, "Inside")
    hdr_b = ws.cell(r, 2, "Outer")
    for c in (hdr_a, hdr_b):
        c.font = Font(name=FONT, bold=True, size=10, color=PURPLE)
        c.fill = fill(LAVENDER_2)
        c.alignment = Alignment(horizontal="center")
        c.border = BORDER
    r += 1
    ins, out = d.get("inside_amenities") or [], d.get("outer_amenities") or []
    for i in range(max(len(ins), len(out), 8)):
        for col, lst in ((1, ins), (2, out)):
            c = ws.cell(r, col, lst[i] if i < len(lst) else "")
            c.font = Font(name=FONT, size=10, color=INK)
            c.border = BORDER
            c.alignment = Alignment(indent=1, vertical="center")
        ws.row_dimensions[r].height = 19
        r += 1
    sub("2. DESIGNS")
    kv("Preferred Architectural Style", d.get("arch_style"))
    kv("Design References & Notes", "")
    block(d.get("design_notes"))
    if d.get("reference_files"):
        kv("Reference Files (on server)", "\n".join(d["reference_files"]))
    gap()

    band("R - RESOURCES")
    sub("1. LAND SPECIFICATIONS")
    area = d.get("plot_area")
    kv("Plot Area (Cent / Sq.ft)", f"{area} {d.get('plot_unit') or ''}".strip() if area else "")
    kv("Plot Details & Site Conditions", "")
    block(d.get("site_conditions"))
    sub("2. BUDGET")
    amt = d.get("budget_amount")
    kv("Estimated Total Budget",
       f"{d.get('budget_currency') or ''} {amt:,.0f}".strip() if isinstance(amt, (int, float)) else "")
    gap()

    band("O - OPTIONS")
    block(row.get("options"))
    gap()
    band("W - WAY FORWARD")
    block(row.get("way_forward"))
    gap()
    kv("Status", row.get("status"))
    if row.get("team_notes"):
        kv("Team Notes", row.get("team_notes"))
    if row.get("client_message"):
        kv("Message to Client", "")
        block(row.get("client_message"))
        if row.get("client_reply") and row.get("reply_for") == row.get("message_at"):
            kv("Client Reply", row.get("client_reply"))
    gap()
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
    c = ws.cell(r, 1, "DROW Discovery Framework  -  Intelligent House Owner  -  An AYOK & AYOK Initiative  -  Confidential")
    c.font = Font(name=FONT, italic=True, size=8, color="7C748E")
    c.alignment = Alignment(horizontal="center")

    ws.print_options.horizontalCentered = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True

    with file_lock(path):
        atomic_save(wb, path)
