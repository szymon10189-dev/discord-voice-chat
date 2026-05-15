#!/usr/bin/env bash
# Render.com (i podobne): instalacja zależności, statyczne pliki, migracje.
set -o errexit
set -o pipefail

cd "$(dirname "$0")"

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate --no-input
