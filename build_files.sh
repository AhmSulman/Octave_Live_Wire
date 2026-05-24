#!/usr/bin/env bash
# Runs during Vercel build to collect Django static files.
set -e
pip install -r requirements.txt
python3 manage.py collectstatic --noinput
