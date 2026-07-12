"""Flask web dashboard for netwatch: charts + on-demand check-now."""
import io
import time

from flask import Flask, Response, render_template

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


@app.route("/check-now", methods=["POST"])
def check_now():
    try:
        targets = netwatch.build_targets()
        for target in targets:
            netwatch.sample_ping(target)
            netwatch.sample_traceroute(target)
        netwatch.sample_speedtest()
        return {"status": "ok", "ts": time.time()}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
