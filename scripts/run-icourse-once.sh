#!/bin/sh
set -eu
umask 077
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_dir"
# Shares the same DB and lock as the scheduled container. Mail disabled for manual runs.
exec docker compose --project-directory "$project_dir" -f "$project_dir/compose.yaml" run --rm -T --no-deps \
    -e RUN_MODE=once -e SMTP_EMAIL= -e SMTP_PASSWORD= icourse
