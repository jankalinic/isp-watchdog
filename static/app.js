const GAUGE_MAX = 1000;
// Same categorical slots as the historical speed chart (chart.py
// SERIES_COLORS[0]/[1]) so download/upload mean the same color everywhere.
const DOWNLOAD_COLOR = '#2a78d6';
const UPLOAD_COLOR = '#1baf7a';

const gaugeCanvas = document.getElementById('gauge');
const gauge = new Gauge(gaugeCanvas).setOptions({
  angle: 0.15,
  lineWidth: 0.3,
  radiusScale: 1,
  pointer: { length: 0.6, strokeWidth: 0.035, color: '#ffffff' },
  limitMax: true,
  limitMin: true,
  colorStart: DOWNLOAD_COLOR,
  colorStop: DOWNLOAD_COLOR,
  strokeColor: '#2c2c2a',
  generateGradient: false,
  highDpiSupport: true,
  staticLabels: {
    font: '10px sans-serif',
    labels: [0, 5, 10, 50, 100, 250, 500, 750, 1000],
    color: '#c3c2b7',
    fractionDigits: 0,
  },
});
gauge.maxValue = GAUGE_MAX;
gauge.setMinValue(0);
gauge.animationSpeed = 32;
gauge.set(0);

const statPing = document.getElementById('stat-ping');
const statDownload = document.getElementById('stat-download');
const statUpload = document.getElementById('stat-upload');
const gaugeValue = document.getElementById('gauge-value');
const checkStatus = document.getElementById('check-status');
const checkButton = document.getElementById('check-now');
const progressBar = document.getElementById('test-progress-bar');

const PHASE_LABELS = {
  ping: 'Testing ping...',
  download: 'Testing download speed...',
  upload: 'Testing upload speed...',
  targets: 'Running network diagnostics...',
  done: 'Done!',
  error: 'Check failed',
};

// Coarse overall-progress marks for the bottom progress bar -- there's no
// fine-grained "% through this phase" signal, so each phase just jumps to
// its mark, like most speed-test UIs do.
const PHASE_PROGRESS = {
  ping: 10,
  download: 35,
  upload: 65,
  targets: 90,
  done: 100,
  error: 100,
};

const ACTIVE_PHASES = new Set(['download', 'upload']);

let downloadShown = false;
let uploadShown = false;
let lastPhase = null;

function resetUI() {
  statPing.textContent = '—';
  statDownload.textContent = '—';
  statUpload.textContent = '—';
  gaugeValue.textContent = '0.00';
  gauge.setOptions({ colorStart: DOWNLOAD_COLOR, colorStop: DOWNLOAD_COLOR });
  gauge.set(0);
  downloadShown = false;
  uploadShown = false;
  lastPhase = null;
  progressBar.style.width = '0%';
  progressBar.style.backgroundColor = '#2dd4bf';
}

function refreshCharts() {
  const t = Date.now();
  document.querySelectorAll('.chart-img').forEach((img) => {
    const base = img.src.split('?')[0];
    img.src = `${base}?t=${t}`;
  });
}

function applyStatus(data) {
  checkStatus.textContent = PHASE_LABELS[data.phase] || data.phase;

  // Drop the needle back to zero and recolor for the new measurement phase,
  // like a real speedometer, before live progress starts arriving.
  if (data.phase !== lastPhase) {
    if (data.phase === 'download') {
      gauge.setOptions({ colorStart: DOWNLOAD_COLOR, colorStop: DOWNLOAD_COLOR });
    } else if (data.phase === 'upload') {
      gauge.setOptions({ colorStart: UPLOAD_COLOR, colorStop: UPLOAD_COLOR });
    }
    if (ACTIVE_PHASES.has(data.phase)) {
      gauge.set(0);
      gaugeValue.textContent = '0.00';
    }
    lastPhase = data.phase;
  }

  if (data.phase in PHASE_PROGRESS) {
    progressBar.style.width = `${PHASE_PROGRESS[data.phase]}%`;
    progressBar.style.backgroundColor = data.phase === 'error' ? '#d03b3b' : '#2dd4bf';
  }

  if (data.ping_ms !== null && data.ping_ms !== undefined) {
    statPing.textContent = data.ping_ms.toFixed(0);
  }

  // Live-updating reading while a phase is actively measuring.
  if (ACTIVE_PHASES.has(data.phase) &&
      data.current_mbps !== null && data.current_mbps !== undefined) {
    gauge.set(Math.min(data.current_mbps, GAUGE_MAX));
    gaugeValue.textContent = data.current_mbps.toFixed(2);
  }

  // Settle on the exact final value once a phase completes.
  if (data.download_mbps !== null && data.download_mbps !== undefined) {
    statDownload.textContent = data.download_mbps.toFixed(1);
    if (!downloadShown) {
      downloadShown = true;
      gauge.set(Math.min(data.download_mbps, GAUGE_MAX));
      gaugeValue.textContent = data.download_mbps.toFixed(2);
    }
  }

  if (data.upload_mbps !== null && data.upload_mbps !== undefined) {
    statUpload.textContent = data.upload_mbps.toFixed(1);
    if (!uploadShown) {
      uploadShown = true;
      gauge.set(Math.min(data.upload_mbps, GAUGE_MAX));
      gaugeValue.textContent = data.upload_mbps.toFixed(2);
    }
  }
}

async function pollStatus(jobId) {
  const res = await fetch(`/check-now/status/${jobId}`);
  const data = await res.json();
  applyStatus(data);

  if (data.phase === 'done' || data.phase === 'error') {
    checkButton.disabled = false;
    if (data.phase === 'done') {
      refreshCharts();
    } else {
      checkStatus.textContent = `Check failed: ${data.error}`;
    }
    return;
  }
  const delay = ACTIVE_PHASES.has(data.phase) ? 300 : 500;
  setTimeout(() => pollStatus(jobId), delay);
}

checkButton.addEventListener('click', async () => {
  checkButton.disabled = true;
  resetUI();
  checkStatus.textContent = PHASE_LABELS.ping;
  try {
    const res = await fetch('/check-now', { method: 'POST' });
    const data = await res.json();
    pollStatus(data.job_id);
  } catch (err) {
    checkStatus.textContent = `Check failed: ${err}`;
    checkButton.disabled = false;
  }
});

setInterval(refreshCharts, 60000);
