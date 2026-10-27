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
  const marks = buckets.map((b, i) => `<circle cx="${x(i)}" cy="${y(b.count)}" r="4"><title>${b.label}: ${b.count} uploads</title></circle>${visibleLabels.includes(i) ? `<text x="${x(i)}" y="235" text-anchor="${i === 0 ? 'start' : i === buckets.length - 1 ? 'end' : 'middle'}">${b.label}</text>` : ''}`).join('');
  document.querySelector('#uploadChart').innerHTML = `<svg viewBox="0 0 ${width} 260" role="img" aria-labelledby="uploadChartTitle uploadChartDescription"><title id="uploadChartTitle">Uploads by ${mode}</title><desc id="uploadChartDescription">${buckets.map(b => `${b.label}: ${b.count}`).join('; ')}</desc>${gradient}${grid}${area}<polyline points="${points}"/>${marks}</svg>`;
  document.querySelector('#uploadChartSummary').textContent = `${total} images · ${buckets[0].label} – ${buckets[buckets.length - 1].label}`;
  document.querySelector('#uploadChartTable').innerHTML = `<table><caption>Upload counts by ${mode}</caption><thead><tr><th>Period</th><th>Images</th></tr></thead><tbody>${buckets.map(b => `<tr><td>${b.label}</td><td>${b.count}</td></tr>`).join('')}</tbody></table>`;
}
