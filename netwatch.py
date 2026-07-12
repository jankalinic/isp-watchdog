"""Continuous internet connection quality watchdog.

Samples ping latency/loss every --ping-interval seconds, a full traceroute
every --traceroute-interval seconds, and a download/upload speed test every
--speed-test-interval seconds (once per cycle, not per target), writing
results to netwatch.db. Runs until interrupted (Ctrl-C or SIGTERM).

sample_ping/sample_traceroute/sample_speedtest are also imported directly
by app.py to run an on-demand check from the web dashboard.
"""
import argparse
import concurrent.futures
import logging
import signal
import time

import bandwidth
import db
import network

PING_INTERVAL_S = 60
TRACEROUTE_INTERVAL_S = 900
SPEED_TEST_INTERVAL_S = 1800
MAX_WORKERS = 8

LOG_PATH = db.DB_PATH.parent / "netwatch.log"

_stop = False


def _handle_stop(signum, frame):
    global _stop
    _stop = True


def build_targets():
    gateway = network.get_default_gateway()
    return [gateway, "1.1.1.1", "8.8.8.8"]


def sample_ping(target):
    logging.info("pinging %s", target)
    conn = db.init_db()
    try:
        rtt_ms, lost = network.ping_host(target)
        db.insert_ping(conn, time.time(), target, rtt_ms, lost)
    except Exception:
        logging.exception("ping sample failed for %s", target)
    finally:
        conn.close()


def sample_traceroute(target):
    conn = db.init_db()
    logging.info("traceroute for %s", target)
    try:
        hops = network.traceroute_host(target)
        ts = time.time()
        for hop in hops:
            db.insert_traceroute(
                conn, ts, target,
                hop["hop_num"], hop["hop_ip"], hop["rtt_ms"], hop["timed_out"],
            )
    except Exception:
        logging.exception("traceroute sample failed for %s", target)
    finally:
        conn.close()


def sample_speedtest(on_phase=None, on_progress=None):
    conn = db.init_db()
    logging.info("speedtest for %s", on_phase)
    try:
        result = bandwidth.run_speed_test(on_phase=on_phase, on_progress=on_progress)
        db.insert_speed_sample(
            conn, time.time(), result["download_mbps"], result["upload_mbps"],
            result["ping_ms"], result["server"],
        )
        return result
    except Exception:
        logging.exception("speed test sample failed")
        return None
    finally:
        conn.close()


def _idle(futures, key):
    future = futures.get(key)
    return future is None or future.done()


def main():
    parser = argparse.ArgumentParser(description="Internet connection quality watchdog")
    parser.add_argument("--ping-interval", type=float, default=PING_INTERVAL_S)
    parser.add_argument("--traceroute-interval", type=float, default=TRACEROUTE_INTERVAL_S)
    parser.add_argument("--speed-test-interval", type=float, default=SPEED_TEST_INTERVAL_S)
    args = parser.parse_args()

    logging.basicConfig(
        filename=str(LOG_PATH), level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    targets = build_targets()
    db.init_db().close()  # ensure schema exists before any worker thread writes
    logging.info("starting watchdog, targets=%s", targets)
    print(f"netwatch started, targets={targets}, logging to {LOG_PATH}")

    next_ping = {t: 0.0 for t in targets}
    next_traceroute = {t: 0.0 for t in targets}
    next_speedtest = 0.0
    futures = {}

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS)
    try:
        while not _stop:
            try:
                now = time.monotonic()
                for target in targets:
                    ping_key = (target, "ping")
                    if now >= next_ping[target] and _idle(futures, ping_key):
                        futures[ping_key] = executor.submit(sample_ping, target)
                        next_ping[target] = now + args.ping_interval

                    tr_key = (target, "traceroute")
                    if now >= next_traceroute[target] and _idle(futures, tr_key):
                        futures[tr_key] = executor.submit(sample_traceroute, target)
                        next_traceroute[target] = now + args.traceroute_interval

                speed_key = ("_global_", "speedtest")
                if now >= next_speedtest and _idle(futures, speed_key):
                    futures[speed_key] = executor.submit(sample_speedtest)
                    next_speedtest = now + args.speed_test_interval
            except Exception:
                logging.exception("unexpected error in main loop iteration")
            time.sleep(1)
    finally:
        executor.shutdown(wait=True)
        logging.info("watchdog stopped")
        print("netwatch stopped")


if __name__ == "__main__":
    main()
