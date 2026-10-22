# Deployment

StreamOS runs as a single Python service plus a static web client. Target: a
box on the household LAN (mini-PC, NAS, Raspberry Pi 4/5, or a container).

## Requirements
- Python 3.11+ (developed on 3.13)
- FFmpeg + ffprobe on PATH (only for generating test content / future
  transcode; not needed to relay)
- ~100 MB RAM for the service; disk for the SQLite DB and warm segment cache

## Run from source
```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r hub/requirements.txt
cd hub
STREAMOS_DATA=/var/lib/streamos \
STREAMOS_MAX_UPSTREAM=2 \
python -m uvicorn streamos.main:app --host 0.0.0.0 --port 8099
```
Open `http://<hub-ip>:8099` from any device on the LAN.

## Configuration (environment variables)
| Var | Default | Meaning |
|---|---|---|
| `STREAMOS_DATA` | `./scratch/hubdata` | state dir (SQLite + cache) |
| `STREAMOS_MAX_UPSTREAM` | `2` | global cap on simultaneous upstream sessions — **set to what your source actually permits** |
| `STREAMOS_SEGMENT_TTL` | `30` | seconds a fetched segment stays warm |
| `STREAMOS_PLAYLIST_TTL` | `1` | live manifest cache window |
| `STREAMOS_SESSION_IDLE` | `20` | idle seconds before a viewer/upstream is reaped |
| `STREAMOS_UPSTREAM_TIMEOUT` | `10` | upstream fetch timeout |

## Docker
```dockerfile
FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY hub/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY hub/ ./hub/
ENV STREAMOS_DATA=/data
VOLUME /data
EXPOSE 8099
CMD ["python","-m","uvicorn","streamos.main:app","--app-dir","hub","--host","0.0.0.0","--port","8099"]
```
```bash
docker build -t streamos .
docker run -d --name streamos -p 8099:8099 -v streamos-data:/data streamos
```
A `docker-compose.yml` that also runs the test origin for a self-contained
demo is in the repo root (`docker compose up --build`).

> Verification note: `docker compose config` validates the compose file here,
> but no image was built in the development environment (no Docker daemon was
> available — CLI only). The `Dockerfile`/compose are provided as-is; build
> them on a host with Docker running.

## First-run setup
1. Open the client → **Streaming Sources** → add a source. During development
   point it at the test origin
   (`python testkit/origin.py --content ./scratch/origin --port 8100`,
   URL `http://<ip>:8100/ch1/index.m3u8`).
2. Set each source's **Max sessions** and **Shareable** to match what the
   source permits.
3. Pair devices under **Connected Devices** (code shown on the hub).

## Running as a service (systemd)
```ini
[Unit]
Description=StreamOS hub
After=network-online.target

[Service]
Environment=STREAMOS_DATA=/var/lib/streamos
Environment=STREAMOS_MAX_UPSTREAM=2
ExecStart=/opt/streamos/.venv/bin/python -m uvicorn streamos.main:app \
  --app-dir /opt/streamos/hub --host 0.0.0.0 --port 8099
Restart=on-failure
User=streamos

[Install]
WantedBy=multi-user.target
```

## Before exposing beyond the LAN — don't, yet
The control API is unauthenticated and the transport is plain HTTP (see
`KNOWN_LIMITATIONS.md`). Keep the hub on the LAN. For remote viewing, use a
VPN back into the home network rather than port-forwarding. Internet exposure
requires the auth + TLS work listed as open.

## Backup / recovery
State is one SQLite file under `STREAMOS_DATA`. Back it up by copying
`streamos.db*`. The segment cache is disposable and rebuilds on demand.

## Health & diagnostics
- `GET /api/health` — liveness.
- `GET /api/metrics` — upstream sessions, cache hit ratio, bytes, TTFS, host
  CPU/RAM. The **Diagnostics** screen renders this live.
