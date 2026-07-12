"""Download/upload speed sampling using the speedtest-cli library.

Provides an optional live-progress callback (on_progress) alongside the
existing phase-completion callback (on_phase), so a caller can drive a
continuously-updating gauge during the download/upload phases rather than
only seeing the final number.
"""
import os
import time
import urllib.request

import speedtest

PROGRESS_MIN_INTERVAL_S = 0.25


def _download_chunk_byte_sizes(st):
    """Real byte size of each speedtest.net download test image, via HEAD request.

    speedtest-cli's config only gives pixel dimensions (e.g. 350, 750), not
    byte counts -- JPEG compression makes those unpredictable to guess. The
    test images are fixed files on the server, so a HEAD request to the
    same URLs the library uses gives the real Content-Length per size,
    letting live download progress be tracked in real bytes.
    """
    base = os.path.dirname(st.best["url"])
    byte_sizes = {}
    for size in set(st.config["sizes"]["download"]):
        url = f"{base}/random{size}x{size}.jpg"
        try:
            req = urllib.request.Request(
                url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                byte_sizes[size] = int(resp.headers.get("Content-Length", 0))
        except Exception:
            byte_sizes[size] = 0
    return byte_sizes


def _chunk_sizes_bytes(st, kind, byte_sizes=None):
    """Reconstruct the per-chunk byte-size list in the same order
    speedtest-cli's download()/upload() build their internal request lists,
    so a chunk index from the library's callback maps to the right size.
    """
    sizes = []
    for size in st.config["sizes"][kind]:
        for _ in range(st.config["counts"][kind]):
            sizes.append(byte_sizes[size] if byte_sizes else size)
    return sizes


def _run_with_progress(kind, run_fn, chunk_bytes, on_progress):
    completed_bytes = [0]
    start_time = [None]
    last_report = [0.0]

    def callback(i, request_count, start=False, end=False):
        if start_time[0] is None:
            start_time[0] = time.monotonic()
        if not end:
            return
        completed_bytes[0] += chunk_bytes[i] if i < len(chunk_bytes) else 0
        if on_progress is None:
            return
        now = time.monotonic()
        if now - last_report[0] < PROGRESS_MIN_INTERVAL_S:
            return
        last_report[0] = now
        elapsed = now - start_time[0]
        if elapsed <= 0:
            return
        mbps = (completed_bytes[0] * 8) / elapsed / 1_000_000
        on_progress(kind, mbps)

    return run_fn(callback=callback)


def run_speed_test(on_phase=None, on_progress=None):
    st = speedtest.Speedtest()
    st.get_best_server()
    ping_ms = st.results.ping
    if on_phase:
        on_phase("ping", ping_ms)

    download_byte_sizes = _download_chunk_byte_sizes(st)
    download_chunk_bytes = _chunk_sizes_bytes(st, "download", download_byte_sizes)
    download_bps = _run_with_progress(
        "download", st.download, download_chunk_bytes, on_progress
    )
    download_mbps = download_bps / 1_000_000
    if on_phase:
        on_phase("download", download_mbps)

    upload_chunk_bytes = _chunk_sizes_bytes(st, "upload")
    upload_bps = _run_with_progress(
        "upload", st.upload, upload_chunk_bytes, on_progress
    )
    upload_mbps = upload_bps / 1_000_000
    if on_phase:
        on_phase("upload", upload_mbps)

    return {
        "download_mbps": download_mbps,
        "upload_mbps": upload_mbps,
        "ping_ms": ping_ms,
        "server": st.results.server.get("host"),
    }
