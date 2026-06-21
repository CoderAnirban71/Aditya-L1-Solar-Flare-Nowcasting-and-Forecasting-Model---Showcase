// app.js
const API = 'http://localhost:8000/api';
let playing = false;
let softData = [], hardData = [];
const MAX_POINTS = 600;

// ── CHARTS ───────────────────────────────────────────────────
const chartOpts = (color, label) => ({
  type: 'line',
  data: {
    datasets: [{
      label,
      data: [],
      borderColor: color,
      borderWidth: 1,
      pointRadius: 0,
      fill: true,
      backgroundColor: color.replace(')', ',0.06)').replace('rgb', 'rgba'),
      tension: 0.1,
    }]
  },
  options: {
    animation: false,
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: {
        type: 'time',
        time: { unit: 'minute', displayFormats: { minute: 'HH:mm' } },
        ticks: { color: '#64748b', maxTicksLimit: 8, font: { size: 10 } },
        grid: { color: '#1e2d4a' }
      },
      y: {
        type: 'logarithmic',
        ticks: { color: '#64748b', font: { size: 10 } },
        grid: { color: '#1e2d4a' }
      }
    }
  }
});

const softChart = new Chart(
  document.getElementById('softChart'),
  chartOpts('rgb(96,165,250)', 'SoLEXS')
);
const hardChart = new Chart(
  document.getElementById('hardChart'),
  chartOpts('rgb(249,115,22)', 'HEL1OS')
);

// ── GAUGE ─────────────────────────────────────────────────────
const gaugeCanvas = document.getElementById('gaugeCanvas');
const gCtx = gaugeCanvas.getContext('2d');

function drawGauge(prob) {
  const w = gaugeCanvas.width, h = gaugeCanvas.height;
  gCtx.clearRect(0, 0, w, h);

  const cx = w / 2, cy = h - 10, r = 58;
  const startA = Math.PI, endA = 2 * Math.PI;

  // BG arc
  gCtx.beginPath();
  gCtx.arc(cx, cy, r, startA, endA);
  gCtx.strokeStyle = '#1e2d4a';
  gCtx.lineWidth = 10;
  gCtx.stroke();

  // Value arc
  const color = prob > 0.75 ? '#ff0000' : prob > 0.50 ? '#ff6b00' :
                prob > 0.25 ? '#f0a500' : '#1db954';
  gCtx.beginPath();
  gCtx.arc(cx, cy, r, startA, startA + (endA - startA) * prob);
  gCtx.strokeStyle = color;
  gCtx.lineWidth = 10;
  gCtx.lineCap = 'round';
  gCtx.stroke();

  // Needle
  const angle = Math.PI + Math.PI * prob;
  const nx = cx + (r - 15) * Math.cos(angle);
  const ny = cy + (r - 15) * Math.sin(angle);
  gCtx.beginPath();
  gCtx.moveTo(cx, cy);
  gCtx.lineTo(nx, ny);
  gCtx.strokeStyle = '#ffffff';
  gCtx.lineWidth = 2;
  gCtx.stroke();

  // Labels
  gCtx.fillStyle = '#64748b';
  gCtx.font = '9px monospace';
  gCtx.fillText('0%', cx - r + 2, cy + 12);
  gCtx.fillText('100%', cx + r - 28, cy + 12);

  // Center value
  gCtx.fillStyle = color;
  gCtx.font = 'bold 14px monospace';
  gCtx.textAlign = 'center';
  gCtx.fillText(`${Math.round(prob * 100)}%`, cx, cy - 16);
  gCtx.textAlign = 'left';
}

drawGauge(0);

// ── UPDATE GRAPH ─────────────────────────────────────────────
function updateGraph(buffer) {
  if (!buffer || buffer.length === 0) return;

  const softPts = buffer.map(p => ({ x: new Date(p.t), y: p.soft || 0.001 }));
  const hardPts = buffer.map(p => ({ x: new Date(p.t), y: p.hard || 0.001 }));

  softChart.data.datasets[0].data = softPts;
  hardChart.data.datasets[0].data = hardPts;
  softChart.update('none');
  hardChart.update('none');
}

