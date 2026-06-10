#!/usr/bin/env bash
# scripts/dev.sh — run the admin UI locally with NO Docker (the HC-3 enabler).
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
#
# Creates/activates a .venv, installs the package, exports a throwaway dev admin
# (admin / admin) and a random JWT secret, uses a local SQLite file, skips the MQTT
# broker, and starts uvicorn with reload on :8080.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
  echo "→ creating .venv"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "→ installing (editable, with dev extras)"
pip install --quiet -e ".[dev]"

# Throwaway dev credentials — generated each run, never committed (R-8).
export ADMIN_USER="admin"
ADMIN_PASS_HASH="$(python3 -c 'import bcrypt; print(bcrypt.hashpw(b"admin", bcrypt.gensalt()).decode())')"
export ADMIN_PASS_HASH
JWT_SECRET="$(openssl rand -hex 32)"
export JWT_SECRET
export DB_PATH="./dev.db"
export BRIDGE_ENABLED="false" # no broker needed for the UI

echo
echo "  open http://localhost:8080 — log in  admin / admin"
echo
exec uvicorn app.main:app --reload --port 8080
