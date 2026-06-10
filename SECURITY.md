# Security Policy

## Why

EmbedIQ Cloud is self-hosted and often internet-facing, so its security model must hold without
depending on an operator's network setup. This page states the posture honestly and explains how
to report a problem.

## Security posture

### Administrator access

- A single administrator authenticates with a username and password. The password is stored only
  as a bcrypt hash, never in plaintext.
- Login issues a JSON Web Token (24-hour expiry). All `/api/v1` calls require that bearer token.
- The page shells are public chrome; the JSON API behind them stays behind admin authentication.

### Device authentication (production)

- The production broker is TLS/mTLS-only (`require_certificate true`); anonymous access is off,
  and the plain `1883` listener is not exposed.
- Every device is authenticated through the API: the Mosquitto go-auth plugin calls
  `/internal/auth` (password or client-certificate CN) and `/internal/acl` (topic scope).

### Internal endpoints (`/internal/*`)

- These endpoints are an allow/deny oracle, so they are guarded by a shared secret
  (`INTERNAL_API_KEY`) checked in **constant time**. The secret may arrive as the
  `X-Internal-Key` header or, for the broker, the `User-Agent` (the go-auth HTTP backend has no
  custom-header facility).
- **Fail-closed in production:** with `EMBEDIQ_PROFILE=prod` the app refuses to start if the key
  is empty.
- The device-authentication path is **rate-limited** per source, so it is not an open
  brute-force oracle.

### Secrets and exposure

- `INTERNAL_API_KEY`, the admin password hash, and all service secrets live in `.env` (generated
  by `install.sh`) and are never committed. Secrets are never logged.
- Terminate TLS at a reverse proxy in front of port `8080`; do not expose `8080` — including
  `/internal/*` — to the public internet. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Supported versions

The latest `0.1.x` release of the open-source edition receives security fixes.

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |
| < 0.1 | No |

## Reporting a vulnerability

Please report privately — do **not** open a public issue.

- Preferred: use GitHub's private vulnerability reporting ("Report a vulnerability" under the
  repository's Security tab).
- Alternatively, email `security@ritzylab.com`.

Include the affected version, reproduction steps, and impact. We aim to acknowledge a report
within a few business days and will coordinate a fix and disclosure timeline with you.
