# ARCHITECTURE — EmbedIQ Cloud (OSS edition)

## Why this document

This is the single in-repo design reference for building EmbedIQ Cloud. Every task prompt grounds here. It encodes the locked design (see `pm/DECISIONS.md` D-04/D-08 and the private master-package OSS design) so a coding agent can build any component correctly without external context. It describes the **OSS edition only**; Pro scope is explicitly marked deferred and must never be built into OSS.

## What EmbedIQ Cloud is

The cloud control plane for devices running the EmbedIQ firmware framework. Devices run the open-source firmware; this platform manages them — identity, telemetry, logs, configuration, OTA — through a thin REST API and admin UI. The OSS edition is single-user, packaged as one Docker Compose stack, and fully self-hostable.

## The two-channel device model (core invariant)

Every gateway or Linux device has two independent channels:

- **Control — MQTT over TLS — always through EmbedIQ Cloud.** Low-bandwidth, bidirectional, real-time. This is what the platform manages, and it is why we always have fleet visibility.
- **Data — REST / GraphQL / RTSP — goes wherever the customer chooses** (their own storage, or optionally through us). High-throughput, device to destination.

Invariant: control always flows through the platform; the customer's bulk data never has to.

## Component stack (configure, don't build; pin exact tags — no `latest`)

| Function | Component | Version | License | Notes |
| --- | --- | --- | --- | --- |
| MQTT broker | Mosquitto | 2.0 | EPL-2.0 | TLS; mTLS + user/pass |
| Telemetry | InfluxDB | 2.7 | MIT | time-series |
| Logs | Loki | 3.x | AGPL-3.0 | label-based on device_id |
| Dashboards | Grafana | 10.x | AGPL-3.0 | provisioned via YAML |
| OTA | Hawkbit | 0.9.x | EPL-2.0 | deployment orchestration |
| Video/stream | mediamtx | 1.x | MIT | RTSP/WebRTC |
| Glue/API/UI | Python + FastAPI | 3.12 | Apache-2.0 | what we own |

Loki and Grafana are AGPL — consumed as standalone services only. Our glue stays Apache-2.0; never copy their source into our code. Footprint is roughly 1.7 GB; minimum 2 GB RAM and 2 vCPU. A `docker-compose.lite.yml` (no Hawkbit or mediamtx) targets 1 GB hosts.

## What we build — the glue (Python/FastAPI)

Device Registry, Device Shadow, MQTT Bridge, REST API gateway, OTA proxy, and Admin UI. Everything else is configuration of the components above.

## Data model — SQLite (single file `/data/embediq.db`)

Four tables:

- `devices` — id, cert_cn, password_hash, group_id, attributes (JSON), created_at.
- `device_state` — device_id, online, last_seen, ip_address, firmware_version.
- `device_shadow` — device_id, desired (JSON), reported (JSON), updated_at.
- `groups` — id, description, created_at.

Auto-registration: a device that connects with valid credentials but isn't in the registry is created with `auto_registered=true` and flagged in the UI. There is no approval gate in OSS.

## MQTT topic contract (the firmware interface — do not change without cross-team agreement)

```text
embediq/{device_id}/telemetry        device -> cloud  (sensor JSON)
embediq/{device_id}/logs             device -> cloud  (Observatory logs)
embediq/{device_id}/state/desired    cloud -> device  (retain=true)
embediq/{device_id}/state/reported   device -> cloud  (retain=true)
embediq/{device_id}/cmd              cloud -> device  (OTA/reboot/rotate_cert; NOT retained)
embediq/{device_id}/status           device -> cloud  (online/offline, firmware_version)
```

Flat two-level (`type` plus `channel`); no namespace version prefix in v0.

## Device shadow

`state/desired` and `state/reported` are retained. The cloud writes desired with delta PATCH semantics (only changed keys); the broker delivers the retained desired to a device the moment it reconnects, so configuration survives offline gaps with no custom protocol. The device applies and publishes reported; the bridge updates SQLite.

## MQTT bridge (consumer-only — never in the device-to-broker hot path)

