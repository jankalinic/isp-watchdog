const GAUGE_MAX = 1000;

const gaugeCanvas = document.getElementById('gauge');
const gauge = new Gauge(gaugeCanvas).setOptions({
  angle: 0.15,
  lineWidth: 0.3,
  radiusScale: 1,
  pointer: { length: 0.6, strokeWidth: 0.035, color: '#ffffff' },
  limitMax: true,
  limitMin: true,
  colorStart: '#2a78d6',
  colorStop: '#1baf7a',
  strokeColor: '#2c2c2a',
  generateGradient: true,
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

const PHASE_LABELS = {
  ping: 'Testing ping...',
  download: 'Testing download speed...',
  upload: 'Testing upload speed...',
  targets: 'Running network diagnostics...',
  done: 'Done!',
  error: 'Check failed',
};

let downloadShown = false;
let uploadShown = false;

function resetUI() {
  statPing.textContent = '—';
  statDownload.textContent = '—';
  statUpload.textContent = '—';
  gaugeValue.textContent = '0.00';
  gauge.set(0);
  downloadShown = false;
  uploadShown = false;
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

  if (data.ping_ms !== null && data.ping_ms !== undefined) {
    statPing.textContent = data.ping_ms.toFixed(0);
  }

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
      gauge.set(0);
      setTimeout(() => {
        gauge.set(Math.min(data.upload_mbps, GAUGE_MAX));
        gaugeValue.textContent = data.upload_mbps.toFixed(2);
      }, 300);
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
  setTimeout(() => pollStatus(jobId), 500);
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
