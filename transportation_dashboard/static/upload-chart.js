'use strict';
// Calendar buckets use Central Time, independent of the browser's timezone.
const uploadDateFormatter = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/Chicago', year: 'numeric', month: 'numeric'
});
function uploadCalendarDate(value) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  const parts = Object.fromEntries(uploadDateFormatter.formatToParts(date).map(p => [p.type, p.value]));
  return {year: Number(parts.year), month: Number(parts.month)};
}
// Fixed windows include the current period. Empty buckets are real zero counts.
function groupUploadPeriods(records, mode, now = new Date()) {
  const calendar = uploadCalendarDate(now);
  const perYear = mode === 'year' ? 1 : mode === 'quarter' ? 4 : 12;
  const index = ({year, month}) => year * perYear + Math.floor((month - 1) / (12 / perYear));
  const end = index(calendar);
  const length = mode === 'month' ? 12 : mode === 'quarter' ? 8 : 5;
  const buckets = Array.from({length}, (_, i) => {
    const key = end - length + 1 + i;
    const year = Math.floor(key / perYear);
    const period = key % perYear;
    const label = mode === 'year' ? String(year) : mode === 'quarter' ? `Q${period + 1} ${year}` : `${['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][period]} ${year}`;
    return {key, label, count: 0};
  });
  for (const record of records) {
    const date = uploadCalendarDate(record.upload_date);
    if (!date) continue;
    const offset = index(date) - buckets[0].key;
    if (offset >= 0 && offset < buckets.length) buckets[offset].count++;
  }
  return buckets;
}
function renderUploadChart(records) {
  const mode = document.querySelector('#uploadPeriod [aria-pressed="true"]').dataset.period;
  const buckets = groupUploadPeriods(records, mode);
  const total = buckets.reduce((sum, b) => sum + b.count, 0);
  const max = Math.max(1, ...buckets.map(b => b.count));
  const ceiling = Math.ceil(max / 4) * 4;
  const width = Math.max(300, Math.min(900, document.querySelector('#uploadChart').clientWidth || 600));
  const right = width - 24;
  const x = i => 42 + i * (right - 42) / (buckets.length - 1);
  const labelStep = Math.max(1, Math.ceil(buckets.length * 72 / (right - 42))); 
  const y = count => 210 - count * 172 / ceiling;
  const grid = Array.from({length: 5}, (_, i) => {
    const value = ceiling * i / 4;
    return `<line x1="42" x2="${right}" y1="${y(value)}" y2="${y(value)}" class="upload-gridline"/><text x="31" y="${y(value) + 4}" text-anchor="end">${value}</text>`;
  }).join('');
  const points = buckets.map((b, i) => `${x(i)},${y(b.count)}`).join(' ');
  // Close the area along the zero baseline, beneath the line and markers.
  const area = `<polygon points="${x(0)},210 ${points} ${x(buckets.length - 1)},210" fill="url(#uploadAreaGradient)"/>`;
  const gradient = '<defs><linearGradient id="uploadAreaGradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#22786d" stop-opacity="0.24"/><stop offset="100%" stop-color="#22786d" stop-opacity="0.03"/></linearGradient></defs>';
  const visibleLabels = buckets.map((_,i)=>i).filter(i=>i%labelStep===0 || i===buckets.length-1);
  // Keep the last label, but suppress a nearby penultimate label.
  if(visibleLabels.length>2 && x(visibleLabels.at(-1))-x(visibleLabels.at(-2))<70) visibleLabels.splice(-2,1);
  const marks = buckets.map((b, i) => `<circle cx="${x(i)}" cy="${y(b.count)}" r="4"/>${visibleLabels.includes(i) ? `<text x="${x(i)}" y="235" text-anchor="${i === 0 ? 'start' : i === buckets.length - 1 ? 'end' : 'middle'}">${b.label}</text>` : ''}`).join('');
  // Full-height targets make every period easy to hover, including zero counts.
  const targets = buckets.map((b, i) => {
    const left = i === 0 ? 32 : (x(i - 1) + x(i)) / 2;
    const end = i === buckets.length - 1 ? width - 14 : (x(i) + x(i + 1)) / 2;
    return `<rect class="upload-hit" data-index="${i}" x="${left}" y="28" width="${end-left}" height="188" tabindex="0" role="button" aria-label="${b.label}: ${b.count} ${b.count===1?'upload':'uploads'}"/>`;
  }).join('');
  const chart = document.querySelector('#uploadChart');
  chart.innerHTML = `<svg viewBox="0 0 ${width} 260" role="group" aria-labelledby="uploadChartTitle uploadChartDescription"><title id="uploadChartTitle">Uploads by ${mode}</title><desc id="uploadChartDescription">Hover, tap, or focus a period to see its upload count. ${buckets.map(b => `${b.label}: ${b.count}`).join('; ')}</desc>${gradient}${grid}${area}<polyline points="${points}"/>${marks}${targets}<g class="upload-tooltip" visibility="hidden" pointer-events="none"><line class="upload-guide" y1="28" y2="210"/><circle class="upload-active" r="6"/><g class="upload-tooltip-box"><rect width="132" height="49" rx="7"/><text class="upload-tooltip-period" x="12" y="19"></text><text class="upload-tooltip-count" x="12" y="37"></text></g></g></svg>`;
  const tooltip = chart.querySelector('.upload-tooltip');
  const show = index => {
    const bucket = buckets[index];
    const px = x(index), py = y(bucket.count);
    const boxX = Math.max(4, Math.min(width - 136, px - 66));
    const boxY = py < 88 ? py + 14 : py - 63;
    tooltip.setAttribute('visibility', 'visible');
    const guide = tooltip.querySelector('.upload-guide');
    guide.setAttribute('x1', px); guide.setAttribute('x2', px);
    const marker = tooltip.querySelector('.upload-active');
    marker.setAttribute('cx', px); marker.setAttribute('cy', py);
    tooltip.querySelector('.upload-tooltip-box').setAttribute('transform', `translate(${boxX} ${boxY})`);
    tooltip.querySelector('.upload-tooltip-period').textContent = bucket.label;
    tooltip.querySelector('.upload-tooltip-count').textContent = `${bucket.count} ${bucket.count === 1 ? 'upload' : 'uploads'}`;
  };
  const hide = () => tooltip.setAttribute('visibility', 'hidden');
  chart.querySelectorAll('.upload-hit').forEach(target => {
    const reveal = () => show(Number(target.dataset.index));
    target.addEventListener('pointerenter', reveal);
    target.addEventListener('focus', reveal);
    target.addEventListener('click', reveal);
    target.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {event.preventDefault(); reveal();}
    });
  });
  chart.onpointerleave = () => {if (!chart.contains(document.activeElement)) hide();};
  chart.onfocusout = event => {if (!chart.contains(event.relatedTarget)) hide();};
  chart.onkeydown = event => {if (event.key === 'Escape') hide();};
  document.querySelector('#uploadChartSummary').textContent = `${total} images · ${buckets[0].label} – ${buckets[buckets.length - 1].label}`;
  document.querySelector('#uploadChartTable').innerHTML = `<table><caption>Upload counts by ${mode}</caption><thead><tr><th>Period</th><th>Images</th></tr></thead><tbody>${buckets.map(b => `<tr><td>${b.label}</td><td>${b.count}</td></tr>`).join('')}</tbody></table>`;
}
