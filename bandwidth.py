"""Download/upload speed sampling using the speedtest-cli library."""
import speedtest


def run_speed_test(on_phase=None):
    st = speedtest.Speedtest()
    st.get_best_server()
    ping_ms = st.results.ping
    if on_phase:
        on_phase("ping", ping_ms)

    download_mbps = st.download() / 1_000_000
    if on_phase:
        on_phase("download", download_mbps)

    upload_mbps = st.upload() / 1_000_000
    if on_phase:
        on_phase("upload", upload_mbps)

    return {
        "download_mbps": download_mbps,
        "upload_mbps": upload_mbps,
        "ping_ms": ping_ms,
        "server": st.results.server.get("host"),
    }
