'use strict';
const $ = id => document.getElementById(id);
const NS = 'http://www.w3.org/2000/svg';
const pct = value => `${(value * 100).toFixed(1)}%`;
let state, geometry, selected, view = [0, 0, 600, 620];
const colors = ['#dbe9dd', '#afcfac', '#e3ca81', '#da9467', '#b75547'];
function text(id, value) { $(id).textContent = value; }
function svg(tag, attributes) { const e = document.createElementNS(NS, tag); for (const [k,v] of Object.entries(attributes)) e.setAttribute(k,v); return e; }
function setView() { $('map').setAttribute('viewBox', view.join(' ')); }
function drawMap() {
 $('map').replaceChildren();
 const points = [];
 for (const feature of geometry.features) { const polygons = feature.geometry.type === 'Polygon' ? [feature.geometry.coordinates] : feature.geometry.coordinates; for (const polygon of polygons) for (const ring of polygon) points.push(...ring); }
 const xs = points.map(p=>p[0]), ys = points.map(p=>p[1]);
 const minX=Math.min(...xs), maxX=Math.max(...xs), minY=Math.min(...ys), maxY=Math.max(...ys);
 const scale=Math.min(550/(maxX-minX), 570/(maxY-minY));
 const project=p=>[(p[0]-(minX+maxX)/2)*scale+300, ((minY+maxY)/2-p[1])*scale+310];
 const lookup=new Map(state.counties.map(row=>[row.county,row]));
 for (const feature of geometry.features) {
  const county=feature.properties.county, row=lookup.get(county);
  const polygons=feature.geometry.type==='Polygon'?[feature.geometry.coordinates]:feature.geometry.coordinates;
  const d=polygons.flatMap(poly=>poly.map(ring=>ring.map((p,i)=>`${i?'L':'M'}${project(p).join(',')}`).join(' ')+'Z')).join(' ');
  const path=svg('path',{d,fill:row?colors[Math.min(4,Math.floor(row.probability*5))]:'#ddd','fill-rule':'evenodd',tabindex:'0',role:'button','aria-label':`${county}: ${row?pct(row.probability):'unavailable'}`});
  path.dataset.county=county;const title=svg('title',{});title.textContent=`${county} · ${row?pct(row.probability):'unavailable'}`;path.append(title);
  path.addEventListener('click',()=>select(county));path.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select(county);}});$('map').append(path);
 }
}
function drawTable() {
 const query=$('search').value.toLowerCase();$('county-table').replaceChildren();
 for(const row of state.counties.filter(r=>r.county.toLowerCase().includes(query))){
  const tr=document.createElement('tr');tr.classList.toggle('selected',row.county===selected);
  const county=document.createElement('td'), button=document.createElement('button');button.textContent=row.county;button.addEventListener('click',()=>select(row.county));county.append(button);
  const probability=document.createElement('td');probability.textContent=pct(row.probability);
  const flag=document.createElement('td');flag.textContent=row.probability>=state.threshold?'Above threshold':'Below threshold';tr.append(county,probability,flag);$('county-table').append(tr);
 }
 if(!$('county-table').children.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=3;td.textContent='No matching counties';tr.append(td);$('county-table').append(tr);}
}
function select(county){
 selected=county;const row=state.counties.find(r=>r.county===county);if(!row)return;
 text('selected-county',`${county} County`);text('selected-probability',pct(row.probability));text('events',row.events_30d??'—');text('high-events',row.high_30d??'—');
 text('selected-signal',`${row.probability>=state.threshold?'Above':'Below'} research threshold (${pct(state.threshold)})${state.fresh?' · human review only':' · current alerts suppressed'}`);
 for(const path of $('map').querySelectorAll('path'))path.classList.toggle('selected',path.dataset.county===county);
 $('trend').replaceChildren();const trend=row.trend||[];
 if(trend.length>1){const max=Math.max(.1,...trend.map(t=>t.probability));const line=trend.map((p,i)=>`${i?'L':'M'}${10+i*280/(trend.length-1)},${90-p.probability/max*75}`).join(' ');$('trend').append(svg('path',{d:line,fill:'none',stroke:'#4d7951','stroke-width':2}));text('trend-caption',`${trend[0].origin} → ${trend.at(-1).origin} · ${state.mode==='historical_demo'?'held-out historical estimates':'saved research forecasts'}. Scale 0–${pct(max)}.`);}
 else text('trend-caption','Forecast history will appear after multiple weekly runs.');drawTable();
}
function render(){
 $('notice').className=`notice${state.fresh?' fresh':''}`;text('notice',state.notice);
 text('mode',state.mode==='historical_demo'?'HISTORICAL REPLAY':state.fresh?'CURRENT RESEARCH FORECAST':'STALE / UNAVAILABLE');
 text('horizon',state.origin?`${state.origin} → ${state.end_exclusive} (end exclusive)`:'No forecast period');
 text('cutoff',state.history_cutoff_exclusive?`History before ${state.history_cutoff_exclusive}`:'');
 text('count',state.counties.length);const peak=state.counties[0];text('peak',peak?pct(peak.probability):'—');text('peak-county',peak?.county||'No forecast available');
 text('alerts-count',state.fresh?state.alerts.length:'—');text('alerts-note',state.fresh?'Research threshold · not validated':'Suppressed: historical or stale data');
 text('coverage',state.snapshot?.coverage_end||'—');text('collected',state.snapshot?.collected_at?`Retrieved ${new Date(state.snapshot.collected_at).toLocaleString()}`:'Historical export · no live ingestion yet');
 text('alert-status',state.fresh?`${state.alerts.length} counties exceed the research threshold. Prioritise contextual review.`:'No current alerts. The displayed map is historical or stale.');
 $('alert-list').replaceChildren();for(const row of (state.alerts||[])){const li=document.createElement('li'),b=document.createElement('button'),p=document.createElement('strong');b.textContent=row.county;b.addEventListener('click',()=>select(row.county));p.textContent=pct(row.probability);li.append(b,p);$('alert-list').append(li);}
 text('model-name',`County forecasting: ${state.model_name||'unavailable'} · ${state.model_status||'research only'}`);
 const m=state.test_metrics;text('performance',m?`Held-out precision ${pct(m.precision)} · recall ${pct(m.recall)} · false discovery rate ${pct(m.false_discovery_rate)}.`:'Evaluation unavailable.');
 text('threshold-note',`Alert threshold ${pct(state.threshold||0)} was tuned for positive-class F1, not operational costs. Forecast features use a ${state.reporting_delay_days??'—'}-day reporting delay.`);
 if(geometry)drawMap();select(state.counties.some(r=>r.county===selected)?selected:peak?.county);
}
async function refresh(){
 $('refresh').disabled=true;
 try{const response=await fetch('/v1/forecasts',{cache:'no-store'});if(!response.ok)throw new Error('Forecast service unavailable');state=await response.json();render();}
 catch(error){$('notice').className='notice error';text('notice',`${error.message}. Displayed results may be outdated; retry refresh.`);text('alerts-count','—');text('alert-status','Alerts unavailable: refresh failed.');$('alert-list').replaceChildren();}
 finally{$('refresh').disabled=false;}
}
$('refresh').addEventListener('click',refresh);$('search').addEventListener('input',()=>state&&drawTable());$('reset-map').addEventListener('click',()=>{view=[0,0,600,620];setView();});
$('map').addEventListener('wheel',e=>{e.preventDefault();const factor=e.deltaY<0?.85:1.15;const w=Math.max(140,Math.min(600,view[2]*factor)),h=w*620/600;view=[300-w/2,310-h/2,w,h];setView();},{passive:false});
fetch('/static/kenya-counties.geojson').then(r=>{if(!r.ok)throw new Error('Map unavailable');return r.json();}).then(data=>{geometry=data;if(state){drawMap();select(selected);}}).catch(()=>text('notice','County geometry unavailable. Use the county table below.'));
refresh();setInterval(refresh,60000);
