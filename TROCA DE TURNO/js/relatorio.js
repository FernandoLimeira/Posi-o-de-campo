const STORAGE_KEY = 'posicao-campo-v1-state';

let rendered = false;
let autoPrintScheduled = false;

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function printMetricIcon(index) {
  const icons = [
    '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 21V11l6 4v-5l6 4V5h4v16H3Z"/><path d="M6 21v-3M10 21v-3M15 21v-3"/></svg>',
    '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3.5"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1"/></svg>',
    '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7h11v10H3Z"/><path d="M14 11h4l3 3v3h-7Z"/><circle cx="7" cy="18" r="2"/><circle cx="18" cy="18" r="2"/></svg>',
    '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m12 2 8 4.5v11L12 22l-8-4.5v-11L12 2Z"/><path d="m4 6.5 8 4.5 8-4.5M12 11v11"/></svg>',
    '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3.5"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1"/></svg>',
    '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7h11v10H3Z"/><path d="M14 11h4l3 3v3h-7Z"/><circle cx="7" cy="18" r="2"/><circle cx="18" cy="18" r="2"/></svg>'
  ];
  return icons[index] || icons[0];
}

function getHeaderData(generatedAt) {
  const now = generatedAt ? new Date(generatedAt) : new Date();
  const safeDate = Number.isNaN(now.getTime()) ? new Date() : now;
  const hour = safeDate.getHours();
  return {
    greeting: hour < 12 ? 'BOM DIA!' : hour < 18 ? 'BOA TARDE!' : 'BOA NOITE!',
    date: safeDate.toLocaleDateString('pt-BR')
  };
}

function normalizeUnit(unit, index) {
  const fallbackCodes = ['PPT', 'NRD', 'RBR', 'PST'];
  const fallbackNames = ['PARAGUAÇU PAULISTA', 'NARANDIBA', 'RIO BRILHANTE', 'PARAÍSA TEMPO'];
  return {
    code: unit?.code || fallbackCodes[index] || `UN${index + 1}`,
    name: unit?.name || fallbackNames[index] || 'UNIDADE',
    border: ['active', 'attention', 'critical'].includes(unit?.border) ? unit.border : 'active',
    rows: Array.isArray(unit?.rows) ? unit.rows : [],
    metrics: Array.isArray(unit?.metrics) ? unit.metrics.slice(0, 6) : [],
    observation: unit?.observation || '-',
    changes: unit?.changes || '-',
    rain: Array.isArray(unit?.rain) ? unit.rain : []
  };
}

function metricValue(unit, index, label, unitLabel) {
  const metric = unit.metrics[index];
  if (Array.isArray(metric) && metric.length >= 3) {
    return {
      label: metric[1] || label,
      value: metric[2] || `0 ${unitLabel}`
    };
  }
  return { label, value: `0 ${unitLabel}` };
}

function printUnitCard(unit) {
  const rowDensity = unit.rows.length > 10 ? 'rows-very-dense' : unit.rows.length > 8 ? 'rows-dense' : '';
  const rainDensity = unit.rain.length > 8 ? 'rain-dense' : '';

  const rows = unit.rows.length
    ? unit.rows.map(row => {
      const [front = '', sector = '', color = 'yellow', status = ''] = Array.isArray(row) ? row : [];
      const safeColor = ['green', 'yellow', 'red'].includes(color) ? color : 'yellow';
      return `
        <tr>
          <td><span class="print-front-cell"><i class="print-status-dot ${safeColor}"></i>${escapeHtml(front)}</span></td>
          <td>${escapeHtml(sector)}</td>
          <td><span class="print-status-cell ${safeColor}">${escapeHtml(status)}</span></td>
        </tr>`;
    }).join('')
    : '<tr class="print-empty-row"><td colspan="3">Aguardando preenchimento do turno</td></tr>';

  const definitions = [
    ['INDÚSTRIA', 'TN/H'],
    ['MOAGEM TURNO', 'TN/H'],
    ['ENTREGA TURNO', 'TN/H'],
    ['ESTOQUE', 'CARGAS'],
    ['MOAGEM ÚLTIMAS 3H', 'TN/H'],
    ['ENTREGA ÚLTIMAS 3H', 'TN/H']
  ];

  const metrics = definitions.map(([label, unitLabel], index) => {
    const metric = metricValue(unit, index, label, unitLabel);
    return `
      <div class="print-metric">
        <span class="print-metric-icon">${printMetricIcon(index)}</span>
        <span class="print-metric-copy">
          <small>${escapeHtml(metric.label)}</small>
          <strong>${escapeHtml(metric.value)}</strong>
        </span>
      </div>`;
  }).join('');

  const rain = unit.rain.length
    ? unit.rain.map(item => {
      const [eq = '', turn = 0, accum = 0] = Array.isArray(item) ? item : [];
      return `<div class="print-rain-row"><span>${escapeHtml(eq)}</span><span>${escapeHtml(turn)}</span><span>/</span><span>${escapeHtml(accum)}</span></div>`;
    }).join('')
    : '<div class="print-rain-empty">Sem apontamento de chuva</div>';

  return `
    <article class="print-unit-card ${unit.border} ${rowDensity} ${rainDensity}">
      <header class="print-unit-header">
        <span class="print-unit-mark" aria-hidden="true"><i></i><i></i><i></i></span>
        <div class="print-unit-name">
          <strong>${escapeHtml(unit.code)}</strong>
          <span>${escapeHtml(unit.name)}</span>
        </div>
      </header>

      <div class="print-table-wrap">
        <table class="print-table">
          <thead><tr><th>Frente</th><th>Setor</th><th>Status</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>

      <div class="print-metrics">${metrics}</div>

      <div class="print-unit-bottom">
        <div class="print-notes">
          <h3>Observação</h3>
          <p>${escapeHtml(unit.observation || '-')}</p>
          <h3>Mudanças</h3>
          <p>${escapeHtml(unit.changes || '-')}</p>
        </div>
        <div class="print-rain-box">
          <div class="print-rain-title">Chuva turno / acum. (mm)</div>
          ${rain}
        </div>
      </div>
    </article>`;
}

