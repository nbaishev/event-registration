#!/bin/sh
# Shared by Make and systemd. No shell sourcing of application secrets.
set -eu
case "$#:$*" in
    0:) dry_run= ;;
    1:--dry-run) dry_run=--dry-run ;;
    *) echo 'Usage: renew.sh [--dry-run]' >&2; exit 2 ;;
esac
checkout=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$checkout"
# Lock lives in the deployment checkout and is automatically released on exit.
exec 9>infra/certbot/.renew.lock
flock -n 9 || { echo 'Certificate renewal already running' >&2; exit 1; }
prod() { docker compose --env-file .env.prod -f compose.prod.yaml "$@"; }
# An unchanged certificate also gets a harmless graceful reload.
if [ -n "$dry_run" ]; then
    prod run --rm --no-deps certbot renew --non-interactive --dry-run
else
    prod run --rm --no-deps certbot renew --non-interactive
fi
prod exec -T nginx nginx -t
prod exec -T nginx nginx -s reload
