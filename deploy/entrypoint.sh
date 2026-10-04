#!/bin/sh
# Apply migrations and seed reference data, then start the production server.
set -e
export FLASK_APP=wsgi.py
flask db upgrade
flask seed
exec gunicorn -c gunicorn.conf.py wsgi:app
