@echo off
REM Windows: double-click to run. First run installs packages.
cd /d "%~dp0"
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
if not exist .env (copy .env.example .env & echo Created .env - set ADMIN_PASSWORD and SECRET_KEY in it.)
python app.py
pause
