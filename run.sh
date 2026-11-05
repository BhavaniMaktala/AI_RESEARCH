#!/usr/bin/env bash
# One-command start (Linux / macOS)
set -e
cd "$(dirname "$0")/backend"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  ./.venv/bin/pip install --quiet --upgrade pip
  ./.venv/bin/pip install --quiet -r requirements.txt
fi
exec ./.venv/bin/python app.py
