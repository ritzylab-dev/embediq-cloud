#!/usr/bin/env bash
# scripts/gen-certs.sh — generate the CA + server certificates the MQTT broker needs (TLS/mTLS).
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
#
# Non-interactive and idempotent: writes ./certs/{ca.crt,server.crt,server.key} on first run and
# reuses them after. Shared by install.sh (first-run setup) and the CI integration job (so the
# broker can start its 8883 TLS listener — without these files Mosquitto exits and takes the
# plain 1883 listener down with it). Resolves paths from its own location, so CWD does not matter.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERTS="$ROOT/certs"

command -v openssl >/dev/null 2>&1 || { echo "ERROR: openssl is required"; exit 1; }

mkdir -p "$CERTS"
if [ ! -f "$CERTS/ca.crt" ]; then
  echo "==> Generating CA + server certificates (10-year)…"
  openssl genrsa -out "$CERTS/ca.key" 4096
  openssl req -x509 -new -nodes -key "$CERTS/ca.key" -sha256 -days 3650 \
    -subj "/CN=EmbedIQ-CA" -out "$CERTS/ca.crt"
  openssl genrsa -out "$CERTS/server.key" 4096
  openssl req -new -key "$CERTS/server.key" -subj "/CN=embediq-cloud" -out "$CERTS/server.csr"
  openssl x509 -req -in "$CERTS/server.csr" -CA "$CERTS/ca.crt" -CAkey "$CERTS/ca.key" \
    -CAcreateserial -sha256 -days 3650 -out "$CERTS/server.crt"
  rm -f "$CERTS/server.csr"
  chmod 600 "$CERTS"/*.key
else
  echo "==> Reusing existing certificates in $CERTS"
fi
