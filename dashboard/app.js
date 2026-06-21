// app.js
const API = '/api';
let playing = false;
let currentTime = null;
let liveFlares  = [];   // live detected flares list
let rollingIdx  = 0;    // rolling card index
let rollingTimer = null;
// ── CHARTS ───────────────────────────────────────────────────
const makeChart = (id, color, yMin, yMax) => new Chart(
  document.getElementById(id),
  {
    type: 'line',
    data: { datasets: [{ data: [], borderColor: color, borderWidth: 1,
      pointRadius: 0, fill: true,
      backgroundColor: color.replace('rgb','rgba').replace(')',',0.05)'),
      tension: 0.2 }] },
    options: {
      animation: false,
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        annotation: { annotations: {} }
      },
      scales: {
        x: {
          type: 'time',
          time: { unit: 'minute', displayFormats: { minute: 'HH:mm' } },
          ticks: { color: '#64748b', maxTicksLimit: 6, font: { size: 9 } },
          grid: { color: '#1e2d4a' },
        },
        y: {
          type: 'logarithmic',
          min: yMin,
          max: yMax,
          ticks: {
            color: '#64748b',
            font: { size: 9 },
            maxTicksLimit: 6,
            callback: function(value) {
              const map = {
                0.001: '10⁻³', 0.01: '10⁻²', 0.1: '10⁻¹',
                1: '10⁰', 10: '10¹', 100: '10²',
                1000: '10³', 10000: '10⁴', 100000: '10⁵'
              };
              return map[value] || '';
            }
          },
          grid: { color: '#1e2d4a', lineWidth: 0.5 }
        },
      }
    }
  }
);
const softChart = makeChart('softChart', 'rgb(96,165,250)', 1,     20000);
const hardChart = makeChart('hardChart', 'rgb(249,115,22)', 0.001, 5000);
// ── NOW LINE ──────────────────────────────────────────────────
function setNowLine(charts, time) {
  if (!time) return;
  const annotation = {
    type: 'line',
    xMin: time, xMax: time,
    borderColor: 'rgba(255,255,255,0.7)',
    borderWidth: 1.5,
    borderDash: [],
  };
  charts.forEach(chart => {
    chart.options.plugins.annotation.annotations = { nowLine: annotation };
    chart.update('none');
  });
}
// ── SMOOTH GRAPH UPDATE ───────────────────────────────────────
// Keep max 600 points, shift oldest, push newest
// X-axis fixed window = last 10 minutes
let lastBufferLen = 0;
function updateGraphSmooth(buffer) {
  if (!buffer || buffer.length === 0) return;
  const softDs = softChart.data.datasets[0];
  const hardDs = hardChart.data.datasets[0];
  // If buffer reset (seek), replace all
  if (buffer.length < lastBufferLen || softDs.data.length === 0) {
    softDs.data = buffer.map(p => ({ x: new Date(p.t), y: Math.max(p.soft, 0.001) }));
    hardDs.data = buffer.map(p => ({ x: new Date(p.t), y: Math.max(p.hard, 0.001) }));
  } else {
    // Only add new points
    const newPts = buffer.slice(lastBufferLen);
    newPts.forEach(p => {
      softDs.data.push({ x: new Date(p.t), y: Math.max(p.soft, 0.001) });
      hardDs.data.push({ x: new Date(p.t), y: Math.max(p.hard, 0.001) });
    });
    // Trim to 600
    if (softDs.data.length > 600) {
      const trim = softDs.data.length - 600;
      softDs.data.splice(0, trim);
      hardDs.data.splice(0, trim);
    }
  }
  // Replace data directly because backend already manages the 600-point sliding window
  softDs.data = buffer.map(p => ({ x: new Date(p.t), y: Math.max(p.soft, 0.1) }));
  hardDs.data = buffer.map(p => ({ x: new Date(p.t), y: Math.max(p.hard, 0.1) }));
  lastBufferLen = buffer.length;
  // Fixed x-axis: show last 10 min + 1 min future (for "now" line space)
  if (softDs.data.length > 0) {
    const last = softDs.data[softDs.data.length - 1].x;
    const xMax = new Date(last.getTime() + 60000);         // +1 min future
    const xMin = new Date(last.getTime() - 9 * 60000);    // -9 min past
    [softChart, hardChart].forEach(ch => {
      ch.options.scales.x.min = xMin;
      ch.options.scales.x.max = xMax;
      ch.update('none');
    });
    setNowLine([softChart, hardChart], last);
  }
}
// ── GAUGE ─────────────────────────────────────────────────────
const gCvs = document.getElementById('gauge');
const gCtx = gCvs.getContext('2d');
function drawGauge(prob) {
  const w = gCvs.width, h = gCvs.height;
  gCtx.clearRect(0, 0, w, h);
  const cx = w/2, cy = h - 8, r = 52;
  // BG
  gCtx.beginPath(); gCtx.arc(cx,cy,r,Math.PI,2*Math.PI);
  gCtx.strokeStyle = '#1e2d4a'; gCtx.lineWidth = 9; gCtx.stroke();
  // Value
  const col = prob>.75?'#ff2222':prob>.50?'#ff6b00':prob>.25?'#f0a500':'#1db954';
  gCtx.beginPath(); gCtx.arc(cx,cy,r,Math.PI,Math.PI+Math.PI*prob);
  gCtx.strokeStyle = col; gCtx.lineWidth = 9; gCtx.lineCap='round'; gCtx.stroke();
  // Needle
  const ang = Math.PI + Math.PI*prob;
  gCtx.beginPath(); gCtx.moveTo(cx,cy);
  gCtx.lineTo(cx+(r-14)*Math.cos(ang), cy+(r-14)*Math.sin(ang));
  gCtx.strokeStyle='#fff'; gCtx.lineWidth=2; gCtx.lineCap='round'; gCtx.stroke();
  // % text
  gCtx.fillStyle=col; gCtx.font='bold 13px monospace';
  gCtx.textAlign='center'; gCtx.fillText(`${Math.round(prob*100)}%`, cx, cy-14);
  gCtx.textAlign='left';
}
drawGauge(0);
// ── DYNAMIC LEAD TIME ─────────────────────────────────────────
function dynamicLeadTime(prob) {
  // Higher probability = flare more imminent = shorter lead time
  if (prob >= 95) return 5;
  if (prob >= 90) return 7;
  if (prob >= 85) return 10;
  if (prob >= 80) return 12;
  return 15;
}
// ── LEVEL HELPERS ─────────────────────────────────────────────
const LEVEL_COLOR = {
  QUIET:'#1db954', LOW:'#7cbb00', MODERATE:'#f0a500',
  HIGH:'#ff6b00', EXTREME:'#ff2222'
};
const LEVEL_CSS = {
  QUIET:'', LOW:'s-low', MODERATE:'s-moderate',
  HIGH:'s-high', EXTREME:'s-extreme'
};
// ── NOWCAST UPDATE ────────────────────────────────────────────
function updateNowcast(nc, curTime) {
  const cls   = (nc.class || 'QUIET').toUpperCase();
  const alert = nc.alert || false;
  // Alert square
  const sq  = document.getElementById('alert-square');
  const lvl = document.getElementById('alert-level-txt');
  const blb = document.getElementById('alert-bulb');
  sq.className  = 'alert-square ' + (LEVEL_CSS[cls] || '');
  lvl.className = 'alert-level-txt c-' + cls.toLowerCase();
  lvl.textContent = alert ? cls : 'QUIET';
  const bulbMap = {QUIET:'💡',LOW:'🟡',MODERATE:'🟠',HIGH:'🔴',EXTREME:'🚨'};
  blb.textContent = bulbMap[cls] || '💡';
  alert && cls !== 'QUIET' ? blb.classList.add('glow') : blb.classList.remove('glow');
  // Info
  document.getElementById('nc-class').textContent = alert ? cls : '--';
  document.getElementById('nc-conf').textContent  = alert ? '96%' : '--';
  document.getElementById('nc-sig').textContent   = nc.sig ? `${nc.sig}σ` : '--';
  document.getElementById('nc-bands').textContent = nc.n_bands || '--';
  document.getElementById('nc-time').textContent  =
    nc.detected_at
      ? new Date(nc.detected_at).toUTCString().slice(17,25) + ' UTC'
      : '--';
  // Live flares list — add if new
  if (alert && nc.peak_time) {
    const pt = nc.peak_time;
    if (!liveFlares.find(f => f.peak === pt)) {
      liveFlares.unshift({ peak: pt, cls, sig: nc.sig || 0 });
      if (liveFlares.length > 20) liveFlares.pop();
      renderLiveList();
    }
  }
}
function renderLiveList() {
  const el = document.getElementById('live-list');
  if (liveFlares.length === 0) {
    el.innerHTML = '<div class="live-empty">Monitoring...</div>';
    return;
  }
  el.innerHTML = liveFlares.map(f => `
    <div class="live-item">
      <span class="li-time">${new Date(f.peak).toUTCString().slice(17,25)} UTC</span>
      <span class="li-class">${f.cls} (${f.sig}σ)</span>
    </div>
  `).join('');
}
// ── FORECAST UPDATE ───────────────────────────────────────────
function updateForecast(fc, curTime) {
  if (!fc.ready) {
    drawGauge(0);
    document.getElementById('fc-class').textContent = 'BUFFERING';
    document.getElementById('fc-prob').textContent  = '--%';
    document.getElementById('fc-conf').textContent  = '--';
    document.getElementById('lead-sentence').textContent = 'Awaiting data buffer (300 rows)...';
    return;
  }
  const prob    = (fc.probability || 0) / 100;
  const leadMin = dynamicLeadTime(fc.probability || 0);
  drawGauge(prob);
  document.getElementById('fc-class').textContent = fc.level || '--';
  document.getElementById('fc-prob').textContent  = `${fc.probability || 0}%`;
  document.getElementById('fc-conf').textContent  = fc.confidence || '--';
  // Dynamic lead time sentence
  if (curTime && fc.alert) {
    const predictAt = new Date(new Date(curTime).getTime() + leadMin * 60000);
    const hms = predictAt.toUTCString().slice(17, 25);
    document.getElementById('lead-sentence').textContent =
      `⚠️ In ~${leadMin} min — around ${hms} UTC`;
    document.getElementById('lead-sentence').style.color = '#ff6b00';
  } else {
    document.getElementById('lead-sentence').textContent =
      prob > 0.3
        ? `📈 Elevated activity — monitoring`
        : `✅ No flare predicted in next 15 min`;
    document.getElementById('lead-sentence').style.color =
      prob > 0.3 ? '#f0a500' : '#1db954';
  }
  // Rolling cards
  renderRollingCards(fc.upcoming || [], fc.probability || 0);
}
// ── ROLLING CARDS ─────────────────────────────────────────────
let rollingCards = [];
let rollingPos   = 0;
function renderRollingCards(upcoming, totalProb) {
  const track = document.getElementById('rolling-track');
  if (upcoming.length === 0) {
    track.innerHTML = '<div class="rolling-empty">No flares in next 30 min</div>';
    clearInterval(rollingTimer);
    return;
  }
  rollingCards = upcoming;
  // Cumulative color — more flares = more red
  const intensity = Math.min(upcoming.length / 3, 1);
  const r = Math.round(255 * intensity);
  const g = Math.round(107 * (1 - intensity));
  track.innerHTML = upcoming.map((u, i) => {
    const col = i === 0
      ? `rgb(${r},${g},0)`
      : LEVEL_COLOR[u.level] || '#64748b';
    return `
      <div class="rolling-card cl-${u.level.toLowerCase()}"
           style="border-color:${col}">
        <span class="card-txt" style="color:${col}">
          ${u.level} flare — ${u.sig}σ
        </span>
        <span class="card-time">~${u.time} UTC</span>
      </div>
    `;
  }).join('');
  // Auto-scroll cards every 3 sec if multiple
  clearInterval(rollingTimer);
  if (upcoming.length > 1) {
    rollingTimer = setInterval(() => {
      rollingPos = (rollingPos + 1) % upcoming.length;
      track.style.transform = `translateY(-${rollingPos * 36}px)`;
    }, 3000);
  } else {
    track.style.transform = 'translateY(0)';
    rollingPos = 0;
  }
}
// ── CATALOG TABLE ─────────────────────────────────────────────
function updateTable(flares) {
  if (!flares || !flares.length) return;
  document.getElementById('ev-tbody').innerHTML = flares.map((f, i) => {
    const sig = parseFloat(f.peak_sig || 0);
    const cls = sig>=100?'extreme':sig>=50?'high':sig>=20?'moderate':'low';
    const lbl = sig>=100?'EXTREME':sig>=50?'HIGH':sig>=20?'MODERATE':'LOW';
    return `<tr>
      <td>${i+1}</td>
      <td>${(f.start_time||'').slice(0,19)}</td>
      <td>${(f.peak_time ||'').slice(0,19)}</td>
      <td>${parseFloat(f.duration_sec||0).toFixed(0)}</td>
      <td>${f.n_bands||'--'}</td>
      <td>${sig.toFixed(1)}</td>
      <td>${parseFloat(f.hardness_ratio||0).toFixed(2)}</td>
      <td class="c-${cls}">${lbl}</td>
    </tr>`;
  }).join('');
}
// ── CONTROLS ──────────────────────────────────────────────────
async function togglePlay() {
  playing = !playing;
  const btn = document.getElementById('btn-play');
  if (playing) {
    await fetch(`${API}/play`, {method:'POST'});
    btn.textContent = '⏸ Pause';
    btn.classList.add('active');
  } else {
    await fetch(`${API}/pause`, {method:'POST'});
    btn.textContent = '▶ Play';
    btn.classList.remove('active');
  }
}
async function resetReplay() {
  playing = false; liveFlares = []; lastBufferLen = 0;
  document.getElementById('btn-play').textContent = '▶ Play';
  document.getElementById('btn-play').classList.remove('active');
  softChart.data.datasets[0].data = [];
  hardChart.data.datasets[0].data = [];
  await fetch(`${API}/reset`, {method:'POST'});
  renderLiveList();
}
async function setSpeed(v) {
  await fetch(`${API}/speed/${v}`, {method:'POST'});
}
let seekTimer;
async function seekTo(v) {
  clearTimeout(seekTimer);
  lastBufferLen = 0;
  seekTimer = setTimeout(async () => {
    await fetch(`${API}/seek/${v}`, {method:'POST'});
  }, 150);
}
// ── MAIN POLL ─────────────────────────────────────────────────
async function poll() {
  try {
    const [data, nc, fc, graph, catalog, appState] = await Promise.all([
      fetch(`${API}/data`   ).then(r=>r.json()),
      fetch(`${API}/nowcast`).then(r=>r.json()),
      fetch(`${API}/forecast`).then(r=>r.json()),
      fetch(`${API}/graph`  ).then(r=>r.json()),
      fetch(`${API}/catalog`).then(r=>r.json()),
      fetch(`${API}/state`  ).then(r=>r.json()),
    ]);
    currentTime = data.time;
    // Header
    document.getElementById('utc-clock').textContent = `UTC ${data.time || '--'}`;
    document.getElementById('soft-live').textContent = `${data.soft} cts/s`;
    document.getElementById('hard-live').textContent = `${data.hard} cts/s`;
    // Slider
    const sk = document.getElementById('seek');
    sk.max = appState.total;
    if (!sk.matches(':active')) sk.value = appState.idx;
    document.getElementById('ctrl-progress').textContent = `${data.progress}%`;
    // Sync play state
    if (appState.playing !== playing) {
      playing = appState.playing;
      const btn = document.getElementById('btn-play');
      btn.textContent = playing ? '⏸ Pause' : '▶ Play';
      playing ? btn.classList.add('active') : btn.classList.remove('active');
    }
    updateGraphSmooth(graph.buffer);
    updateNowcast(nc, currentTime);
    updateForecast(fc, currentTime);
    updateTable(catalog.flares);
  } catch(e) { console.warn('Poll:', e.message); }
}
// ── START ─────────────────────────────────────────────────────
setInterval(poll, 200);
poll();
// Load catalog once
fetch(`${API}/catalog`).then(r=>r.json()).then(d => updateTable(d.flares));