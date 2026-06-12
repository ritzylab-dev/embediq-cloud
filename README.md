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

`scripts/dev.sh` runs the **UI and API only** (SQLite, broker disabled). You can explore the
admin panel and the REST API, but the device → MQTT → telemetry flow needs the full
`docker compose up` stack below — there is no MQTT broker in no-Docker mode, so a device cannot
connect.

### Local development with device connectivity

To test a real EmbedIQ device against the cloud **without Docker**, use the broker-enabled dev
mode. Unlike `scripts/dev.sh` (UI + API only), this also starts a local Mosquitto broker, so a
device can connect on `localhost:1883` and appear in the admin panel.

Install the Mosquitto binary first:

```sh
brew install mosquitto                                        # macOS
sudo apt install mosquitto mosquitto-clients netcat-openbsd   # Ubuntu
```

Then start both services with one command:

```sh
bash scripts/dev-with-broker.sh
```

It runs Mosquitto on port `1883` and the Cloud API (with the MQTT bridge active) on port `8080`;
sign in with **admin / admin**. Press **Ctrl+C** to stop both services together.

> **Dev only:** this broker runs with `allow_anonymous` — no credentials, no TLS — for local
> convenience. Never use this configuration in production; production broker auth (the go-auth
> plugin, TLS) is configured in `docker-compose.yml`.

Run the full stack with Docker:

```sh
bash install.sh          # generate certificates and a .env with secrets
docker compose up -d --build
curl http://localhost:8080/health
```

For production (TLS-only broker, required secrets, reverse-proxy guidance) see
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Ports & endpoints

`docker compose up` publishes these host ports:

| Port | Service | For |
| --- | --- | --- |
| `8080` | API + admin UI | operators / clients — the UI and the REST API |
| `1883` | MQTT (plain) | devices — development |
| `8883` | MQTT (TLS / mTLS) | devices — production |
| `3000` | Grafana | dashboards |

InfluxDB, Loki, and hawkBit are **internal-only** — the app reaches them over the Docker network,
so they are not published. The streaming server (mediamtx) is optional and lives in
`docker-compose.media.yml` (`docker compose -f docker-compose.yml -f docker-compose.media.yml up`).

Two audiences, two entry points:

- **Operators / clients →** `http://<host>:8080` (admin UI) and `http://<host>:8080/api/v1/*`
  (REST API; OpenAPI at `/docs`).
- **Devices →** the MQTT broker at `<host>:1883` (plain) or `<host>:8883` (TLS). Publish to
  `embediq/{device_id}/telemetry` (and `/status`, `/logs`, `/state/reported`); subscribe to
  `embediq/{device_id}/state/desired` and `/cmd`. The full topic contract:

```text
embediq/{device_id}/telemetry        device -> cloud  (sensor JSON)
embediq/{device_id}/logs             device -> cloud  (Observatory logs)
embediq/{device_id}/state/desired    cloud -> device  (retain=true)
embediq/{device_id}/state/reported   device -> cloud  (retain=true)
embediq/{device_id}/cmd              cloud -> device  (OTA/reboot/rotate_cert; NOT retained)
embediq/{device_id}/status           device -> cloud  (online/offline, firmware_version)
```

## Connect your first device

The end-to-end path on the full Docker stack (no-Docker mode has no broker, so a device cannot
connect there).

**1. Bring up the stack.**

```sh
bash install.sh            # sets your admin password + generates secrets and certs
docker compose up -d --build
```

**2. Get an admin token** (use the admin username/password you set in `install.sh`):

```sh
TOKEN=$(curl -fsS -X POST http://localhost:8080/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<your-admin-password>"}' \
  | python3 -c 'import sys, json; print(json.load(sys.stdin)["data"]["token"])')
```

**3. Register a device:**

```sh
curl -fsS -X POST http://localhost:8080/api/v1/devices \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"id": "sensor-001", "password": "device-secret"}'
```

**4. Connect the device** and publish status + telemetry (the default stack's broker is anonymous
on `1883`; production requires TLS and per-device auth):

```sh
mosquitto_pub -h localhost -p 1883 -t 'embediq/sensor-001/status' \
  -m '{"online": true, "firmware_version": "1.0.0"}'
mosquitto_pub -h localhost -p 1883 -t 'embediq/sensor-001/telemetry' \
  -m '{"metrics": {"temp_c": 21.5}}'
```

**5. See it.** The device shows **online** on the Fleet page (<http://localhost:8080/ui/fleet>),
and its telemetry lands in InfluxDB — view it in Grafana (<http://localhost:3000>).

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
| Video / stream (optional) | MediaMTX | `bluenviron/mediamtx:1.19.0` |
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
