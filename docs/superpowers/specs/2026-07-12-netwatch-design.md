# netwatch — Internet Connection Quality Watchdog

## Purpose

Continuously monitor internet connection quality (latency, packet loss, and per-hop
delay) over a 4-week period to determine whether the ISP connection is slow/low
quality, and produce charts from the collected data on demand.

## Environment assumptions

- macOS (Darwin), machine stays powered on and awake for the full monitoring period.
- Python 3.9+, plus `matplotlib` (only non-stdlib dependency).
- Uses the system `ping` and `traceroute` binaries via `subprocess` (BSD variants,
  as shipped with macOS).

## Architecture

Two independent scripts sharing one SQLite database, all living in `~/netwatch/`:

- `netwatch.py` — the watchdog. Runs in the foreground indefinitely (started once,
  e.g. in a terminal/tmux session, or via `nohup ... &`). Internally runs a single
  loop with two independent timers: one for ping sampling, one for traceroute
  sampling, so a slow traceroute never blocks ping cadence.
- `chart.py` — run on demand (e.g. `python3 chart.py --days 7`). Reads
  `netwatch.db` and writes PNG charts to `~/netwatch/charts/`.
- `netwatch.db` — SQLite database, single source of truth for both scripts.
- `netwatch.log` — plain text log of warnings/errors from the watchdog loop.

No service manager / launchd is used since the machine is assumed always-on;
the watchdog is just a long-running foreground/background process.

## Targets

Three targets, checked every cycle:

1. Default gateway — resolved once at startup via `route -n get default`
   (parse the `gateway:` line).
2. `1.1.1.1` (Cloudflare)
3. `8.8.8.8` (Google)

Targets are a hardcoded list/constant near the top of `netwatch.py` (gateway
substituted in at startup) so they're easy to edit later. Distinguishing
gateway vs. public-DNS latency lets the data show whether slowness is local
(Wi-Fi/router) or upstream (ISP/internet).

## Sampling

- **Ping**: every 60 seconds per target. Runs `ping -c 1 -W 2000 <host>`,
  parses round-trip time in ms from the output. A non-zero exit code or
  unparsable output is recorded as a loss (not a crash).
- **Traceroute**: every 15 minutes per target. Runs
  `traceroute -q 1 -w 1 -m 20 <host>`, parses each hop line for hop number,
  IP address (or `*` for no response), and RTT in ms.

Two independent monotonic-clock timers drive these; the main loop sleeps in
short increments (e.g. 1s) and checks whether either timer has elapsed, so a
slow traceroute for one target doesn't delay ping sampling for others.

## Data model (SQLite)

```sql
CREATE TABLE ping_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,        -- unix timestamp
    target TEXT NOT NULL,
    rtt_ms REAL,             -- NULL if lost
    lost INTEGER NOT NULL    -- 0 or 1
);

CREATE TABLE traceroute_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    target TEXT NOT NULL,
    hop_num INTEGER NOT NULL,
    hop_ip TEXT,             -- NULL if timed out
    rtt_ms REAL,             -- NULL if timed out
    timed_out INTEGER NOT NULL
);
```

Indexes on `(target, ts)` for both tables to keep chart queries fast over
4 weeks of data (~40k ping rows and ~2.7k traceroute cycles per target).

## Error handling

- Each individual ping/traceroute invocation is wrapped in its own
  try/except; a failure is recorded as a loss/timeout row (or skipped with a
  logged warning if the DB write itself fails) rather than raising.
- The outer loop has a top-level try/except per iteration: any unexpected
  exception is logged to `netwatch.log` with a timestamp and traceback, and
  the loop continues on the next tick. This is what makes a 4-week
  unattended run survive transient issues (temporary DNS failure, brief
  network outage, etc.) without the process dying.
- SIGINT/SIGTERM are handled to flush and close the SQLite connection
  cleanly before exiting.

## Charting (`chart.py`)

CLI: `python3 chart.py [--days N] [--target HOST]` (default: all data, all
targets).

Produces three PNGs per run into `~/netwatch/charts/`:

1. **Latency over time** — line chart per target, samples bucketed (e.g. by
   hour) and averaged so a month of minute-by-minute noise stays readable.
2. **Packet loss % over time** — bucketed (e.g. hourly) loss rate per target.
3. **Latest traceroute hop breakdown** — bar chart of per-hop RTT for the
   most recent traceroute cycle per target, to identify which hop
   introduces delay.

Chart styling follows the project's dataviz skill guidance (palette,
accessibility, consistent look) at implementation time.

## Testing approach

Manual smoke test, no unit test framework:

1. Run `netwatch.py` for ~2 minutes (with traceroute interval temporarily
   shortened for the test) and confirm rows land in `netwatch.db` for all
   three targets, for both tables.
2. Run `chart.py` against that data and confirm three PNGs are produced and
   visually sane (real numbers, correctly labeled axes/targets).

## Out of scope (YAGNI)

- Alerting/notifications on high latency or loss.
- A live/auto-refreshing dashboard.
- Support for non-macOS platforms or non-BSD `ping`/`traceroute` flags.
- Concurrent/async probing (three sequential targets at these intervals
  don't need it).
