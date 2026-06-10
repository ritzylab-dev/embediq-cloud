# EmbedIQ Cloud

EmbedIQ Cloud is the open-source, self-hostable control plane for connected devices. It gives
you a device registry, an MQTT control channel, a device shadow, OTA updates, and a branded
admin panel — packaged as one Docker Compose stack you run on your own host. It is part of the
EmbedIQ suite: the open firmware framework, the Studio debugger, and this Cloud control plane.

*The open-source, AI-agent-ready control plane that takes a device from unboxing to
cloud-connected fleet in minutes.* The "minutes" setup is a design target, not a measured
benchmark.

## What you get

Everything here is in this repository and runs today:

- A branded **admin panel** — an Overview dashboard plus Fleet, Device detail, OTA, and
  Settings pages; light and dark themes; mobile layouts. It runs with **no Docker** for a quick
  look (see Quickstart).
- A device **registry** with single-admin authentication (JWT; bcrypt-hashed password).
- An **MQTT bridge** (consumer-only) that routes telemetry to InfluxDB, logs to Loki, and
  shadow/status to SQLite.
- A **device shadow** — desired and reported state with delta semantics, retained so config
  survives offline gaps.
- **OTA** updates proxied to Eclipse hawkBit, with a command relay to devices.
- A **production security profile** — a TLS/mTLS-only broker, device authentication, and
  secret-guarded internal endpoints.

## Quickstart

Preview the admin panel without Docker (SQLite, no broker — the fastest look):

```sh
bash scripts/dev.sh
```

Then open <http://localhost:8080> and sign in with **admin / admin** (throwaway credentials,
regenerated each run). The telemetry-backed widgets show their empty state because no metrics
stack is running; the registry-backed widgets are fully live.

Run the full stack with Docker:

```sh
bash install.sh          # generate certificates and a .env with secrets
docker compose up -d --build
curl http://localhost:8080/health
```

For production (TLS-only broker, required secrets, reverse-proxy guidance) see
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Why EmbedIQ Cloud

- **Data sovereignty.** Devices have two independent channels: a low-bandwidth **control**
  channel (MQTT over TLS) through this platform, and a high-throughput **data** channel
  (REST / RTSP / your choice) that goes straight to your own storage. Control flows through the
  platform; your bulk data never has to. See [ARCHITECTURE.md](ARCHITECTURE.md).
- **AI-agent-ready.** The REST API is a clean, predictable `/api/v1` surface with an OpenAPI
  spec at `/docs` — the contract a higher-tier agent layer can drive. The agent layer itself is
  not part of this open-source edition.
- **Open foundation.** Apache-2.0, self-hostable, no managed-service lock-in.

## Component stack

Configured and pinned to exact image tags (no floating tags); the glue is the only code we own:

| Function | Component | Pinned image |
| --- | --- | --- |
| MQTT broker | Mosquitto (+ go-auth plugin) | `iegomez/mosquitto-go-auth:3.0.0-mosquitto_2.0.18` |
| Telemetry | InfluxDB | `influxdb:2.7.12` |
| Logs | Loki | `grafana/loki:3.7.2` |
| Dashboards | Grafana | `grafana/grafana:10.4.19` |
| OTA | hawkBit | `hawkbit/hawkbit-update-server:0.9.0` |
| Video / stream | MediaMTX | `bluenviron/mediamtx:1.19.0` |
| Glue / API / UI | Python 3.12 + FastAPI | built from this repo |

The full stack needs roughly 2 GB RAM and 2 vCPU. A lighter profile
(`docker-compose.lite.yml`, without hawkBit and MediaMTX) targets ~1 GB hosts. Loki and Grafana
are AGPL-3.0 and are consumed as standalone services only; the EmbedIQ glue stays Apache-2.0.

## Documentation

- [docs/README.md](docs/README.md) — the documentation index.
- [ARCHITECTURE.md](ARCHITECTURE.md) — the design and contracts.
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — development vs production.
- [SECURITY.md](SECURITY.md) — the security posture and how to report a vulnerability.
- [CONTRIBUTING.md](CONTRIBUTING.md) — local setup, gates, and the contribution flow.

## License

Apache-2.0. See [LICENSE](LICENSE).
