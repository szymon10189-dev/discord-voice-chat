#!/usr/bin/env bash
# Render.com (render.yaml: buildCommand: bash build.sh)
set -o errexit
set -o pipefail

cd "$(dirname "$0")"

echo "==> Instalacja zależności Python"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "==> Walidacja projektu Django"
python manage.py check

echo "==> Pliki statyczne (CSS/JS, m.in. search, emoji, voice, reactions)"
python manage.py collectstatic --no-input

echo "==> Migracje bazy danych"
python manage.py migrate --no-input

echo "==> Katalogi na uploady (media na dysku instancji Render)"
mkdir -p media/avatars media/message_attachments media/dm_attachments

echo "==> Domyślny serwer, role, kanały (#ogólny, ogólny-głos)"
python manage.py shell -c "from core.bootstrap import bootstrap_defaults; bootstrap_defaults()"

if [ -n "${DJANGO_SUPERUSER_USERNAME:-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
  echo "==> Konto administratora (opcjonalne, ze zmiennych środowiskowych)"
  export DJANGO_SUPERUSER_EMAIL="${DJANGO_SUPERUSER_EMAIL:-admin@example.com}"
  python manage.py createsuperuser --noinput || true
fi

echo "==> Build zakończony"
