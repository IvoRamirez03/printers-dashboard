/* global POLL_INTERVAL injected from template */

const POLL_MS = (typeof POLL_INTERVAL !== 'undefined' ? POLL_INTERVAL : 120) * 1000;

let currentFilter = 'all';
let lastData = null;
let firstLoad = true;

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

async function fetchStatus() {
  try {
    const res  = await fetch('/api/status');
    const data = await res.json();
    lastData = data;
    updateUI(data);

    if (firstLoad && data.scan_count > 0) {
      firstLoad = false;
      hideLoader();
    }
  } catch (e) {
    console.error('Fetch error', e);
  }
}

async function triggerScan() {
  const btn = document.getElementById('scan-btn');
  btn.disabled = true;
  btn.textContent = 'Escaneando...';
  try {
    await fetch('/api/scan', { method: 'POST' });
    setTimeout(poll, 800);
  } catch (e) {
    btn.disabled = false;
    btn.textContent = 'Escanear ahora';
  }
}

async function poll() {
  await fetchStatus();
  setTimeout(poll, POLL_MS);
}

// ---------------------------------------------------------------------------
// Loading overlay
// ---------------------------------------------------------------------------

function hideLoader() {
  const overlay = document.getElementById('loading-overlay');
  if (overlay) overlay.classList.add('hidden');
}

// ---------------------------------------------------------------------------
// Filter
// ---------------------------------------------------------------------------

function setFilter(f, el) {
  currentFilter = f;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
  if (lastData) renderGrid(lastData.printers);
}

// ---------------------------------------------------------------------------
// UI update
// ---------------------------------------------------------------------------

function updateUI(data) {
  const scanTime = document.getElementById('scan-time');
  const btn      = document.getElementById('scan-btn');

  if (data.scanning) {
    btn.disabled    = true;
    btn.textContent = 'Escaneando...';
  } else {
    btn.disabled    = false;
    btn.textContent = 'Escanear ahora';
    scanTime.textContent = data.last_scan ? 'Actualizado: ' + data.last_scan : '—';
  }

  const printers = data.printers || [];

  document.getElementById('count-total').textContent    = printers.length;
  document.getElementById('count-critical').textContent = printers.filter(p => p.level === 'critical').length;
  document.getElementById('count-low').textContent      = printers.filter(p => p.level === 'low').length;
  document.getElementById('count-ok').textContent       = printers.filter(p => p.level === 'ok' || p.level === 'unknown').length;

  renderGrid(printers);
}

function renderGrid(printers) {
  const grid = document.getElementById('grid');

  const filtered = currentFilter === 'all'
    ? printers
    : currentFilter === 'ok'
      ? printers.filter(p => p.level === 'ok' || p.level === 'unknown')
      : printers.filter(p => p.level === currentFilter);

  if (!filtered.length) {
    grid.innerHTML = `<div class="state-msg">${
      printers.length === 0
        ? 'Esperando primer escaneo...'
        : 'No hay impresoras en este estado.'
    }</div>`;
    return;
  }

  // Ordenar por IP ascendente (último octeto)
  const sorted = [...filtered].sort((a, b) => {
    const numA = parseInt(a.ip.split('.').pop(), 10);
    const numB = parseInt(b.ip.split('.').pop(), 10);
    return numA - numB;
  });

  grid.innerHTML = sorted.map((p, i) => cardHTML(p, i)).join('');
}

// ---------------------------------------------------------------------------
// Card HTML
// ---------------------------------------------------------------------------

