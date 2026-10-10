#!/bin/sh
set -e

python manage.py migrate --noinput

case "${DJANGO_CREATE_SUPERUSER:-false}" in
  1|true|True|yes|Yes)
    python manage.py ensure_initial_superuser
    ;;
esac

exec "$@"
