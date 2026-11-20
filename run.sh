#!/usr/bin/env bash
# Mac / Linux: first run creates a virtual environment and installs packages.
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
[ -f .env ] || { cp .env.example .env; echo "Created .env - set ADMIN_PASSWORD and SECRET_KEY in it."; }
python app.py