function buildReport(payload) {
  const rawUnits = Array.isArray(payload?.units) ? payload.units : [];
  if (!rawUnits.length) return false;

  const units = rawUnits.slice(0, 4).map(normalizeUnit);
  while (units.length < 4) units.push(normalizeUnit(null, units.length));

  const { greeting, date } = getHeaderData(payload?.generatedAt);
  const report = document.querySelector('#print-report');

  report.innerHTML = `
    <div class="print-topbar">
      <div class="print-greeting">
        <span class="print-calendar" aria-hidden="true">▦</span>
        <strong>${greeting}</strong>
        <span class="print-separator" aria-hidden="true"></span>
        <span class="print-date">${date} - TC</span>
      </div>
      <div class="print-cocal"><span class="print-cocal-mark" aria-hidden="true"></span><strong>cocal</strong></div>
    </div>

    <header class="print-hero">
      <img class="print-hero-image" src="assets/cornfield.svg" alt="" />
      <div class="print-hero-copy">
        <h1><span class="line-white">Posição de campo</span><span class="line-green">Atualizada</span></h1>
        <p class="print-hero-subtitle">Segurança e qualidade em nossas operações!</p>
      </div>
      <div class="print-slogan">Juntos<br>por uma safra<br>mais segura<br>e produtiva.</div>
      <div class="print-legend">
        <span class="print-legend-item"><i class="print-legend-dot green"></i>Em atividade</span>
        <span class="print-legend-item"><i class="print-legend-dot yellow"></i>Solo úmido, mudança ou teste</span>
        <span class="print-legend-item"><i class="print-legend-dot red"></i>Indústria parada ou situação crítica</span>
      </div>
    </header>

    <section class="print-units-grid">${units.map(printUnitCard).join('')}</section>

    <footer class="print-footer">
      <div class="print-footer-highlights">
        <div class="print-footer-item"><span class="print-footer-icon">⌂</span><span class="print-footer-copy">Segurança<br>sempre</span></div>
        <div class="print-footer-item"><span class="print-footer-icon">♧</span><span class="print-footer-copy">Operação<br>com qualidade</span></div>
        <div class="print-footer-item"><span class="print-footer-icon">●●</span><span class="print-footer-copy">Pessoas<br>que fazem<br>a diferença</span></div>
        <div class="print-footer-item"><span class="print-footer-icon">▥</span><span class="print-footer-copy">Resultados<br>sustentáveis</span></div>
      </div>
      <div class="print-footer-bottom">
        <span class="print-footer-brand">COA &nbsp; | &nbsp; COCAL &nbsp; | &nbsp; SAFRA 2026</span>
        <span class="print-footer-signature">Juntos fazemos mais!</span>
      </div>
    </footer>`;

  rendered = true;
  document.querySelector('#report-error').hidden = true;
  document.title = `Posicao-de-Campo-${date.replaceAll('/', '-')}`;
  scheduleAutoPrint();
  return true;
}

async function scheduleAutoPrint() {
  if (autoPrintScheduled) return;
  autoPrintScheduled = true;

  try {
    if (document.fonts?.ready) await document.fonts.ready;
  } catch (error) {
    console.warn('Não foi possível aguardar as fontes.', error);
  }

  const images = [...document.images];
  await Promise.all(images.map(image => {
    if (image.complete) return Promise.resolve();
    return new Promise(resolve => {
      image.addEventListener('load', resolve, { once: true });
      image.addEventListener('error', resolve, { once: true });
    });
  }));

  window.setTimeout(() => window.print(), 350);
}

function tryLocalStorageFallback() {
  if (rendered) return;
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      const units = JSON.parse(saved);
      if (Array.isArray(units) && units.length) {
        buildReport({ units, generatedAt: new Date().toISOString() });
        return;
      }
    }
  } catch (error) {
    console.warn('Fallback local do relatório indisponível.', error);
  }

  if (!rendered) document.querySelector('#report-error').hidden = false;
}

window.addEventListener('message', event => {
  if (event.data?.type !== 'posicao-campo-report-data') return;
  const built = buildReport(event.data.payload);
  if (built && window.opener) {
    window.opener.postMessage({ type: 'posicao-campo-report-received' }, '*');
  }
});

document.querySelector('#print-now').addEventListener('click', () => {
  if (rendered) window.print();
});

document.querySelector('#close-report').addEventListener('click', () => window.close());

if (window.opener) {
  window.opener.postMessage({ type: 'posicao-campo-report-ready' }, '*');
}

window.setTimeout(tryLocalStorageFallback, 1800);
