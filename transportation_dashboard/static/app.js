const escapeHtml = value => String(value ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');
const $ = (selector) => document.querySelector(selector);
const months = ['Aug','Sep','Oct','Nov','Dec','Jan','Feb','Mar','Apr','May','Jun','Jul'];
const RISKS = ['Low Risk','Moderate Risk','High Risk'];
const HAZARDS = ['Alligator Crack','Longitudinal Crack','Transverse Crack','Pothole'];
const menuToggle = document.querySelector('#menuToggle');
const sidebar = document.querySelector('#sidebar');
const uploadPage = document.querySelector('#uploadPage');
const mainContent = document.querySelector('.content');
function updatePageTab() {
  const upload = window.location.hash === '#upload';
  if (uploadPage) uploadPage.style.display = upload ? 'block' : 'none';
  if (mainContent) mainContent.style.display = upload ? 'none' : 'grid';
  document.querySelectorAll('.side-nav a').forEach(link => link.classList.toggle('active', upload ? link.getAttribute('href') === '#upload' : link.getAttribute('href') === '#overview'));
}
window.addEventListener('hashchange', updatePageTab); updatePageTab();
menuToggle?.addEventListener('click', () => {
  const isOpen = sidebar.classList.toggle('is-open');
  menuToggle.setAttribute('aria-expanded', String(isOpen));
});
const imageInput = document.querySelector('#imageInput');
const imageSubmit = document.querySelector('#imageSubmit');
let selectedImages = [];
imageInput?.addEventListener('change', () => { selectedImages = [...imageInput.files]; imageSubmit.disabled = !selectedImages.length; $('#imageStatus').textContent = selectedImages.length ? `${selectedImages.length} image(s) selected` : 'No images loaded'; });
imageSubmit?.addEventListener('click', async () => { if (!selectedImages.length) return; const body = new FormData(); selectedImages.forEach(file => body.append('files', file)); imageSubmit.disabled = true; $('#imageStatus').textContent = 'Saving images…'; try { const response = await fetch('/api/upload-images', {method:'POST', body}); const result = await response.json(); if (!response.ok) throw new Error(result.errors?.map(e => `${e.name}: ${e.error}`).join('; ') || result.detail || 'Upload failed'); $('#imageStatus').textContent = `Saved ${result.count} image(s) to Supabase. ${result.errors?.length ? result.errors.map(e => `${e.name}: ${e.error}`).join('; ') : 'Awaiting model analysis.'}`; selectedImages = []; imageInput.value = ''; await loadAssets(); } catch (error) { $('#imageStatus').textContent = error.message || 'Upload failed'; imageSubmit.disabled = false; } });
let allAssets = [];
function renderAssets() { const filter = $('#assetFilter').value; const visible = allAssets.filter(asset => filter === 'all' || asset.class_name === filter); $('#assetGallery').innerHTML = visible.length ? visible.map(asset => `<figure><img src="${asset.url}" alt="${escapeHtml(asset.name)}"><figcaption><b>${asset.id}</b><span>${escapeHtml(asset.class_name)}</span></figcaption></figure>`).join('') : '<p class="empty-assets">No images match this filter.</p>'; renderAssetTable(visible); renderAssetAnalytics(); }
function ensureAssetExtras() { if ($('#assetTable')) return; $('#assetGallery').insertAdjacentHTML('afterend','<div id="assetAnalytics" class="asset-analytics"><div><h3>Risk conditions</h3><div id="riskBars"></div></div><div><h3>Hazard types</h3><div id="hazardBars"></div></div><div><h3>Risk score sequence</h3><svg id="scoreChart" viewBox="0 0 260 90"></svg></div></div><div id="assetTable" class="asset-table"></div>'); }
function renderAssetTable(rows) { ensureAssetExtras(); const query = ($('#assetSearch')?.value || '').trim().toLowerCase(); const filtered = query ? rows.filter(a => [a.id, a.upload_date, a.class_name, a.predicted_hazard_type, a.predicted_risk_condition, a.expert_hazard_type, a.expert_risk_condition, a.expert_comments].some(v => String(v ?? '').toLowerCase().includes(query))) : rows; $('#assetTable').innerHTML = `<div class="asset-table-head"><h3>Hazard records</h3><label class="asset-search"><span>Search</span><input id="assetSearch" type="search" placeholder="Search ID, hazard, risk…" value="${escapeHtml(query)}"></label></div><div class="table-wrap"><table><thead><tr><th>ID <button type="button" class="sort-btn" data-sort="0" title="Sort by ID">↕</button></th><th>Uploaded <button type="button" class="sort-btn" data-sort="1" title="Sort by upload date">↕</button></th><th>Hazard <button type="button" class="sort-btn" data-sort="2" title="Sort by hazard">↕</button></th><th>Risk <button type="button" class="sort-btn" data-sort="3" title="Sort by risk">↕</button></th><th>Score <button type="button" class="sort-btn" data-sort="4" title="Sort by score">↕</button></th><th>Expert <button type="button" class="sort-btn" data-sort="5" title="Sort by expert status">↕</button></th><th>View</th></tr></thead><tbody>${filtered.map(a=>`<tr class="risk-${(a.expert_risk_condition||a.predicted_risk_condition||'').toLowerCase().replaceAll(' ','-')}"><td>${a.id}</td><td>${a.upload_date ? new Date(a.upload_date).toLocaleString() : '—'}</td><td>${escapeHtml(a.expert_hazard_type||a.predicted_hazard_type||a.class_name)}</td><td>${escapeHtml(a.expert_risk_condition||a.predicted_risk_condition||(a.legacy_demo ? 'Demo: '+a.legacy_demo.predicted_risk_condition : '—'))}</td><td>${escapeHtml(a.expert_risk_score??a.predicted_risk_score??(a.legacy_demo ? 'Demo: '+a.legacy_demo.predicted_risk_score : '—'))}</td><td>${a.expert_annotated?'Reviewed':'Pending'}</td><td><button type="button" data-asset-id="${a.id}" class="view-asset">View</button></td></tr>`).join('') || '<tr><td colspan="7" class="empty-assets">No matching records.</td></tr>'}</tbody></table></div>`; $('#assetSearch')?.addEventListener('input', e => { const q=e.target.value.trim().toLowerCase(); document.querySelectorAll('#assetTable tbody tr').forEach(row => { row.style.display = !q || row.textContent.toLowerCase().includes(q) ? '' : 'none'; }); }); }
function renderAssetAnalytics() { const riskCounts = Object.fromEntries(RISKS.map(r=>[r,allAssets.filter(a=>(a.predicted_risk_condition||'')===r).length])); $('#riskBars').innerHTML=Object.entries(riskCounts).map(([k,v])=>`<p><span>${k}</span><b style="width:${Math.max(v*24,2)}px">${v}</b></p>`).join(''); const hazardCounts=Object.fromEntries(HAZARDS.map(h=>[h,allAssets.filter(a=>(a.predicted_hazard_type||a.class_name)===h).length])); $('#hazardBars').innerHTML=Object.entries(hazardCounts).map(([k,v])=>`<p><span>${k}</span><b style="width:${Math.max(v*24,2)}px">${v}</b></p>`).join(''); }
let assetsLoading = false;
async function loadAssets() { if (assetsLoading) return; assetsLoading = true; const selectedFilter = $('#assetFilter').value; try { const data = await fetch('/api/assets').then(response => response.json()); allAssets = data.assets; const classes = [...new Set(allAssets.map(a => a.class_name))].sort(); $('#assetTotal').textContent = allAssets.length; $('#classA').textContent = new Set(allAssets.map(a => a.predicted_hazard_type).filter(Boolean)).size; $('#classB').textContent = allAssets.length; $('#classOther').textContent = allAssets.filter(a => !a.predicted_hazard_type).length; $('#assetFilter').innerHTML = '<option value="all">All classes</option>' + classes.map(name => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join(''); if (classes.includes(selectedFilter)) $('#assetFilter').value = selectedFilter; renderAssets(); } catch { $('#imageStatus').textContent = 'Could not load records. Check the server connection.'; } finally { assetsLoading = false; } }
$('#assetFilter')?.addEventListener('change', renderAssets); loadAssets();
// Keep latest saved records visible without requiring a page reload.
setInterval(() => { if (!document.hidden && window.location.hash === '#upload') loadAssets(); }, 30000);
let selectedAsset = null;
document.addEventListener('click', event => { const button = event.target.closest('.view-asset'); if (button) window.openImageById(button.dataset.assetId); });
window.openImageById = id => { const asset = allAssets.find(item => item.id === id); if (!asset) return; selectedAsset = asset; $('#modalImage').src = asset.url; $('#modalName').textContent = asset.name; $('#modalClass').textContent = asset.class_name; $('#imageModal').classList.add('open'); $('#imageModal').setAttribute('aria-hidden','false'); };
$('#assetGallery')?.addEventListener('click', event => { const image = event.target.closest('img'); if (!image) return; selectedAsset = allAssets.find(asset => asset.url === image.getAttribute('src')); if (!selectedAsset) return; $('#modalImage').src = selectedAsset.url; $('#modalName').textContent = selectedAsset.name; $('#modalClass').textContent = selectedAsset.class_name; $('#imageModal').classList.add('open'); $('#imageModal').setAttribute('aria-hidden','false'); });
function closeModal() { $('#imageModal')?.classList.remove('open'); $('#imageModal')?.setAttribute('aria-hidden','true'); selectedAsset = null; }
$('#modalClose')?.addEventListener('click', closeModal);
$('#imageModal')?.addEventListener('click', event => { if (event.target.id === 'imageModal') closeModal(); });
$('#modalDelete')?.addEventListener('click', async () => { if (!selectedAsset) return; if (!window.confirm(`Delete ${selectedAsset.name}?`)) return; const response = await fetch(`/api/assets/${encodeURIComponent(selectedAsset.id)}`, {method:'DELETE'}); if (response.ok) { closeModal(); $('#imageStatus').textContent = `Deleted ${selectedAsset.name}`; await loadAssets(); } else { $('#imageStatus').textContent = 'Delete failed'; } });
const tip = document.createElement('div'); tip.className = 'chart-tip'; document.body.append(tip);
function addHover(el, text) { el.addEventListener('mouseenter', e => { tip.textContent = text; tip.style.display='block'; }); el.addEventListener('mousemove', e => { tip.style.left=`${e.clientX+12}px`; tip.style.top=`${e.clientY+12}px`; }); el.addEventListener('mouseleave', () => { tip.style.display='none'; }); }

function linePath(values) {
  const x = i => 42 + (i * 49); const y = value => 160 - ((value - 40) * 0.88);
  return values.map((value, i) => `${i ? 'L' : 'M'} ${x(i)} ${y(value)}`).join(' ');
}
function drawCharts() {
  const series = [
    ['#0c8d95',[142,118,64,79,45,97,60,72,104,66,75,78]],
    ['#d64c4f',[116,128,94,125,50,77,71,69,109,70,72,77]],
    ['#d8ba55',[124,98,77,103,53,81,101,75,116,73,71,77]],
    ['#35bfca',[129,109,69,84,51,70,85,65,108,63,72,76]]
  ];
  $('#profitLines').innerHTML = series.map(([color, values]) => `<path d="${linePath(values)}" stroke="${color}"/>`).join('');
  [...document.querySelectorAll('#profitLines path')].forEach((line,i) => addHover(line, `${['USA','France','Germany','Switzerland'][i]} · hover points for monthly trend`));
  $('#months').innerHTML = months.map(m => `<span>${m}<br>2026</span>`).join('');
  $('#shortMonths').innerHTML = months.map(m => `<span>${m}</span>`).join('');
  const routes = [690,735,645,640,700,698,650,592,540,530,548,642];
  const times = [7.2,8.7,6.8,8.1,7.3,8,7.2,7.5,5.3,6.3,6.6,8.6];
  const x = i => 51 + i * 36.2; const y = value => 178 - (value / 800 * 150);
  const bars = routes.map((route,i) => `<rect x="${x(i)}" y="${y(route)}" width="13" height="${178-y(route)}" fill="#0c8d95"/>`).join('');
  const path = times.map((value,i) => `${i?'L':'M'} ${x(i)+6} ${180-value*16}`).join(' ');
  $('#deliveryMarks').innerHTML = `${bars}<path d="${path}" fill="none" stroke="#d64c4f" stroke-width="2" stroke-dasharray="4 3"/>${times.map((value,i)=>`<circle cx="${x(i)+6}" cy="${180-value*16}" r="2.5" fill="#d64c4f" data-hover="${months[i]} · ${value}h"/>`).join('')}`;
  [...document.querySelectorAll('#deliveryMarks rect')].forEach((bar,i) => addHover(bar, `${months[i]} · ${routes[i]} km`));
  [...document.querySelectorAll('#deliveryMarks circle')].forEach(circle => addHover(circle, circle.dataset.hover));
  renderMarks([{id:'V-204',marks:82},{id:'V-118',marks:66},{id:'V-307',marks:74},{id:'V-091',marks:91}]);
}

function renderMarks(rows) {
  const svg=$('#marksChart'); const width=600, height=170, max=Math.max(...rows.map(r=>r.marks),100); const step=width/Math.max(rows.length,1);
  svg.innerHTML=`<line class="marks-grid" x1="30" y1="145" x2="590" y2="145"/>${rows.map((r,i)=>{const h=(r.marks/max)*120;const x=40+i*step;return `<rect class="marks-bar" x="${x}" y="${145-h}" width="${Math.max(18,step-12)}" height="${h}" data-hover="${r.id} · ${r.marks} marks"/><text x="${x+4}" y="160" font-size="10">${r.id}</text>`}).join('')}`;
  svg.querySelectorAll('.marks-bar').forEach(bar=>addHover(bar,bar.dataset.hover));
  // Make the uploaded data visible in the main trend plot as well.
  const trend = rows.slice(0, 12).map(row => Math.max(0, Math.min(100, row.marks)));
  $('#profitLines').innerHTML = `<path d="${linePath(trend)}" stroke="#0c8d95"/>`;
  addHover($('#profitLines path'), `Uploaded marks · ${rows.length} rows`);
  const chartRows = rows.slice(0, 12), barWidth = 440 / Math.max(chartRows.length, 1);
  const uploadedBars = chartRows.map((row, i) => {
    const height = Math.max(2, Math.min(150, row.marks / 100 * 150));
    const x = 45 + i * barWidth;
    return `<rect x="${x}" y="${178 - height}" width="${Math.max(10, barWidth - 7)}" height="${height}" fill="#0c8d95" data-upload-hover="${row.id} · ${row.marks} marks"/><text x="${x}" y="198" font-size="9">${row.id}</text>`;
  }).join('');
  $('#deliveryMarks').innerHTML = uploadedBars;
  $('#deliveryMarks').querySelectorAll('rect').forEach(bar => addHover(bar, bar.dataset.uploadHover));
}
// Select first, then parse only when the user presses Submit file.
let selectedCsvFile = null;
$('#csvInput').addEventListener('change', event => {
  selectedCsvFile = event.target.files[0] || null;
  $('#csvSubmit').disabled = !selectedCsvFile;
  $('#csvStatus').textContent = selectedCsvFile ? `Selected: ${selectedCsvFile.name}` : 'No file loaded';
});
$('#csvSubmit').addEventListener('click', () => {
  const file = selectedCsvFile; if (!file) return;
  $('#csvStatus').textContent = `Reading ${file.name}…`;
  const reader = new FileReader();
  reader.onload = () => {
    const lines = String(reader.result).replace(/^\uFEFF/, '').trim().split(/\r?\n/).filter(Boolean);
    if (!lines.length) { $('#csvStatus').textContent = 'The file is empty'; return; }
    const delimiter = lines[0].includes('\t') ? '\t' : lines[0].includes(';') ? ';' : ',';
    let cells = lines.map(line => line.split(delimiter).map(value => value.trim()));
    const first = cells[0].map(value => value.toLowerCase());
    if (first.includes('id') && first.includes('marks')) {
      const idIndex = first.indexOf('id'), marksIndex = first.indexOf('marks');
      cells = cells.slice(1).map(row => ({id: row[idIndex], marks: Number(row[marksIndex])}));
    } else {
      cells = cells.map(row => ({id: row[0], marks: Number(row[1])}));
    }
    const rows = cells.filter(row => row.id && Number.isFinite(row.marks));
    if (!rows.length) { $('#csvStatus').textContent = 'No numeric id/marks rows found'; return; }
    renderMarks(rows);
    $('#csvStatus').textContent = `Loaded ${rows.length} rows from ${file.name}`;
  };
  reader.readAsText(file);
});

async function load() {
  const data = await fetch('/api/overview').then(response => response.json());
  $('#vehicles').textContent = data.metrics.active_vehicles;
  $('#otp').textContent = `${Math.round(data.metrics.on_time_rate)}%`;
  $('#alertsCount').textContent = data.metrics.open_alerts;
  $('#impact').textContent = data.metrics.estimated_impacts;
  $('#updated').textContent = `Updated ${new Date(data.updated_at).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}`;
}

$('#riskForm').addEventListener('submit', async (event) => {
  event.preventDefault(); const fd = new FormData(event.currentTarget); const payload = Object.fromEntries(fd.entries());
  ['delay_minutes','speed_kph','vehicle_age_years','weather_risk'].forEach(key => payload[key] = Number(payload[key]));
  const output = $('#prediction'); output.textContent = 'Scoring trip…';
  try { const result = await fetch('/api/predict',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}).then(response => response.json());
    output.textContent = `${result.risk_band.toUpperCase()} RISK · ${Math.round(result.risk_score * 100)}% · ${result.model_name}`;
  } catch { output.textContent = 'Model service unavailable.'; }
});
drawCharts();
load().catch(() => { $('#updated').textContent = 'Preview mode · start FastAPI for live data'; });
fetch('/api/marks').then(response => response.json()).then(data => {
  if (data.rows?.length) { renderMarks(data.rows); $('#csvStatus').textContent = `Loaded ${data.rows.length} rows from ${data.source}`; }
}).catch(() => {});

// Centered preview magnifier.
document.addEventListener('DOMContentLoaded', function(){var modal=document.querySelector('#imageModal'),img=document.querySelector('#modalImage');if(!modal||!img)return;var zoom=document.querySelector('#modalZoom');if(!zoom){zoom=document.createElement('div');zoom.id='modalZoom';img.parentElement.appendChild(zoom);}img.addEventListener('mousemove',function(e){var r=img.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom){zoom.style.display='none';return;}zoom.style.display='block';zoom.style.backgroundImage='url("'+img.src+'")';zoom.style.backgroundPosition=((e.clientX-r.left)/r.width*100)+'% '+((e.clientY-r.top)/r.height*100)+'%';});img.addEventListener('mouseleave',function(){zoom.style.display='none';});});
const sortDirections = {};
document.addEventListener('click', event => {
  const button = event.target.closest('.sort-btn');
  if (!button) return;
  const column = Number(button.dataset.sort);
  const direction = sortDirections[column] = -(sortDirections[column] || 1);
  const body = document.querySelector('#assetTable tbody');
  if (!body) return;
  [...body.rows].sort((a,b) => {
    const av = a.cells[column]?.textContent.trim() || '', bv = b.cells[column]?.textContent.trim() || '';
    const an = Number(av.replace(/[^0-9.-]/g,'')), bn = Number(bv.replace(/[^0-9.-]/g,''));
    const riskOrder={'Low Risk':1,'Moderate Risk':2,'High Risk':3}; const numeric = value => /^-?\d+(?:\.\d+)?$/.test(value); const result = column===3 ? (riskOrder[av]||99)-(riskOrder[bv]||99) : (numeric(av) && numeric(bv) ? an-bn : av.localeCompare(bv, undefined, {sensitivity:'base'}));
    return result * direction;
  }).forEach(row => body.appendChild(row));
  button.textContent = direction === 1 ? '↑' : '↓';
});
