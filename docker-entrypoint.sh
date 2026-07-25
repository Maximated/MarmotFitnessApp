#!/bin/sh
set -e

uv run alembic upgrade head
uv run python -m scripts.auto_import_exercises

exec "$@"
