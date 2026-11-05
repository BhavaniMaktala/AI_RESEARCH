@echo off
REM One-command start (Windows)
cd /d "%~dp0backend"
if not exist .venv (
  python -m venv .venv
  .venv\Scripts\python -m pip install --quiet --upgrade pip
  .venv\Scripts\pip install --quiet -r requirements.txt
)
.venv\Scripts\python app.py
