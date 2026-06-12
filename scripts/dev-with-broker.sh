#!/usr/bin/env bash
# scripts/dev-with-broker.sh — run the FULL EmbedIQ Cloud stack locally WITHOUT Docker.
#
# Starts Mosquitto (MQTT broker) + the Python API with the MQTT bridge active.
# Use this when you need real device connectivity (EmbedIQ firmware ↔ EmbedIQ Cloud).
#
# WHEN TO USE EACH SCRIPT:
#   scripts/dev.sh              — UI-only preview (no MQTT broker, no device)
#   scripts/dev-with-broker.sh  — full stack without Docker (broker + API + bridge)
#   docker compose up           — full production-equivalent stack
#
# SECURITY NOTE — DEV MODE ONLY:
#   This script starts Mosquitto with allow_anonymous=true.
#   This is intentional for local development. Never use this configuration
#   in production. Production broker auth is configured in docker-compose.yml
#   (go-auth plugin, TLS, credentials required).
#
# Prerequisites: mosquitto  python3  openssl  nc (netcat)
#   macOS:  brew install mosquitto
#   Ubuntu: sudo apt install mosquitto mosquitto-clients netcat-openbsd
#
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MQTT_PORT="${MQTT_PORT:-1883}"
API_PORT="${API_PORT:-8080}"
MOSQUITTO_CONF="/tmp/embediq-dev-mosquitto.conf"
MOSQUITTO_PID=""

# --- helpers ---

log()   { printf "  %s\n" "$*"; }
fatal() { printf "ERROR: %s\n" "$*" >&2; exit 1; }

cleanup() {
    log "Stopping services..."
    # Best-effort stop: kill the broker only if we started one, and never let cleanup fail.
    # shellcheck disable=SC2015  # the `&& … || true` is intentional, not if-then-else
    [ -n "$MOSQUITTO_PID" ] && kill "$MOSQUITTO_PID" 2>/dev/null || true
    log "Done."
}
trap cleanup EXIT INT TERM

check_cmd() {
    command -v "$1" >/dev/null 2>&1 || fatal \
        "'$1' not found. Install: macOS: brew install $2  |  Ubuntu: sudo apt install $3"
}

# --- pre-checks ---

log "→ Checking prerequisites..."
check_cmd mosquitto  mosquitto            "mosquitto mosquitto-clients"
check_cmd python3    python3              python3
check_cmd openssl    openssl              openssl
check_cmd nc         netcat               netcat-openbsd
log "  prerequisites OK"

# --- start Mosquitto ---

log "→ Writing Mosquitto dev config (anonymous, port ${MQTT_PORT})..."
# DEV ONLY — allow_anonymous true. Not for production.
printf 'listener %s\nallow_anonymous true\nlog_type error\nlog_type warning\n' \
    "$MQTT_PORT" > "$MOSQUITTO_CONF"

log "→ Starting Mosquitto..."
mosquitto -c "$MOSQUITTO_CONF" &
MOSQUITTO_PID=$!    # capture the background PID via $! (not a process lookup, not daemon mode)

i=0
while ! nc -z localhost "$MQTT_PORT" 2>/dev/null; do
    i=$((i + 1))
    [ "$i" -ge 10 ] && fatal "Mosquitto did not start on port ${MQTT_PORT} after 10 s"
    sleep 1
done
log "  Mosquitto is up on port ${MQTT_PORT} (PID ${MOSQUITTO_PID})"

# --- start Python API ---

cd "$REPO_ROOT"

if [ ! -d .venv ]; then
    log "→ Creating .venv..."
    python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

log "→ Installing (editable, with dev extras)..."
pip install --quiet -e ".[dev]"

# Throwaway dev credentials — generated each run, never committed (R-8).
export ADMIN_USER="admin"
ADMIN_PASS_HASH="$(python3 -c 'import bcrypt; print(bcrypt.hashpw(b"admin", bcrypt.gensalt()).decode())')"
export ADMIN_PASS_HASH
JWT_SECRET="$(openssl rand -hex 32)"
export JWT_SECRET
# dev-broker.db is separate from dev.sh's dev.db — both scripts can coexist.
export DB_PATH="./dev-broker.db"

# MQTT bridge — active, pointing at the local anonymous broker started above.
export BRIDGE_ENABLED="true"
export MQTT_HOST="localhost"
export MQTT_PORT="$MQTT_PORT"
export MQTT_USERNAME=""   # anonymous — matches allow_anonymous=true above
export MQTT_PASSWORD=""   # anonymous

printf '\n'
printf '  %-44s\n' "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
printf '  %-44s\n' "  EmbedIQ Cloud — dev with broker"
printf '  %-44s\n' ""
printf '    Admin UI:    http://localhost:%s\n' "$API_PORT"
printf '    MQTT broker: localhost:%s  (anonymous, dev only)\n' "$MQTT_PORT"
printf '    Login:       admin / admin\n'
printf '    Ctrl+C to stop both services.\n'
printf '  %-44s\n' "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
printf '\n'

# Run uvicorn — NOT exec, so the cleanup trap still fires on exit.
uvicorn app.main:app --reload --port "$API_PORT"
