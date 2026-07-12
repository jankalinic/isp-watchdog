# netwatch

Continuous internet connection quality watchdog for macOS and Linux
(including Raspberry Pi OS). Samples ping latency/loss every 60s, a full
traceroute every 15 min, and a download/upload speed test every 30 min, for
your default gateway plus `1.1.1.1` and `8.8.8.8`, storing results in
`netwatch.db`. Designed to run unattended for weeks on an always-on
machine. Includes a local-network web dashboard with an on-demand
"check now" button — see [Web dashboard](#web-dashboard) below.

## Setup

```bash
cd ~/netwatch
pip3 install -r requirements.txt
```

## Running the watchdog

Start it in the foreground, or backgrounded so it survives closing the
terminal:

```bash
nohup python3 netwatch.py > /dev/null 2>&1 &
echo $! > netwatch.pid
```

Check it's alive: `ps -p $(cat netwatch.pid)`

Stop it: `kill -TERM $(cat netwatch.pid)`

Logs (including any transient sample failures) go to `netwatch.log`.

## Generating charts

Run any time, even while the watchdog is still running:

```bash
python3 chart.py                # all data, all targets
python3 chart.py --days 7       # last 7 days only
python3 chart.py --target 1.1.1.1
```

Charts are written to `charts/`:
- `latency_over_time.png` — hourly-averaged round-trip time per target
- `packet_loss.png` — hourly packet loss % per target
- `speed_over_time.png` — hourly-averaged download/upload Mbps
- `traceroute_<target>.png` — per-hop latency for the most recent traceroute
  to that target (red X marks hops that didn't respond)

## Interpreting results

Compare the gateway line against the two public DNS lines: if the gateway is
fast/stable but `1.1.1.1`/`8.8.8.8` are slow or lossy, the problem is
upstream (ISP), not your local Wi-Fi/router. The traceroute charts show
exactly which hop introduces delay. The speed chart shows whether your ISP
is actually delivering the download/upload throughput you're paying for.

## Web dashboard

Instead of (or alongside) the CLI, `app.py` serves a live dashboard on the
local network:

```bash
python3 app.py
```

Open `http://<this-machine's-ip>:8000/` from any device on the same
network. The page shows all charts (auto-refreshing every 60s) and a
"Check now" button that immediately samples ping + traceroute (all 3
targets) + one speed test and updates the charts — useful for checking the
connection right now instead of waiting for the next scheduled sample.
There's no login; it's intended for a trusted home LAN only.

`app.py` and `netwatch.py` are independent processes that share the same
`netwatch.db` — run one or both depending on whether you want the
dashboard, the background collector, or both.

## Deploying on a Raspberry Pi

netwatch supports both macOS and Linux (including Raspberry Pi OS).

1. Copy this directory to the Pi, e.g. `/home/pi/netwatch`.
2. Install dependencies: `pip3 install -r requirements.txt` (includes
   `flask` and `speedtest-cli` for the dashboard and speed testing).
3. Edit `netwatch-collector.service` and `netwatch-web.service` if your
   username or install path differs from `/home/pi/netwatch`.
4. Install and start both services:

```bash
sudo cp netwatch-collector.service netwatch-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now netwatch-collector netwatch-web
```

5. Check status/logs: `systemctl status netwatch-collector`,
   `journalctl -u netwatch-web -f`.
6. From a PC on the same network, open `http://<pi-ip-address>:8000/` to
   view the dashboard. Click "Check now" to sample immediately instead of
   waiting for the next scheduled interval.

The dashboard has no login — it's intended for a trusted home LAN only.
