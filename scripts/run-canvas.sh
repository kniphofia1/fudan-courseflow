#!/bin/sh
set -eu
umask 077
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_dir"
exec docker compose --project-directory "$project_dir" -f "$project_dir/compose.yaml" run --rm -T --no-deps canvas
