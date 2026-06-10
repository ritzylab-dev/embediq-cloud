# Changelog

All notable changes to EmbedIQ Cloud are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-06-09

The first open-source edition: a self-hostable, single-administrator control plane.

### Added

- **Infrastructure stack** — one Docker Compose stack (Mosquitto, InfluxDB, Loki, Grafana,
  hawkBit, MediaMTX) with pinned images, plus `install.sh` for first-run setup and a
  `docker-compose.lite.yml` profile for smaller hosts.
- **Device registry and authentication** — a device registry with single-admin login (JWT;
  bcrypt-hashed password) and the `/api/v1` REST API with an OpenAPI spec at `/docs`.
- **MQTT bridge** — a consumer-only bridge routing telemetry to InfluxDB, logs to Loki, and
  shadow/status to SQLite.
- **Device shadow** — desired and reported state with delta semantics, delivered retained so
  configuration survives offline gaps.
- **OTA** — a thin proxy to Eclipse hawkBit plus an MQTT command relay to devices.
- **Admin panel** — a hand-authored, framework-free design system: an Overview dashboard plus
  Fleet, Device detail, OTA, and Settings pages; light and dark themes; mobile layouts; a
  no-Docker preview via `scripts/dev.sh`.
- **Security baseline** — a production TLS/mTLS-only broker profile, device authentication via
  the go-auth plugin against `/internal/*`, a constant-time shared secret on the internal
  endpoints (fail-closed in production), rate-limited device authentication, and CA-expiry
  tracking with a manual rotation trigger.
- **End-to-end test harness** — a simulated-device integration suite exercising registry,
  bridge, shadow, and OTA against the live stack, run in CI.

[0.1.0]: https://github.com/ritzylab-dev/embediq-cloud/releases/tag/v0.1.0
