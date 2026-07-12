"""Ping/traceroute sampling helpers backed by system ping/traceroute/route binaries.

Supports macOS (Darwin, BSD tools) and Linux (Raspberry Pi OS and similar).
"""
import platform
import re
import subprocess

PING_TIME_RE = re.compile(r"time=([\d.]+)\s*ms")
GATEWAY_RE_DARWIN = re.compile(r"^\s*gateway:\s*(\S+)", re.MULTILINE)
GATEWAY_RE_LINUX = re.compile(r"^default via (\S+)", re.MULTILINE)
HOP_IP_RE = re.compile(r"\(([\d.]+)\)")
HOP_TIME_RE = re.compile(r"([\d.]+)\s*ms")


def get_default_gateway():
    system = platform.system()
    if system == "Darwin":
        result = subprocess.run(
            ["route", "-n", "get", "default"],
            capture_output=True, text=True, timeout=5,
        )
        match = GATEWAY_RE_DARWIN.search(result.stdout)
    elif system == "Linux":
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True, text=True, timeout=5,
        )
        match = GATEWAY_RE_LINUX.search(result.stdout)
    else:
        raise RuntimeError(f"unsupported platform: {system}")

    if not match:
        raise RuntimeError(f"could not determine default gateway from: {result.stdout!r}")
    return match.group(1)


def ping_host(host, timeout_ms=2000):
    system = platform.system()
    if system == "Linux":
        timeout_s = max(1, round(timeout_ms / 1000))
        cmd = ["ping", "-c", "1", "-W", str(timeout_s), host]
    else:
        cmd = ["ping", "-c", "1", "-W", str(timeout_ms), host]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=(timeout_ms / 1000) + 2,
        )
    except subprocess.TimeoutExpired:
        return None, True

    match = PING_TIME_RE.search(result.stdout)
    if match:
        return float(match.group(1)), False
    return None, True


def traceroute_host(host, max_hops=20, wait_s=1):
    try:
        result = subprocess.run(
            ["traceroute", "-q", "1", "-w", str(wait_s), "-m", str(max_hops), host],
            capture_output=True, text=True, timeout=max_hops * wait_s + 10,
        )
        output = result.stdout
    except subprocess.TimeoutExpired as e:
        output = e.stdout.decode() if e.stdout else ""

    return _parse_traceroute(output)


def _parse_traceroute(output):
    hops = []
    for line in output.splitlines():
        line = line.strip()
        if not line or not line[0].isdigit():
            continue
        parts = line.split(None, 1)
        hop_num = int(parts[0])
        rest = parts[1] if len(parts) > 1 else ""
        if rest.startswith("*"):
            hops.append({"hop_num": hop_num, "hop_ip": None, "rtt_ms": None, "timed_out": True})
            continue
        ip_match = HOP_IP_RE.search(rest)
        time_match = HOP_TIME_RE.search(rest)
        hops.append({
            "hop_num": hop_num,
            "hop_ip": ip_match.group(1) if ip_match else None,
            "rtt_ms": float(time_match.group(1)) if time_match else None,
            "timed_out": ip_match is None,
        })
    return hops
