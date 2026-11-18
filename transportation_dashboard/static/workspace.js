'use strict';
const $ = selector => document.querySelector(selector);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const statusLabels = {not_analyzed:'No saved analysis', queued:'Queued', processing:'Analyzing…', completed:'Completed', failed:'Failed'};
let analyzingId = null;
let detailViewVersion = 0;
let assets = [], loaded = false, loading = false, selectedId = null, files = [], uploading = false, returnFocus = null;
// Remember the data currently displayed.
let lastAssetsSnapshot = null;
let refreshAgain = false;
const dateText = value => value ? new Date(value).toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric',timeZone:'America/Chicago'}) : 'Unknown date';
const fullDate = value => value ? new Date(value).toLocaleString(undefined,{timeZone:'America/Chicago'}) : 'Not recorded';
const byteText = value => value == null ? 'Not recorded' : value < 1048576 ? `${(value/1024).toFixed(0)} KB` : `${(value/1048576).toFixed(1)} MB`;
const shortId = a => a.legacy_demo ? `Legacy #${a.legacy_demo.id}` : `ID ${a.id.slice(0,8)}`;
const badge = (text, type='') => `<span class="badge ${escapeHtml(type)}">${escapeHtml(text)}</span>`;
const analysisBadge = a => badge(statusLabels[a.analysis_status] || 'Unknown status',a.analysis_status);
// Prefer expert risk, then model risk; historical values remain explicitly marked as demo.
// Moderate is the legacy/database name for the Medium category. Missing risk is never inferred from a score.
function riskInfo(a){
 const candidates=[[a.expert_risk_condition,'Expert'],[a.predicted_risk_condition,'Model'],[a.analysis_status==='not_analyzed'?a.legacy_demo?.predicted_risk_condition:null,'Demo']];
 for(const [value,source] of candidates){
  const key=String(value||'').trim().toLowerCase().replace(/\s+risk$/, '');
  const level={low:'Low',medium:'Medium',moderate:'Medium',high:'High'}[key];
  if(level)return {level,source};
 }
 return null;
}
function riskBadge(a){const risk=riskInfo(a);return risk?badge(`${risk.level} risk${risk.source==='Demo'?' · Demo':risk.source==='Expert'?' · Expert':''}`,`risk-${risk.level.toLowerCase()}`):badge('Risk not assessed');}
const hazard = a => a.expert_hazard_type || a.predicted_hazard_type || (a.analysis_status==='completed'?'No distress predicted':a.analysis_status==='failed'?'Analysis failed':['queued','processing'].includes(a.analysis_status)?'Awaiting results':a.legacy_demo ? a.legacy_demo.predicted_hazard_type : 'Awaiting analysis');
// Stable display reference; original filenames and storage objects are preserved.
const referenceDate = new Intl.DateTimeFormat('en-US', {
 timeZone: 'America/Chicago', year: 'numeric', month: '2-digit', day: '2-digit'
});
function imageReference(asset) {
 const date = new Date(asset.upload_date);
 let stamp = 'UNDATED';
 if (asset.upload_date && !Number.isNaN(date.getTime())) {
  const parts = Object.fromEntries(referenceDate.formatToParts(date).map(part => [part.type, part.value]));
  stamp = `${parts.year}${parts.month}${parts.day}`;
 }
 return `IMG-${stamp}-${asset.id.split('-')[0].toUpperCase()}`;
}
const thumb = a => `<img class="thumb" src="${escapeHtml(a.url)}" alt="" loading="lazy">`;
function pageName(){const p=location.hash.slice(1);return ['overview','inspections','upload','reports'].includes(p)?p:'overview';}
function navigate(){const page=pageName();document.querySelectorAll('.page').forEach(el=>el.hidden=el.id!==`${page}Page`);document.querySelectorAll('nav [data-page]').forEach(el=>{const active=el.dataset.page===page;el.classList.toggle('active',active);if(active)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});$('#breadcrumbPage').textContent={overview:'Overview',inspections:'Inspections',upload:'Upload images',reports:'Reports'}[page];document.title=`${$('#breadcrumbPage').textContent} · Road distress dashboard`;window.scrollTo(0,0);if(page==='overview'&&loaded){renderUploadChart(assets);renderCrackingChart(assets);}}
window.addEventListener('hashchange',navigate);navigate();
function centralDate(date){
 const parts=Object.fromEntries(new Intl.DateTimeFormat('en-US',{timeZone:'America/Chicago',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(date).map(p=>[p.type,p.value]));
 return `${parts.year}-${parts.month}-${parts.day}`;
}
$('#reportTo').value=centralDate(new Date());
$('#reportFrom').value=centralDate(new Date(Date.now()-29*86400000));
$('#reportForm').addEventListener('submit',event=>{
 event.preventDefault();
 const start=$('#reportFrom').value,end=$('#reportTo').value,status=$('#reportStatus');
 if(!start||!end||end<start){status.textContent='Choose a valid start and end date.';return;}
 const url=`/api/reports/analysis?from_date=${encodeURIComponent(start)}&to_date=${encodeURIComponent(end)}`;
 status.textContent='Opening the printable report in a new tab…';
 window.open(url,'_blank','noopener');
});
function error(message){$('#pageError').hidden=!message;$('#pageError').textContent=message||'';}
async function refresh() {
  // Prevent two requests from running at the same time.
  if (loading) { refreshAgain = true; return; }

  loading = true;
  $('#refreshButton').disabled = true;

  try {
    const response = await fetch('/api/assets');
    const data = await response.json();

    if (!response.ok) {
      throw new Error(
        data.detail || 'Could not load inspection records.'
      );
    }

    // Sort consistently before comparing old and new data.
    const nextAssets = [...data.assets].sort((a, b) => {
      const dateDifference =
        new Date(b.upload_date) - new Date(a.upload_date);

      return dateDifference || a.id.localeCompare(b.id);
    });

    // Convert the records into a string we can compare.
    const nextSnapshot = JSON.stringify(nextAssets);
    const hasChanged = nextSnapshot !== lastAssetsSnapshot;

    const previousDetail = assets.find(a => a.id === selectedId);
    assets = nextAssets;
    loaded = true;

    error('');
    $('#connection').className = 'connection ready';
    $('#connection').textContent = 'Storage connected';

    $('#lastUpdated').textContent =
      `Updated ${new Date().toLocaleTimeString(undefined, {
        hour: '2-digit',
        minute: '2-digit'
      })}`;

    // Leave existing thumbnails alone when nothing changed.
    if (hasChanged) {
      render();
      lastAssetsSnapshot = nextSnapshot;
      const currentDetail = assets.find(a => a.id === selectedId);
      if (currentDetail && $('#detailsDialog').open && JSON.stringify(currentDetail) !== JSON.stringify(previousDetail)) openDetails(selectedId, returnFocus, true);
    }
  } catch (e) {
    error(
      `${e.message} ${
        loaded
          ? 'Showing the last loaded records.'
          : 'Check that the local server is running.'
      }`
    );

    $('#connection').className = 'connection failed';
    $('#connection').textContent = 'Connection unavailable';

    // Keep existing records visible if a later refresh fails.
    if (!loaded) {
      $('#recentRecords').innerHTML =
        '<div class="empty"><strong>Records unavailable</strong>' +
        'Use the refresh button to try again.</div>';

      $('#recordsList').innerHTML =
        '<div class="empty">Could not load records.</div>';
    }
  } finally {
    // Run whether the request succeeds or fails.
    loading = false;
    $('#refreshButton').disabled = false;
    // An upload/retry refresh must not be dropped behind an in-flight poll.
    if (refreshAgain) { refreshAgain = false; refresh(); }
  }
}
function updateWithExistingThumbnails(selector, html) {
  const container = $(selector);

  // Store existing images by their source URL.
  // A URL can appear twice: desktop table and mobile card.
  const existingImages = new Map();

  container.querySelectorAll('img.thumb').forEach(image => {
    const source = image.getAttribute('src');

    if (!existingImages.has(source)) {
      existingImages.set(source, []);
    }

    existingImages.get(source).push(image);
  });

  // Prepare the new HTML outside the visible page.
  const template = document.createElement('template');
  template.innerHTML = html;

  // Replace new thumbnail elements with matching old ones.
  template.content.querySelectorAll('img.thumb').forEach(image => {
    const source = image.getAttribute('src');
    const matches = existingImages.get(source);

    if (matches?.length) {
      image.replaceWith(matches.shift());
    }
  });

  // Display updated content, retaining existing image elements.
  container.replaceChildren(template.content);
}
// Segmented buttons select the chart grouping without fetching records again.
$('#uploadPeriod').addEventListener('click', event => {
 const button = event.target.closest('button[data-period]');
 if (!button) return;
 $('#uploadPeriod').querySelectorAll('button').forEach(item => {
  item.setAttribute('aria-pressed', String(item === button));
 });
 if (loaded) renderUploadChart(assets);
});
function workspaceIcon(name) {
 const paths={images:'<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1.5"/><path d="m3 16 5-5 4 4 4-6 5 7"/>',clock:'<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',check:'<circle cx="12" cy="12" r="9"/><path d="m7 12 3 3 7-7"/>',review:'<path d="M8 4H5v17h14V4h-3"/><rect x="8" y="2" width="8" height="5" rx="1"/><path d="M8 11h8m-8 4h6"/>'};
 return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${paths[name]}</svg>`;
}
function renderRecentInspections() {
 if(!assets.length){updateWithExistingThumbnails('#recentRecords','<div class="empty"><strong>No inspections yet</strong>Upload an image to start your inspection history.</div>');return;}
 const recent=assets.slice(0,4);
 const desktop=`<table class="recent-table"><thead><tr><th>DATE · CENTRAL TIME</th><th>IMAGE REFERENCE</th><th>ANALYSIS</th><th>DISTRESS</th><th>PREVIEW</th><th><span class="sr-only">Open image</span></th></tr></thead><tbody>${recent.map(a=>`<tr data-id="${a.id}"><td>${dateText(a.upload_date)}<span class="file-sub">${new Date(a.upload_date).toLocaleTimeString(undefined,{timeZone:'America/Chicago',hour:'2-digit',minute:'2-digit'})}</span></td><td><span class="file-title">${escapeHtml(imageReference(a))}</span><span class="file-sub original-name">${escapeHtml(a.name)}</span></td><td>${analysisBadge(a)}</td><td><span class="recent-hazard">${escapeHtml(a.analysis_status==='completed'?hazard(a):a.analysis_status==='failed'?'Analysis failed':'Awaiting results')}</span><span class="file-sub">${a.expert_annotated?'Expert reviewed':'Pending review'}</span></td><td>${thumb(a)}</td><td><button class="icon-button" data-id="${a.id}" aria-label="View ${escapeHtml(imageReference(a))}">›</button></td></tr>`).join('')}</tbody></table>`;
 const mobile=`<div class="recent-mobile">${recent.map(a=>`<button class="recent-row" data-id="${a.id}" aria-label="View ${escapeHtml(imageReference(a))}">${thumb(a)}<span class="recent-text"><span class="file-title">${escapeHtml(imageReference(a))}</span><span class="file-sub">${dateText(a.upload_date)}</span><span class="badge-row">${analysisBadge(a)}</span></span><span class="arrow" aria-hidden="true">›</span></button>`).join('')}</div>`;
 updateWithExistingThumbnails('#recentRecords',desktop+mobile);
}
['crackMode','crackPeriod','crackSource'].forEach(id=>$('#'+id).addEventListener('change',()=>{
 if(id==='crackMode')$('#crackPeriod').replaceChildren();
 if(loaded)renderCrackingChart(assets);
}));
function render(){
 $('#navCount').textContent=assets.length;$('#recordCount').textContent=assets.length;
 const analyzed=assets.filter(a=>a.analysis_status==='completed').length;
 const waiting=assets.filter(a=>!a.analysis_status||a.analysis_status==='not_analyzed').length;
 const reviewPending=assets.filter(a=>a.analysis_status==='completed'&&!a.expert_annotated).length;
 const demoCount=assets.filter(a=>a.legacy_demo).length;
 const stats=[['Total images',assets.length,`${demoCount} historical demo ${demoCount===1?'record':'records'}`,'images'],['Awaiting analysis',waiting+assets.filter(a=>['queued','processing'].includes(a.analysis_status)).length,'Waiting or processing','clock'],['Analyzed',analyzed,'Saved completed runs','check'],['Awaiting review',reviewPending,'Analyzed images not yet reviewed','review']];
 $('#overviewStats').innerHTML=stats.map(([title,value,note,icon])=>`<article class="stat"><span class="metric-icon metric-${icon}" aria-hidden="true">${workspaceIcon(icon)}</span><div class="metric-content"><div class="stat-label">${title}</div><div class="stat-value">${value}</div><p class="stat-note">${note}</p></div></article>`).join('');
 renderRecentInspections();
 const pipeline=[['Not analyzed',waiting,''],['Queued / processing',assets.filter(a=>['queued','processing'].includes(a.analysis_status)).length,'processing'],['Completed',analyzed,'completed'],['Failed',assets.filter(a=>a.analysis_status==='failed').length,'failed']];
 $('#pipeline').innerHTML=pipeline.map(([name,count,type])=>`<div class="pipeline-item"><div class="pipeline-label"><span>${name}</span><strong>${count} ${count===1?'image':'images'}</strong></div><div class="bar-track ${type}"><i style="width:${assets.length?count/assets.length*100:0}%"></i></div></div>`).join('');
 renderRecords();
 renderUploadChart(assets);
 renderCrackingChart(assets);
}
function renderRecords(){
 const query=$('#recordSearch').value.trim().toLowerCase(), status=$('#statusFilter').value, source=$('#sourceFilter').value;
 const filtered=assets.filter(a=>(status==='all'||a.analysis_status===status)&&(source==='all'||(source==='demo'?!!a.legacy_demo:!a.legacy_demo))&&[a.id,a.name,imageReference(a),hazard(a),shortId(a)].some(v=>String(v).toLowerCase().includes(query)));
 const order=$('#sortOrder').value;
 filtered.sort((a,b)=>order==='filename'?imageReference(a).localeCompare(imageReference(b)):order==='oldest'?new Date(a.upload_date)-new Date(b.upload_date):new Date(b.upload_date)-new Date(a.upload_date));
 $('#visibleCount').textContent=`Showing ${filtered.length} of ${assets.length} images`;
 if(!filtered.length){$('#recordsList').innerHTML=`<div class="empty"><strong>${assets.length?'No matching inspections.':'No inspections yet.'}</strong>${assets.length?'Try another search or change your filters.':'Upload an image to create your first record.'}</div>`;return;}
 const hazardCell=a=>`<span class="hazard-cell">${escapeHtml(hazard(a))}</span>${a.legacy_demo&&!a.predicted_hazard_type&&!a.expert_hazard_type?`<br>${badge('Demo label','demo')}`:''}`;
 updateWithExistingThumbnails('#recordsList', `<table class="records-table"><thead><tr><th>IMAGE</th><th>UPLOADED</th><th>HAZARD</th><th>RISK</th><th>ANALYSIS</th><th>REVIEW</th><th><span class="sr-only">View</span></th></tr></thead><tbody>${filtered.map(a=>`<tr data-id="${a.id}"><td><div class="record-file">${thumb(a)}<div><span class="file-title">${escapeHtml(imageReference(a))}</span><span class="file-sub">${shortId(a)}</span></div></div></td><td>${dateText(a.upload_date)}</td><td>${hazardCell(a)}</td><td>${riskBadge(a)}</td><td>${analysisBadge(a)}</td><td>${badge(a.expert_annotated?'Reviewed':'Pending',a.expert_annotated?'reviewed':'')}</td><td><button class="icon-button" data-id="${a.id}" aria-label="View ${escapeHtml(imageReference(a))}">↗</button></td></tr>`).join('')}</tbody></table><div class="mobile-records">${filtered.map(a=>`<button class="mobile-record" data-id="${a.id}">${thumb(a)}<span class="mobile-record-body"><span class="file-title">${escapeHtml(imageReference(a))}</span><span class="file-sub">${dateText(a.upload_date)} · ${shortId(a)}</span><span class="hazard-cell">${escapeHtml(hazard(a))}</span><span class="badge-row">${riskBadge(a)}${analysisBadge(a)}${a.legacy_demo?badge('Demo label','demo'):badge(a.expert_annotated?'Reviewed':'Pending',a.expert_annotated?'reviewed':'')}</span></span><span class="arrow" aria-hidden="true">↗</span></button>`).join('')}</div>`);
}
['recordSearch','statusFilter','sourceFilter','sortOrder'].forEach(id=>$('#'+id).addEventListener(id==='recordSearch'?'input':'change',renderRecords));
$('#refreshButton').addEventListener('click',refresh);
document.addEventListener('click',e=>{const record=e.target.closest('[data-id]');if(record)openDetails(record.dataset.id, e.target.closest('button')||record);});
function openDetails(id,focusTarget,keepView=false){
 detailViewVersion++;
 $('#modelPreview').replaceChildren();
 const a=assets.find(a=>a.id===id);if(!a)return;selectedId=id;returnFocus=focusTarget;$('#detailStatus').textContent='';$('#detailsTitle').textContent=imageReference(a);$('#detailImage').alt=`Road inspection: ${imageReference(a)}`;if(!keepView)$('#detailImage').src=a.url;$('#openOriginal').href=a.url;$('#previewError').hidden=true;$('#detailImage').hidden=false;
 if(!keepView){$('#imageViewport').classList.remove('zoomed');$('#zoomButton').textContent='Zoom in';$('#zoomButton').setAttribute('aria-pressed','false');}
 $('#detailBadges').innerHTML=riskBadge(a)+analysisBadge(a)+(a.legacy_demo?badge('Historical demo','demo'):'')+badge(a.expert_annotated?'Reviewed':'Pending review',a.expert_annotated?'reviewed':'');
 const fields=[['Original file',a.name],['Uploaded',fullDate(a.upload_date)],['Dimensions',a.width&&a.height?`${a.width} × ${a.height} px`:'Not recorded'],['File size',byteText(a.byte_size)],['Format',a.mime_type||'Not recorded'],['Image ID',a.id]];
 $('#detailMetadata').innerHTML=`<dl class="metadata-grid">${fields.map(([k,v])=>`<dt>${k}</dt><dd>${escapeHtml(v)}</dd>`).join('')}</dl>`;
 let results=a.predicted_hazard_type?`<div class="result-line"><span>Hazard</span><strong>${escapeHtml(a.predicted_hazard_type)}</strong></div>${a.confidence!=null?`<div class="result-line"><span>Model confidence</span><strong>${Math.round(a.confidence*100)}%</strong></div>`:''}${a.predicted_risk_condition?`<div class="result-line"><span>Risk</span><strong>${escapeHtml(a.predicted_risk_condition)}</strong></div>`:''}${a.predicted_risk_score!=null?`<div class="result-line"><span>Score</span><strong>${escapeHtml(a.predicted_risk_score)}</strong></div><p>${escapeHtml(a.score_definition||'Score definition not supplied')}</p>`:''}`:`<p>${a.analysis_status==='failed'?'The latest analysis failed. No usable prediction is shown.':a.analysis_status==='processing'?'Analysis is in progress.':a.analysis_status==='queued'?'This image is waiting for analysis.':a.analysis_status==='completed'?'Analysis completed without a hazard label.':'No analysis result has been saved for this image. Select Analyze and save to process it.'}</p>`;
 if(a.legacy_demo){results+=`<div class="demo-note"><strong>Historical demo values</strong>Hazard: ${escapeHtml(a.legacy_demo.predicted_hazard_type)}<br>Risk: ${escapeHtml(a.legacy_demo.predicted_risk_condition)}<br>Score: ${escapeHtml(a.legacy_demo.predicted_risk_score)}<br>These values were randomly assigned by the original template. They are not model predictions.</div>`;}
 if(a.model_result){
  const r=a.model_result;
  const identified=(r.classes||[]).filter(item=>item.label!=='Background');
  if(r.task_type==='detection'){
   results=`<p>${escapeHtml(r.model_name)} · ${escapeHtml(r.device||'CPU')} · ${Number(r.prediction_seconds).toFixed(3)} seconds for prediction</p>`;
   results+=identified.length?identified.map(item=>`<div class="result-line"><strong>${escapeHtml(item.label)}</strong><span>${item.detection_count} ${item.detection_count===1?'box':'boxes'}</span></div>`).join(''):'<p>No detections above the 10% confidence threshold. This does not establish that the road is distress-free.</p>';
   results+=`<p>Boxes are model detections. Confidence is the model's detection score, not severity or overall road risk. This model does not distinguish longitudinal from transverse cracks.</p>`;
   if((r.detections||[]).length){
    results+=`<p><a class="text-link" target="_blank" rel="noopener" href="/api/analysis/${a.analysis_run_id}/detections-preview">Open image with detection boxes ↗</a></p><img src="/api/analysis/${a.analysis_run_id}/detections-preview" alt="Saved YOLO detections outlined on the road image" style="width:100%;border-radius:8px">`;
    results+=r.detections.map(item=>`<div class="result-line"><span>${escapeHtml(item.label)}</span><strong>${(item.confidence*100).toFixed(1)}% confidence</strong></div>`).join('');
   }
  }else{
   results=`<p>${escapeHtml(r.model_name||'Attain SegFormer-B0')} · ${escapeHtml(r.device||'unknown')} · ${Number(r.prediction_seconds).toFixed(3)} seconds for prediction</p>`;
   results+=identified.length?identified.map(item=>`<div class="result-line"><strong>${escapeHtml(item.label)}</strong><span>${(item.pixel_fraction*100).toFixed(2)}% of image pixels</span></div>`).join(''):'<p>No distress pixels predicted. This does not establish that the road is distress-free.</p>';
   results+=`<p>Pixel coverage is not confidence or a condition score. Low/High belongs to the trained class label; overall risk is not assessed. Predictions await expert review.</p>`;
   if(r.artifacts_available!==false)results+=`<p><a class="text-link" target="_blank" rel="noopener" href="/api/analysis/${a.analysis_run_id}/overlay">Open colored overlay ↗</a> · <a class="text-link" target="_blank" rel="noopener" href="/api/analysis/${a.analysis_run_id}/mask">Open class-ID mask ↗</a></p><img src="/api/analysis/${a.analysis_run_id}/overlay" alt="Model overlay: colors identify predicted classes" style="max-width:100%;border-radius:8px">`;
  }
 }
 if(a.analysis_status==='failed')results=`<p>${escapeHtml(a.analysis_error||'Analysis failed. You can retry.')}</p>`;
 const pending=['queued','processing'].includes(a.analysis_status);
 $('#analyzeImage').disabled=!!analyzingId||pending;
 $('#analyzeImage').textContent=pending?(a.analysis_status==='queued'?'Queued for analysis':'Analyzing…'):a.analysis_status==='failed'?'Retry analysis':a.analysis_status==='completed'?'Analyze again':'Analyze and save';
 $('#analysisProgress').textContent=pending?'Analysis runs in the background. Results will be saved automatically.':a.analysis_status==='completed'?'Analysis saved. Awaiting expert review.':'';
 $('#detailResults').innerHTML=results;
 $('#detailReview').innerHTML=a.expert_annotated?`<p>${escapeHtml(a.expert_hazard_type||'Review saved')}${a.expert_comments?`<br>${escapeHtml(a.expert_comments)}`:''}</p>`:'<p>No expert assessment has been saved. Reviewer login and annotation are planned for a later development step.</p>';
 $('#deleteImage').disabled=analyzingId===a.id||a.analysis_status!=='not_analyzed'||!!a.expert_annotated;$('#deleteImage').title=$('#deleteImage').disabled?'Images with analysis or review history cannot be deleted here.':'';
 if(!$('#detailsDialog').open)$('#detailsDialog').showModal();
}
// Retry/explicit analysis uses the same persisted queue as automatic uploads.
$('#analyzeImage').addEventListener('click', async () => {
 const id=selectedId;if(!id||analyzingId)return;
 analyzingId=id;$('#analyzeImage').disabled=true;$('#deleteImage').disabled=true;
 $('#analysisProgress').textContent='Queueing analysis…';
 try {
  const response=await fetch(`/api/assets/${id}/analyze`,{method:'POST'});
  const result=await response.json();
  if(!response.ok)throw new Error(result.detail||'Could not queue analysis.');
  await refresh();
  if(selectedId===id)openDetails(id,returnFocus,true);
 }catch(error){if(selectedId===id)$('#analysisProgress').textContent=error.message;}
 finally{
  analyzingId=null;
  const current=assets.find(a=>a.id===selectedId);
  $('#analyzeImage').disabled=!!current&&['queued','processing'].includes(current.analysis_status);
  $('#deleteImage').disabled=!current||current.analysis_status!=='not_analyzed'||!!current.expert_annotated;
 }
});
$('#detailImage').addEventListener('error',()=>{$('#previewError').hidden=false;$('#detailImage').hidden=true;});
$('#closeDetails').addEventListener('click',()=>$('#detailsDialog').close());
$('#detailsDialog').addEventListener('click',e=>{if(e.target===$('#detailsDialog')){const box=e.target.getBoundingClientRect();if(e.clientX<box.left||e.clientX>box.right||e.clientY<box.top||e.clientY>box.bottom)e.target.close();}});
$('#detailsDialog').addEventListener('close',()=>{selectedId=null;if(returnFocus?.isConnected)returnFocus.focus();});
function toggleZoom(){const zoomed=$('#imageViewport').classList.toggle('zoomed');$('#zoomButton').textContent=zoomed?'Fit image':'Zoom in';$('#zoomButton').setAttribute('aria-pressed',String(zoomed));}
$('#zoomButton').addEventListener('click',toggleZoom);$('#detailImage').addEventListener('click',toggleZoom);$('#detailImage').addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();toggleZoom();}});
$('#deleteImage').addEventListener('click',async()=>{const a=assets.find(a=>a.id===selectedId);if(!a||!confirm(`Delete ${a.name}? This removes its original image and upload record.`))return;$('#deleteImage').disabled=true;try{const response=await fetch(`/api/assets/${a.id}`,{method:'DELETE'});const data=await response.json();if(!response.ok)throw new Error(data.detail||'Could not delete image.');$('#detailsDialog').close();await refresh();}catch(e){$('#detailStatus').textContent=e.message;$('#deleteImage').disabled=false;}});
function addFiles(incoming){
 if(uploading)return;const messages=[];
 for(const f of incoming){if(!['image/jpeg','image/png','image/webp'].includes(f.type)){messages.push(`${f.name}: use JPEG, PNG, or WebP.`);continue;}if(f.size>20*1024*1024){messages.push(`${f.name}: exceeds 20 MB.`);continue;}if(files.some(x=>x.file.name===f.name&&x.file.size===f.size&&x.file.lastModified===f.lastModified))continue;if(files.length>=10){messages.push('Select up to 10 images per upload.');break;}files.push({file:f,url:URL.createObjectURL(f)});}
 $('#uploadStatus').textContent=messages.join('\n');$('#uploadStatus').classList.toggle('error',!!messages.length);renderSelection();
}
function renderSelection(){$('#selectionPanel').hidden=!files.length;$('#selectionCount').textContent=files.length;$('#uploadButton').disabled=!files.length||uploading;$('#clearFiles').disabled=uploading;$('#imageInput').disabled=uploading;$('#selectedFiles').innerHTML=files.map((f,i)=>`<div class="selected-file"><img class="thumb" src="${f.url}" alt=""><div><span class="file-title">${escapeHtml(f.file.name)}</span><span class="file-sub">${byteText(f.file.size)}</span></div><button class="remove-file" data-remove="${i}" aria-label="Remove ${escapeHtml(f.file.name)}" ${uploading?'disabled':''}>×</button></div>`).join('');}
$('#imageInput').addEventListener('change',e=>{addFiles([...e.target.files]);e.target.value='';});
$('#clearFiles').addEventListener('click',()=>{files.forEach(f=>URL.revokeObjectURL(f.url));files=[];renderSelection();$('#uploadStatus').textContent='';});
$('#selectedFiles').addEventListener('click',e=>{const b=e.target.closest('[data-remove]');if(b&&!uploading){const [f]=files.splice(Number(b.dataset.remove),1);URL.revokeObjectURL(f.url);renderSelection();}});
['dragenter','dragover'].forEach(type=>$('#dropZone').addEventListener(type,e=>{e.preventDefault();if(!uploading)$('#dropZone').classList.add('dragging');}));
['dragleave','drop'].forEach(type=>$('#dropZone').addEventListener(type,e=>{e.preventDefault();$('#dropZone').classList.remove('dragging');if(type==='drop')addFiles([...e.dataTransfer.files]);}));
$('#uploadButton').addEventListener('click',()=>{
 if(uploading||!files.length)return;uploading=true;renderSelection();$('#uploadProgress').hidden=false;$('#progressBar').value=0;$('#progressLabel').textContent='Sending images…';$('#uploadStatus').textContent='';$('#uploadStatus').classList.remove('error');
 const data=new FormData();files.forEach(f=>data.append('files',f.file));const xhr=new XMLHttpRequest();xhr.open('POST','/api/upload-images');xhr.timeout=180000;
 xhr.upload.onprogress=e=>{if(e.lengthComputable){$('#progressBar').value=e.loaded/e.total*90;$('#progressLabel').textContent=e.loaded===e.total?'Saving images to private storage…':`Sending images · ${Math.round(e.loaded/e.total*100)}%`;}};
 const finish=()=>{uploading=false;$('#uploadProgress').hidden=true;renderSelection();};
 xhr.onload=async()=>{try{const result=JSON.parse(xhr.responseText);if(xhr.status>=400)throw new Error(result.errors?.map(e=>`${e.name}: ${e.error}`).join('\n')||result.detail||'Upload failed.');const savedNames={};result.saved.forEach(r=>savedNames[r.name]=(savedNames[r.name]||0)+1);files=files.filter(f=>{if(savedNames[f.file.name]){savedNames[f.file.name]--;URL.revokeObjectURL(f.url);return false;}return true;});$('#uploadStatus').innerHTML=`${result.count} ${result.count===1?'image saved':'images saved'}. Analysis starts automatically. Results will appear in Recent inspections. <a class="text-link" href="#overview">View recent inspections →</a>${result.analysis_errors?.length?`<br>${result.analysis_errors.map(e=>escapeHtml(`${e.name}: ${e.error}`)).join('<br>')}`:''}${result.errors?.length?`<br>${result.errors.map(e=>escapeHtml(`${e.name}: ${e.error}`)).join('<br>')}`:''}`;$('#uploadStatus').classList.toggle('error',!!(result.errors?.length||result.analysis_errors?.length));await refresh();}catch(e){$('#uploadStatus').textContent=e.message;$('#uploadStatus').classList.add('error');}finally{finish();}};
 xhr.onerror=()=>{$('#uploadStatus').textContent='Connection interrupted. Check Inspections before retrying; some files may have been saved.';$('#uploadStatus').classList.add('error');finish();};xhr.ontimeout=()=>{$('#uploadStatus').textContent='The upload took too long. Check Inspections before retrying; some files may have been saved.';$('#uploadStatus').classList.add('error');finish();};xhr.send(data);
});
// Poll quickly while work is queued/processing, preserving images, zoom and filters.
let lastPoll=0;
setInterval(()=>{
 if(document.hidden||uploading)return;
 const pending=assets.some(a=>['queued','processing'].includes(a.analysis_status));
 const interval=pending?2000:30000;
 if(Date.now()-lastPoll>=interval){lastPoll=Date.now();refresh();}
},2000);
window.addEventListener('beforeunload',()=>files.forEach(f=>URL.revokeObjectURL(f.url)));
refresh();

// Re-measure SVG labels after viewport changes without fetching records again.
let chartResizeTimer;
window.addEventListener('resize',()=>{clearTimeout(chartResizeTimer);chartResizeTimer=setTimeout(()=>{if(loaded&&pageName()==='overview')renderUploadChart(assets);},100);});