A single Python `paho-mqtt` consumer. If it crashes, MQTT still works. Routing:

- `telemetry` to InfluxDB.
- `logs` to Loki.
- `state/reported` to `device_shadow` (SQLite).
- `status` to `device_state` (SQLite).
- `cmd` and `state/desired` are ignored (cloud-to-device direction).

Each device sets a last-will on `status`, so an unclean disconnect marks it offline.

## REST API contract (`/api/v1`)

Standard REST, JSON everywhere, predictable enough to drive from the OpenAPI spec alone (it is the future MCP contract). Auth: `POST /auth/login` returns a JWT (24 h); other calls use `Authorization: Bearer`. Envelope: `{"data": ..., "error": null}` on success, `{"data": null, "error": {"code", "message"}}` on failure. Standard HTTP codes only (200, 201, 400, 401, 404, 409, 500). Endpoint groups: `devices`, `devices/{id}/shadow`, `devices/{id}/cmd`, `groups` (plus bulk shadow and cmd), `ota` (firmware upload, deploy, status), and `system` (health, certs). Internal: `POST /internal/auth`, called by the Mosquitto auth plugin and not public. No pagination in v0.

## OTA

We do not implement OTA logic — Hawkbit owns artifact storage, orchestration, and status. We write a thin REST proxy (`/api/v1/ota/*` to Hawkbit) and an MQTT relay: a Hawkbit deployment event publishes to `embediq/{id}/cmd` (not retained); `fb_ota` on the device downloads, verifies, applies, and reports back on `status`. No phased rollout in OSS.

## Security

Device auth supports both mTLS (production) and username/password (development); the admin chooses at registration. Production compose is TLS-only. Certificate lifecycle uses EST (RFC 7030): the device (firmware `fb_provisioning` Phase C) holds its cert, warns before expiry, and performs an atomic rotation on request; the OSS cloud tracks expiry and can trigger rotation. Secrets live in `.env`, never committed; passwords are bcrypt-hashed; secrets are never logged. Rule: AI may detect, deterministic rules execute — AI never manages keys directly (that monitoring is Pro-tier).

## Architectural boundaries and invariants

- The MQTT bridge is consumer-only; devices talk to Mosquitto directly.
- Our glue is Apache-2.0; never copy AGPL (Loki/Grafana) source into it — consume them as services.
- `pro/` proprietary code never mixes into the OSS tree; the OSS edition must run standalone.
- Flat two-level MQTT topics; server-rendered UI (FastAPI + Jinja2 + Bootstrap 5, no JS framework); one Docker Compose, no Kubernetes.

## Locked decisions

Python 3.12 + FastAPI; SQLite (OSS); Docker Compose, no Kubernetes; the MQTT topic contract above; single-user JWT; mTLS plus username/password. See `pm/DECISIONS.md` (D-04, D-08, D-12) and the master-package pre-decisions. Do not re-litigate without a design session with Ritesh.

## Known limitations (OSS) and what is deferred to Pro

OSS limits, acceptable at self-hosted scale: SQLite write-lock under heavy concurrency; single-threaded paho bridge; no REST pagination; last-write-wins shadow (no versioning); Hawkbit RAM footprint.

Deferred to Pro — do not build in OSS: the MCP server, the AI fleet agent, multi-tenancy, external connectors (AWS/Azure/Kafka and similar), the Studio-to-Cloud relay, advanced/canary OTA, the marketplace, and PostgreSQL or async-worker scaling.

## Firmware dependencies

The cloud OSS stack (infra, glue, UI) builds in parallel with firmware. Real-device integration depends on Item 6 `fb_cloud_mqtt` (MQTT connect — the integration test waits on this), Item 8 `fb_provisioning` (cert injection), Item 10 `fb_ota`, and Item 7 `embediq` CLI (5-minute setup). Cross-team questions go through the private `CLOUD_COLLAB/` maildir.

## Caveats

This document is the OSS architecture; full rationale and the Pro design live privately in the master package. On conflict: this document wins for architecture, `pm/DECISIONS.md` wins for the rationale, and a higher-tier ratified change supersedes both.
