#!/usr/bin/env bash
# Pull the latest commit onto the droplet. Run from your Mac after `git push`.
#
#   DROPLET=root@203.0.113.10 ./deploy/deploy.sh
#
# First-time setup on the droplet is in README.md.
set -euo pipefail

: "${DROPLET:?Set DROPLET=user@droplet-ip}"
APP_DIR="${APP_DIR:-/var/www/distractapp}"

ssh "$DROPLET" "cd '$APP_DIR' && git pull --ff-only && git log -1 --oneline"
echo "Deployed. Nginx serves files straight from $APP_DIR/public, so no reload is needed."