function cardHTML(p, idx) {
  const statusClass = {
    idle:     'status-idle',
    printing: 'status-printing',
    warmup:   'status-warning',
    other:    'status-other',
    unknown:  'status-unknown',
  }[p.status] || 'status-unknown';

  const statusLabel = {
    idle:     'Disponible',
    printing: 'Imprimiendo',
    warmup:   'Calentando',
    other:    'Otro',
    unknown:  'Desconocido',
  }[p.status] || p.status || 'Desconocido';

  // Alerts
  let alertsHTML = '';
  if (p.alerts && p.alerts.length > 0) {
    const warnAlerts = ['genuineHPSupplyFlow', 'singleTrayLop', 'engineInitializing'];
    const tags = p.alerts.map(a => {
      const cls = warnAlerts.includes(a) ? 'alert-tag warn' : 'alert-tag';
      return `<span class="${cls}">${esc(a)}</span>`;
    }).join('');
    alertsHTML = `<div class="card-alerts">${tags}</div>`;
  }

  // Supplies
  let suppliesHTML = '';
  if (p.supplies && p.supplies.length > 0) {
    suppliesHTML = p.supplies.map(s => {
      const name = shortenName(s.name);
      if (s.pct === null || s.pct === undefined) {
        const detail = (s.pages !== undefined && s.pages !== null)
          ? `~${Number(s.pages).toLocaleString('es-ES')} pag. restantes`
          : 'sin datos';
        return `
          <div class="supply-row">
            <span class="supply-name" title="${esc(s.name)}">${esc(name)}</span>
            <span class="supply-unknown-text">${detail}</span>
          </div>`;
      }
      return `
        <div class="supply-row">
          <span class="supply-name" title="${esc(s.name)}">${esc(name)}</span>
          <div class="supply-bar-wrap">
            <div class="supply-bar bar-${s.level}" style="width:${s.pct}%"></div>
          </div>
          <span class="supply-pct pct-${s.level}">${s.pct}%</span>
        </div>`;
    }).join('');
  } else {
    suppliesHTML = '<span style="font-size:11px;color:var(--ink-light)">Sin datos de consumibles</span>';
  }

  const pages     = p.pages ? parseInt(p.pages).toLocaleString('es-ES') + ' pag.' : '—';
  const modelLine = p.model ? `<div class="card-desc" title="${esc(p.model)}">${esc(p.model)}</div>` : '';
  const tonerLine = p.toner_ref ? `<div class="card-toner">${esc(p.toner_ref)}</div>` : '';
  const delay     = `animation-delay:${idx * 40}ms`;

  return `
    <div class="card" data-level="${p.level}" style="${delay}">
      <div class="card-header">
        <div class="card-title-group">
          <div class="card-name">${esc(p.name)}</div>
          <div class="card-ip">${esc(p.ip)}</div>
          ${modelLine}
          ${tonerLine}
        </div>
        <div class="card-meta">
          <span class="status-badge ${statusClass}">${statusLabel}</span>
          <span class="pages-count">${pages}</span>
        </div>
      </div>
      ${alertsHTML}
      <div class="card-supplies">${suppliesHTML}</div>
    </div>`;
}

// ---------------------------------------------------------------------------
// CSV export
// ---------------------------------------------------------------------------

function exportCSV() {
  if (!lastData || !lastData.printers || lastData.printers.length === 0) {
    alert('No hay datos para exportar. Espera a que termine el escaneo.');
    return;
  }

  const rows = [];
  rows.push([
    'IP', 'Nombre', 'Modelo', 'Referencia toner', 'Estado', 'Paginas',
    'Nivel global', 'Consumible', 'Porcentaje', 'Paginas restantes',
    'Nivel consumible', 'Alertas', 'Ultima actualizacion'
  ].join(';'));

  for (const p of lastData.printers) {
    const alertas   = (p.alerts || []).join(' | ');
    const timestamp = lastData.last_scan || '';

    if (p.supplies && p.supplies.length > 0) {
      for (const s of p.supplies) {
        rows.push([
          p.ip, csvEsc(p.name), csvEsc(p.model), csvEsc(p.toner_ref),
          p.status || '', p.pages || '', p.level || '',
          csvEsc(s.name),
          s.pct  !== null && s.pct  !== undefined ? s.pct  + '%' : '',
          s.pages !== null && s.pages !== undefined ? s.pages : '',
          s.level || '', csvEsc(alertas), timestamp,
        ].join(';'));
      }
    } else {
      rows.push([
        p.ip, csvEsc(p.name), csvEsc(p.model), csvEsc(p.toner_ref),
        p.status || '', p.pages || '', p.level || '',
        '', '', '', '', csvEsc(alertas), timestamp,
      ].join(';'));
    }
  }

  const bom     = '\uFEFF';
  const content = bom + rows.join('\r\n');
  const blob    = new Blob([content], { type: 'text/csv;charset=utf-8;' });
  const url     = URL.createObjectURL(blob);
  const ts      = new Date().toISOString().slice(0, 16).replace('T', '_').replace(':', '-');
  const a       = document.createElement('a');
  a.href        = url;
  a.download    = `impresoras_${ts}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function csvEsc(val) {
  if (!val) return '';
  const s = String(val).replace(/"/g, '""');
  return s.includes(';') || s.includes('"') || s.includes('\n') ? `"${s}"` : s;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function shortenName(name) {
  return name
    .replace(/Cartridge\s+HP\s+/i, '')
    .replace(/Toner Cartridge/i, 'Toner')
    .replace(/Ink Cartridge/i, 'Tinta')
    .replace(/ink HP /i, '')
    .replace(/Drum Unit/i, 'Tambor')
    .replace(/Belt Unit/i, 'Correa')
    .replace(/Waste Toner(?: Box)?/i, 'Residuos')
    .replace(/Ink Absorber/i, 'Absorbedor')
    .trim();
}

function esc(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
  poll();
});