"""Generate connection-quality charts from netwatch.db.

Chart-building logic lives in build_*_figure() functions that return a
matplotlib Figure, so both this CLI (which saves to PNG files) and app.py
(which streams PNG bytes over HTTP) share one implementation per chart.
"""
import argparse
import datetime
import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

import db

CHARTS_DIR = Path(__file__).parent / "charts"

# Categorical palette (validated, see dataviz skill references/palette.md),
# assigned in fixed order so the same target always gets the same color.
SERIES_COLORS = ["#2a78d6", "#1baf7a", "#eda100", "#e34948"]
SURFACE = "#fcfcfb"
PRIMARY_INK = "#0b0b0b"
SECONDARY_INK = "#52514e"
MUTED_INK = "#898781"
GRIDLINE = "#e1e0d9"
CRITICAL = "#d03b3b"

BUCKET_SECONDS = 3600  # 1 hour


def connect(days):
    db.init_db().close()  # ensure schema exists even if the collector hasn't run yet
    conn = sqlite3.connect(str(db.DB_PATH))
    conn.row_factory = sqlite3.Row
    cutoff = None
    if days is not None:
        cutoff = datetime.datetime.now().timestamp() - days * 86400
    return conn, cutoff


def targets_in_db(conn, target_filter):
    if target_filter:
        return [target_filter]
    rows = conn.execute("SELECT DISTINCT target FROM ping_samples ORDER BY target").fetchall()
    return [r["target"] for r in rows]


def _style_axes(ax):
    ax.set_facecolor(SURFACE)
    ax.figure.set_facecolor(SURFACE)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(GRIDLINE)
    ax.tick_params(colors=MUTED_INK)
    ax.yaxis.grid(True, color=GRIDLINE, linewidth=1)
    ax.xaxis.grid(False)
    ax.set_axisbelow(True)


def _date_axis(ax):
    locator = mdates.AutoDateLocator()
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))


