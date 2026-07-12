"""Download/upload speed sampling using the speedtest-cli library."""
import speedtest


def run_speed_test():
    st = speedtest.Speedtest()
    st.get_best_server()
    download_bps = st.download()
    upload_bps = st.upload()
    return {
        "download_mbps": download_bps / 1_000_000,
        "upload_mbps": upload_bps / 1_000_000,
        "ping_ms": st.results.ping,
        "server": st.results.server.get("host"),
    }