// ── ALERT CLASSES ─────────────────────────────────────────────
const levelClass = {
  QUIET   : { css: '',               color: '#1db954', bulb: '💡' },
  LOW     : { css: 'alert-low',      color: '#7cbb00', bulb: '🟡' },
  MODERATE: { css: 'alert-moderate', color: '#f0a500', bulb: '🟠' },
  HIGH    : { css: 'alert-high',     color: '#ff6b00', bulb: '🔴' },
  EXTREME : { css: 'alert-extreme',  color: '#ff0000', bulb: '🚨' },
};

// ── UPDATE NOWCAST ────────────────────────────────────────────
function updateNowcast(nc) {
  const box   = document.getElementById('main-alert-box');
  const bulb  = document.getElementById('alert-bulb');
  const level = document.getElementById('alert-level');
  const cls   = nc.class || 'QUIET';
  const lc    = levelClass[cls] || levelClass.QUIET;

  // Remove old classes
  box.className = 'main-alert-box ' + lc.css;
  level.className = 'alert-level level-' + cls.toLowerCase();
  level.textContent = nc.alert ? cls : 'QUIET';
  bulb.textContent  = lc.bulb;

  if (nc.alert && cls !== 'QUIET') {
    bulb.classList.add('glowing');
  } else {
    bulb.classList.remove('glowing');
  }

  document.getElementById('nc-class').textContent  = nc.alert ? cls : '--';
  document.getElementById('nc-sig').textContent     = nc.sig    ? `${nc.sig}σ` : '--';
  document.getElementById('nc-hr').textContent      = nc.hr     ? nc.hr : '--';
  document.getElementById('nc-bands').textContent   = nc.n_bands ? nc.n_bands : '--';
  document.getElementById('nc-time').textContent    = nc.detected_at
    ? new Date(nc.detected_at).toUTCString().slice(17, 25) + ' UTC'
    : '--';
}

// ── UPDATE FORECAST ───────────────────────────────────────────
function updateForecast(fc) {
  if (!fc.ready) {
    drawGauge(0);
    document.getElementById('fc-class').textContent = 'BUFFERING...';
    document.getElementById('fc-prob').textContent  = '--%';
    document.getElementById('fc-conf').textContent  = '--';
    document.getElementById('fc-lead').textContent  = '~-- MIN';
    document.getElementById('fc-time').textContent  = '--:--:--';
    return;
  }

  const prob = (fc.probability || 0) / 100;
  drawGauge(prob);

  document.getElementById('fc-class').textContent = fc.level || '--';
  document.getElementById('fc-prob').textContent  = `${fc.probability || 0}%`;
  document.getElementById('fc-conf').textContent  = fc.confidence || '--';
  document.getElementById('fc-lead').textContent  = `~${fc.lead_time || 15} MIN`;
  document.getElementById('fc-time').textContent  = fc.predict_time || '--:--:--';

  // Upcoming cards
  const container = document.getElementById('upcoming-cards');
  const upcoming  = fc.upcoming || [];
  if (upcoming.length === 0) {
    container.innerHTML = '<div class="upcoming-empty">No upcoming flares in next 30 min</div>';
  } else {
    container.innerHTML = upcoming.map((u, i) => `
      <div class="upcoming-card level-${u.level.toLowerCase()}">
        <span class="upcoming-card-level" style="color:${
          u.level === 'EXTREME' ? '#ff0000' :
          u.level === 'HIGH'    ? '#ff6b00' :
          u.level === 'MODERATE'? '#f0a500' : '#7cbb00'
        }">${u.level} (${u.sig}σ)</span>
        <span class="upcoming-card-time">~${u.time} UTC</span>
      </div>
    `).join('');
  }
}