def _bucketed_latency(conn, target, cutoff):
    query = "SELECT ts, rtt_ms, lost FROM ping_samples WHERE target = ?"
    params = [target]
    if cutoff is not None:
        query += " AND ts >= ?"
        params.append(cutoff)
    rows = conn.execute(query, params).fetchall()

    buckets = {}
    for row in rows:
        bucket = int(row["ts"] // BUCKET_SECONDS) * BUCKET_SECONDS
        buckets.setdefault(bucket, {"rtts": [], "lost": 0, "total": 0})
        buckets[bucket]["total"] += 1
        if row["lost"]:
            buckets[bucket]["lost"] += 1
        else:
            buckets[bucket]["rtts"].append(row["rtt_ms"])

    ordered = sorted(buckets.items())
    times = [datetime.datetime.fromtimestamp(ts) for ts, _ in ordered]
    avg_rtt = [
        (sum(b["rtts"]) / len(b["rtts"])) if b["rtts"] else None
        for _, b in ordered
    ]
    loss_pct = [(b["lost"] / b["total"]) * 100 for _, b in ordered]
    return times, avg_rtt, loss_pct


def _bucketed_speed(conn, cutoff):
    query = "SELECT ts, download_mbps, upload_mbps FROM speed_samples"
    params = []
    if cutoff is not None:
        query += " WHERE ts >= ?"
        params.append(cutoff)
    rows = conn.execute(query, params).fetchall()

    buckets = {}
    for row in rows:
        bucket = int(row["ts"] // BUCKET_SECONDS) * BUCKET_SECONDS
        buckets.setdefault(bucket, {"down": [], "up": []})
        if row["download_mbps"] is not None:
            buckets[bucket]["down"].append(row["download_mbps"])
        if row["upload_mbps"] is not None:
            buckets[bucket]["up"].append(row["upload_mbps"])

    ordered = sorted(buckets.items())
    times = [datetime.datetime.fromtimestamp(ts) for ts, _ in ordered]
    avg_down = [
        (sum(b["down"]) / len(b["down"])) if b["down"] else None
        for _, b in ordered
    ]
    avg_up = [
        (sum(b["up"]) / len(b["up"])) if b["up"] else None
        for _, b in ordered
    ]
    return times, avg_down, avg_up


def build_latency_figure(conn, targets, cutoff):
    fig, ax = plt.subplots(figsize=(10, 5))
    _style_axes(ax)
    for i, target in enumerate(targets):
        times, avg_rtt, _ = _bucketed_latency(conn, target, cutoff)
        color = SERIES_COLORS[i % len(SERIES_COLORS)]
        ax.plot(times, avg_rtt, color=color, linewidth=2, marker="o", markersize=4, label=target)
        valid = [(t, v) for t, v in zip(times, avg_rtt) if v is not None]
        if valid:
            lt, lv = valid[-1]
            ax.annotate(target, (lt, lv), textcoords="offset points",
                        xytext=(6, 10 - i * 14), color=SECONDARY_INK, fontsize=9, va="center")
    ax.set_title("Latency over time (hourly average)", color=PRIMARY_INK)
    ax.set_ylabel("Round-trip time (ms)", color=SECONDARY_INK)
    _date_axis(ax)
    fig.autofmt_xdate()
    ax.legend(frameon=False, labelcolor=SECONDARY_INK)
    fig.tight_layout()
    return fig


def build_loss_figure(conn, targets, cutoff):
    fig, ax = plt.subplots(figsize=(10, 5))
    _style_axes(ax)
    for i, target in enumerate(targets):
        times, _, loss_pct = _bucketed_latency(conn, target, cutoff)
        color = SERIES_COLORS[i % len(SERIES_COLORS)]
        ax.plot(times, loss_pct, color=color, linewidth=2, marker="o", markersize=4, label=target)
        if times:
            ax.annotate(target, (times[-1], loss_pct[-1]), textcoords="offset points",
                        xytext=(6, 10 - i * 14), color=SECONDARY_INK, fontsize=9, va="center")
    ax.set_title("Packet loss over time (hourly)", color=PRIMARY_INK)
    ax.set_ylabel("Packet loss (%)", color=SECONDARY_INK)
    ax.set_ylim(bottom=0)
    _date_axis(ax)
    fig.autofmt_xdate()
    ax.legend(frameon=False, labelcolor=SECONDARY_INK)
    fig.tight_layout()
    return fig


def build_speed_figure(conn, cutoff):
    fig, ax = plt.subplots(figsize=(10, 5))
    _style_axes(ax)
    times, avg_down, avg_up = _bucketed_speed(conn, cutoff)
    ax.plot(times, avg_down, color=SERIES_COLORS[0], linewidth=2, marker="o", markersize=4, label="download")
    ax.plot(times, avg_up, color=SERIES_COLORS[1], linewidth=2, marker="o", markersize=4, label="upload")
    ax.set_title("Speed test results over time (hourly average)", color=PRIMARY_INK)
    ax.set_ylabel("Mbps", color=SECONDARY_INK)
    ax.set_ylim(bottom=0)
    _date_axis(ax)
    fig.autofmt_xdate()
    ax.legend(frameon=False, labelcolor=SECONDARY_INK)
    fig.tight_layout()
    return fig


def build_traceroute_figure(conn, target, cutoff, color):
    query = "SELECT ts, hop_num, rtt_ms, timed_out FROM traceroute_samples WHERE target = ?"
    params = [target]
    if cutoff is not None:
        query += " AND ts >= ?"
        params.append(cutoff)
    rows = conn.execute(query, params).fetchall()
    if not rows:
        return None
    latest_ts = max(r["ts"] for r in rows)
    latest_hops = sorted(
        (r for r in rows if r["ts"] == latest_ts), key=lambda r: r["hop_num"]
    )

    fig, ax = plt.subplots(figsize=(10, 5))
    _style_axes(ax)
    hop_nums = [r["hop_num"] for r in latest_hops]
    responded_x = [r["hop_num"] for r in latest_hops if not r["timed_out"]]
    responded_y = [r["rtt_ms"] for r in latest_hops if not r["timed_out"]]
    timed_out_x = [r["hop_num"] for r in latest_hops if r["timed_out"]]

    ax.bar(responded_x, responded_y, color=color, width=0.6)
    if timed_out_x:
        ax.scatter(timed_out_x, [0] * len(timed_out_x), color=CRITICAL, marker="x",
                   s=60, zorder=3, label="no response")
        ax.legend(frameon=False, labelcolor=SECONDARY_INK)
    ax.set_title(f"Latest traceroute to {target}", color=PRIMARY_INK)
    ax.set_xlabel("Hop", color=SECONDARY_INK)
    ax.set_ylabel("Round-trip time (ms)", color=SECONDARY_INK)
    ax.set_xticks(hop_nums)
    fig.tight_layout()
    return fig


def main():
    parser = argparse.ArgumentParser(description="Chart netwatch connection quality data")
    parser.add_argument("--days", type=float, default=None,
                         help="only include samples from the last N days")
    parser.add_argument("--target", type=str, default=None,
                         help="only chart this target (default: all)")
    args = parser.parse_args()

    CHARTS_DIR.mkdir(exist_ok=True)
    conn, cutoff = connect(args.days)
    targets = targets_in_db(conn, args.target)
    if not targets:
        print("no data found in", db.DB_PATH)
        return

    latency_fig = build_latency_figure(conn, targets, cutoff)
    latency_path = CHARTS_DIR / "latency_over_time.png"
    latency_fig.savefig(latency_path, dpi=150, facecolor=SURFACE)
    plt.close(latency_fig)
    print(f"wrote {latency_path}")

    loss_fig = build_loss_figure(conn, targets, cutoff)
    loss_path = CHARTS_DIR / "packet_loss.png"
    loss_fig.savefig(loss_path, dpi=150, facecolor=SURFACE)
    plt.close(loss_fig)
    print(f"wrote {loss_path}")

    speed_fig = build_speed_figure(conn, cutoff)
    speed_path = CHARTS_DIR / "speed_over_time.png"
    speed_fig.savefig(speed_path, dpi=150, facecolor=SURFACE)
    plt.close(speed_fig)
    print(f"wrote {speed_path}")

    for i, target in enumerate(targets):
        color = SERIES_COLORS[i % len(SERIES_COLORS)]
        tr_fig = build_traceroute_figure(conn, target, cutoff, color)
        if tr_fig:
            safe_name = target.replace(".", "_")
            tr_path = CHARTS_DIR / f"traceroute_{safe_name}.png"
            tr_fig.savefig(tr_path, dpi=150, facecolor=SURFACE)
            plt.close(tr_fig)
            print(f"wrote {tr_path}")
    conn.close()


if __name__ == "__main__":
    main()
