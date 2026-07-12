"""Flask web dashboard for netwatch: charts + on-demand check-now."""
import io
import threading
import uuid

from flask import Flask, Response, jsonify, render_template

import chart
import netwatch

app = Flask(__name__)

CHART_BUILDERS = {
    "latency": lambda conn, cutoff: chart.build_latency_figure(
        conn, chart.targets_in_db(conn, None), cutoff),
    "loss": lambda conn, cutoff: chart.build_loss_figure(
        conn, chart.targets_in_db(conn, None), cutoff),
    "speed": lambda conn, cutoff: chart.build_speed_figure(conn, cutoff),
}

_jobs = {}
_jobs_lock = threading.Lock()


@app.route("/")
def index():
    conn, _ = chart.connect(None)
    targets = chart.targets_in_db(conn, None)
    conn.close()
    return render_template("index.html", targets=targets)


@app.route("/charts/<name>.png")
def chart_image(name):
    conn, cutoff = chart.connect(None)
    try:
        if name in CHART_BUILDERS:
            fig = CHART_BUILDERS[name](conn, cutoff)
        elif name.startswith("traceroute_"):
            target = name[len("traceroute_"):].replace("_", ".")
            targets = chart.targets_in_db(conn, None)
            try:
                target_index = targets.index(target)
            except ValueError:
                target_index = 0
            color = chart.SERIES_COLORS[target_index % len(chart.SERIES_COLORS)]
            fig = chart.build_traceroute_figure(conn, target, cutoff, color)
        else:
            return Response(status=404)

        if fig is None:
            return Response(status=404)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, facecolor=chart.SURFACE)
        chart.plt.close(fig)
        buf.seek(0)
        return Response(buf.getvalue(), mimetype="image/png")
    finally:
        conn.close()


def _set_job(job_id, **kwargs):
    with _jobs_lock:
        _jobs[job_id].update(kwargs)


def _run_check(job_id):
    def on_phase(phase, value):
        if phase == "ping":
            _set_job(job_id, phase="download", ping_ms=value, current_mbps=None)
        elif phase == "download":
            _set_job(job_id, phase="upload", download_mbps=value, current_mbps=None)
        elif phase == "upload":
            _set_job(job_id, phase="targets", upload_mbps=value, current_mbps=None)

    def on_progress(phase, value):
        _set_job(job_id, current_mbps=value)

    try:
        result = netwatch.sample_speedtest(on_phase=on_phase, on_progress=on_progress)
        if result is None:
            _set_job(job_id, phase="error", error="speed test failed, see netwatch.log")
            return

        targets = netwatch.build_targets()
        for target in targets:
            netwatch.sample_ping(target)
            netwatch.sample_traceroute(target)

        _set_job(job_id, phase="done")
    except Exception as e:
        _set_job(job_id, phase="error", error=str(e))


@app.route("/check-now", methods=["POST"])
def check_now():
    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {
            "phase": "ping",
            "ping_ms": None,
            "download_mbps": None,
            "upload_mbps": None,
            "current_mbps": None,
            "error": None,
        }
    threading.Thread(target=_run_check, args=(job_id,), daemon=True).start()
    return jsonify({"job_id": job_id}), 202


@app.route("/check-now/status/<job_id>")
def check_now_status(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        return Response(status=404)
    return jsonify(job)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7788, threaded=True)
