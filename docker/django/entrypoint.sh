#!/bin/sh
set -e

case "${DJANGO_COLLECTSTATIC:-true}" in
  0|false|False|no|No)
    ;;
  *)
    python manage.py collectstatic --noinput
    ;;
esac

case "${DJANGO_MIGRATE:-true}" in
  0|false|False|no|No)
    ;;
  *)
    python manage.py migrate --noinput
    ;;
esac

case "${DJANGO_CREATE_SUPERUSER:-false}" in
  1|true|True|yes|Yes)
    python manage.py ensure_initial_superuser
    ;;
esac

exec "$@"