// ── UPDATE TABLE ──────────────────────────────────────────────
function updateTable(flares) {
  const tbody = document.getElementById('event-tbody');
  if (!flares || flares.length === 0) return;

  tbody.innerHTML = flares.map((f, i) => {
    const sig = parseFloat(f.peak_sig || 0);
    const cls = sig >= 100 ? 'extreme' : sig >= 50 ? 'high' :
                sig >= 20  ? 'moderate' : 'low';
    const label = sig >= 100 ? 'EXTREME' : sig >= 50 ? 'HIGH' :
                  sig >= 20  ? 'MODERATE' : 'LOW';
    return `
      <tr>
        <td>#${String(i+1).padStart(4,'0')}</td>
        <td>${f.start_time || '--'}</td>
        <td>${f.peak_time  || '--'}</td>
        <td>${parseFloat(f.duration_sec||0).toFixed(0)}s</td>
        <td>${f.n_bands    || '--'}</td>
        <td>${parseFloat(f.peak_sig||0).toFixed(1)}σ</td>
        <td>${parseFloat(f.hardness_ratio||0).toFixed(2)}</td>
        <td class="class-${cls}">${label}</td>
      </tr>
    `;
  }).join('');
}

// ── CONTROLS ──────────────────────────────────────────────────
async function togglePlay() {
  playing = !playing;
  const btn = document.getElementById('btn-play');
  if (playing) {
    await fetch(`${API}/play`, { method: 'POST' });
    btn.textContent = '⏸ Pause';
    btn.classList.add('active');
  } else {
    await fetch(`${API}/pause`, { method: 'POST' });
    btn.textContent = '▶ Play';
    btn.classList.remove('active');
  }
}

async function resetReplay() {
  playing = false;
  document.getElementById('btn-play').textContent = '▶ Play';
  document.getElementById('btn-play').classList.remove('active');
  await fetch(`${API}/reset`, { method: 'POST' });
}

async function setSpeed(val) {
  await fetch(`${API}/speed/${val}`, { method: 'POST' });
}

let seekTimeout;
async function seekTo(val) {
  clearTimeout(seekTimeout);
  seekTimeout = setTimeout(async () => {
    await fetch(`${API}/seek/${val}`, { method: 'POST' });
  }, 200);
}

// ── MAIN POLL LOOP ────────────────────────────────────────────
async function poll() {
  try {
    const [data, nc, fc, graph, catalog, appState] = await Promise.all([
      fetch(`${API}/data`).then(r => r.json()),
      fetch(`${API}/nowcast`).then(r => r.json()),
      fetch(`${API}/forecast`).then(r => r.json()),
      fetch(`${API}/graph`).then(r => r.json()),
      fetch(`${API}/catalog`).then(r => r.json()),
      fetch(`${API}/state`).then(r => r.json()),
    ]);

    // Header time
    document.getElementById('utc-display').textContent = `UTC: ${data.time || '--'}`;

    // Metric values
    document.getElementById('soft-val').textContent = `${data.soft} cts/s`;
    document.getElementById('hard-val').textContent = `${data.hard} cts/s`;

    // Timeline slider
    const slider = document.getElementById('timeline-slider');
    slider.max   = appState.total;
    slider.value = appState.idx;
    document.getElementById('progress-pct').textContent = `${data.progress}%`;

    // Play state sync
    if (appState.playing !== playing) {
      playing = appState.playing;
      const btn = document.getElementById('btn-play');
      btn.textContent = playing ? '⏸ Pause' : '▶ Play';
      playing ? btn.classList.add('active') : btn.classList.remove('active');
    }

    updateGraph(graph.buffer);
    updateNowcast(nc);
    updateForecast(fc);
    updateTable(catalog.flares);

  } catch(e) {
    console.error('Poll error:', e);
  }
}

// Poll every 200ms — smooth updates
setInterval(poll, 200);
poll();

// Load catalog once
fetch(`${API}/catalog`)
  .then(r => r.json())
  .then(d => updateTable(d.flares));