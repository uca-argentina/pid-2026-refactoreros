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

exec "$@"
