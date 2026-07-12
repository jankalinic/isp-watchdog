"""SQLite storage for netwatch ping/traceroute/speed samples."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "netwatch.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS ping_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    target TEXT NOT NULL,
    rtt_ms REAL,
    lost INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ping_target_ts ON ping_samples (target, ts);

CREATE TABLE IF NOT EXISTS traceroute_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    target TEXT NOT NULL,
    hop_num INTEGER NOT NULL,
    hop_ip TEXT,
    rtt_ms REAL,
    timed_out INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tr_target_ts ON traceroute_samples (target, ts);

CREATE TABLE IF NOT EXISTS speed_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    download_mbps REAL,
    upload_mbps REAL,
    ping_ms REAL,
    server TEXT
);
CREATE INDEX IF NOT EXISTS idx_speed_ts ON speed_samples (ts);
"""


def init_db(path=DB_PATH):
    conn = sqlite3.connect(str(path), timeout=10)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def insert_ping(conn, ts, target, rtt_ms, lost):
    conn.execute(
        "INSERT INTO ping_samples (ts, target, rtt_ms, lost) VALUES (?, ?, ?, ?)",
        (ts, target, rtt_ms, int(lost)),
    )
    conn.commit()


def insert_traceroute(conn, ts, target, hop_num, hop_ip, rtt_ms, timed_out):
    conn.execute(
        """INSERT INTO traceroute_samples
           (ts, target, hop_num, hop_ip, rtt_ms, timed_out)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (ts, target, hop_num, hop_ip, rtt_ms, int(timed_out)),
    )
    conn.commit()


def insert_speed_sample(conn, ts, download_mbps, upload_mbps, ping_ms, server):
    conn.execute(
        """INSERT INTO speed_samples
           (ts, download_mbps, upload_mbps, ping_ms, server)
           VALUES (?, ?, ?, ?, ?)""",
        (ts, download_mbps, upload_mbps, ping_ms, server),
    )
    conn.commit()
