'use strict';
// TxDOT FY2024 flexible-pavement cracking categories. Never infer orientation
// from the model's broader "Linear crack" label or from an image filename.
const crackingCategories = [
 {label:'Block Cracking', color:'#008d94'},
 {label:'Alligator Cracking', color:'#8bb395'},
 {label:'Longitudinal Cracking', color:'#edae3b'},
 {label:'Transverse Cracking', color:'#5279aa'}
];
function txdotCrack(label) {
 const clean = String(label || '').trim().toLowerCase().replace(/\s*-\s*(low|medium|high)$/, '');
 return {'block crack':0,'block cracking':0,'alligator crack':1,'alligator cracking':1,
         'longitudinal crack':2,'longitudinal cracking':2,'transverse crack':3,'transverse cracking':3}[clean];
}
function crackingSummary(records, source) {
 const counts = [0,0,0,0];
 let unassessed=0, unmapped=0, other=0, matchedImages=0;
 for (const a of records) {
  let labels;
  if (source==='demo') labels=a.legacy_demo?[a.legacy_demo.predicted_hazard_type]:null;
  else if (source==='expert') labels=a.expert_annotated?[a.expert_hazard_type].filter(Boolean):null;
  else if (a.analysis_status!=='completed') labels=null;
  else if (a.model_result) labels=(a.model_result.classes || []).filter(c=>c.class_id!==0).map(c=>c.label);
  else labels=a.predicted_hazard_type && a.predicted_hazard_type!=='No distress predicted'?[a.predicted_hazard_type]:[];
  if (labels===null) {unassessed++;continue;}
  // Count each recognized type once per image, not once per pixel/object.
  const types=new Set();let hasUnmapped=false,hasOther=false;
  for (const label of labels) {
   const index=txdotCrack(label);
   if (index!==undefined) types.add(index);
   else if (/crack/i.test(label)) hasUnmapped=true;
   else hasOther=true;
  }
  if(types.size)matchedImages++;
  types.forEach(index=>counts[index]++);
  if(hasUnmapped)unmapped++;
  if(hasOther)other++;
 }
 return {counts,unassessed,unmapped,other,matchedImages,total:counts.reduce((a,b)=>a+b,0)};
}
function renderCrackingChart(records) {
 const mode=document.querySelector('#crackMode').value;
 const select=document.querySelector('#crackPeriod');
 const previous=select.value;
 const periods=groupUploadPeriods([],mode).reverse();
 select.replaceChildren(...periods.map(p=>new Option(p.label,String(p.key))));
 if(periods.some(p=>String(p.key)===previous))select.value=previous;
 const key=Number(select.value);
 const perYear=mode==='year'?1:mode==='quarter'?4:12;
 const selected=records.filter(a=>{const d=uploadCalendarDate(a.upload_date);return d && d.year*perYear+Math.floor((d.month-1)/(12/perYear))===key;});
 const source=document.querySelector('#crackSource').value;
 const summary=crackingSummary(selected,source);
 const {counts,total}=summary;
 let offset=0;
 const arcs=counts.map((count,index)=>{
  const length=total?count/total*100:0;
  const arc=length?`<circle class="donut-segment" cx="120" cy="120" r="88" pathLength="100" fill="none" stroke="${crackingCategories[index].color}" stroke-width="36" stroke-dasharray="${length} ${100-length}" stroke-dashoffset="${-offset}" transform="rotate(-90 120 120)"><title>${crackingCategories[index].label}: ${count} (${length.toFixed(1)}%)</title></circle>`:'';
  offset+=length;return arc;
 }).join('');
 document.querySelector('#crackDonut').innerHTML=`<svg viewBox="0 0 240 240" role="img" aria-labelledby="crackSvgTitle crackSvgDescription"><title id="crackSvgTitle">Cracking distribution</title><desc id="crackSvgDescription">${crackingCategories.map((c,i)=>`${c.label}: ${counts[i]}`).join('; ')}. ${total?'Percentages are shares of crack labels.':'No mapped cracking labels available.'}</desc><circle cx="120" cy="120" r="88" fill="none" stroke="#edf1f2" stroke-width="36"/>${arcs}<text class="donut-total" x="120" y="119" text-anchor="middle">${total}</text><text class="donut-caption" x="120" y="140" text-anchor="middle">Crack labels</text></svg>`;
 document.querySelector('#crackLegend').innerHTML=crackingCategories.map((c,i)=>`<li><span class="legend-dot" style="background:${c.color}"></span><div><strong>${c.label}</strong><span>${counts[i]} · ${total?(counts[i]/total*100).toFixed(1):'0'}%</span></div></li>`).join('');
 document.querySelector('#crackEmpty').hidden=total>0;
 document.querySelector('#crackEmpty').textContent=source==='demo'?'No demo cracking labels in this period.':source==='expert'?'No mapped expert cracking labels in this period.':'No saved predictions for these cracking categories. Unsaved previews are not counted.';
 document.querySelector('#crackSourceNote').textContent=source==='demo'?'Historical demo labels · not model predictions':source==='expert'?'Saved expert assessments':'Saved model predictions';
 document.querySelector('#crackCounts').textContent=`${summary.matchedImages} images with mapped cracks · ${summary.unassessed} without a ${source==='demo'?'demo label':source==='expert'?'review':'saved analysis'} · ${summary.unmapped} with unmapped crack labels · ${summary.other} with other distress`;
 document.querySelector('#crackMappingNote').textContent=summary.unmapped?'“Linear crack” stays unmapped: this model does not distinguish longitudinal from transverse.':'Each cracking type is counted once per image. An image can contribute to more than one type.';
}
