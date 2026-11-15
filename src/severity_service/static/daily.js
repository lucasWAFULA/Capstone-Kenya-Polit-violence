(()=>{
 'use strict';
 const $=id=>document.getElementById(id), ns='http://www.w3.org/2000/svg';
 const text=(id,value)=>{$(id).textContent=value;};
 const svg=(tag,attrs)=>{const e=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);return e;};
 let available=false, request=0;
 async function loadSeries(){
  if(!available)return;
  const current=++request;
  const county=$('daily-county').value,days=$('daily-window').value;
  text('daily-chart-note','Loading daily records…');
  try{
   const response=await fetch(`/v1/data/daily?county=${encodeURIComponent(county)}&days=${days}`,{cache:'no-store'});
   if(!response.ok)throw new Error('Daily series unavailable');const data=await response.json();if(current!==request)return;
   const rows=data.series;$('daily-chart').replaceChildren();$('daily-table').replaceChildren();
   if(!rows.length){text('daily-chart-note','No daily rows available for this selection.');return;}
   const max=Math.max(1,...rows.map(r=>r.events));
   $('daily-chart').append(svg('line',{x1:40,y1:150,x2:780,y2:150,stroke:'#cddac6'}));
   for(const [field,color] of [['events','#4e7b51'],['high_political_violence_events','#bc7850']]){
    const line=rows.map((row,i)=>`${i?'L':'M'}${40+i*740/Math.max(1,rows.length-1)},${150-row[field]/max*125}`).join(' ');
    $('daily-chart').append(svg('path',{d:line,fill:'none',stroke:color,'stroke-width':2}));
   }
   for(const [i,row] of rows.entries()){
    const point=svg('circle',{cx:40+i*740/Math.max(1,rows.length-1),cy:150-row.events/max*125,r:2.5,fill:'#4e7b51'});
    const title=svg('title',{});title.textContent=`${row.date}: ${row.events} events; ${row.high_political_violence_events} high political violence events`;point.append(title);$('daily-chart').append(point);
   }
   for(const [x,y,label,anchor] of [[40,177,rows[0].date,'start'],[780,177,rows.at(-1).date,'end'],[25,30,String(max),'end'],[25,153,'0','end']]){const e=svg('text',{x,y,fill:'#6b7c65','font-size':11,'text-anchor':anchor});e.textContent=label;$('daily-chart').append(e);}
   const zeros=rows.filter(r=>r.events===0).length;
   text('daily-chart-note',`${county} · ${rows[0].date}–${rows.at(-1).date} · ${zeros} of ${rows.length} days have no recorded events. Historical snapshot; current alerts remain separate.`);
   for(const row of rows.slice(-14).reverse()){const tr=document.createElement('tr');if(!row.events)tr.className='daily-zero-row';for(const key of ['date','events','fatalities','high_political_violence_events']){const td=document.createElement('td');td.textContent=row[key];tr.append(td);}$('daily-table').append(tr);}
  }catch(error){if(current!==request)return;$('daily-chart').replaceChildren();$('daily-table').replaceChildren();text('daily-chart-note',error.message);}
 }
 async function refreshFoundation(){
  try{
   const response=await fetch('/v1/data/summary',{cache:'no-store'});if(!response.ok)throw new Error('Dataset summary unavailable');const summary=await response.json();
   available=summary.available&&summary.series_available;
   if(!summary.available){text('daily-quality','Not built');text('daily-coverage',summary.notice);text('daily-chart-note','Build the complete county-day dataset to view activity.');return;}
   text('daily-quality',Object.values(summary.checks).every(Boolean)?'QUALITY CHECKS PASSED':'Review quality checks');
   text('daily-coverage',`${summary.counties} counties on every day from ${summary.start_date} through ${summary.end_date}. ${summary.matches_latest_extraction===false?'A newer extraction exists: rebuild this panel.':'Historical API snapshot; incident dates are not publication dates.'}`);
   text('daily-rows',summary.rows.toLocaleString());text('daily-calendar',`${summary.calendar_days.toLocaleString()} dates × ${summary.counties} counties`);
   text('daily-zeros',summary.zero_record_county_days.toLocaleString());text('daily-zero-share',`${(summary.zero_record_county_days/summary.rows*100).toFixed(1)}% of all county-days`);
   text('daily-events',summary.source_events.toLocaleString());text('daily-labels',summary.labelled_rows.toLocaleString());text('daily-censored',`${summary.censored_label_rows} ending rows retain unknown outcomes`);
   const restriction=summary.access_restrictions?.date_recency;
   text('daily-restriction',restriction?`Account access: ${restriction.quantity} ${restriction.unit.toLowerCase()} recency restriction. Available history ends ${summary.end_date}; it does not support current alerts.`:'Coverage reflects the available historical snapshot; reporting completeness is not established.');
   const selection=$('daily-county').value;$('daily-county').replaceChildren();for(const county of ['National',...summary.county_names]){const option=document.createElement('option');option.value=county;option.textContent=county;$('daily-county').append(option);}$('daily-county').value=selection;
   $('daily-county').disabled=!available;$('daily-window').disabled=!available;
   if(available)await loadSeries();else text('daily-chart-note','Build metadata is packaged, but daily activity files remain local and are not available in this deployment.');
  }catch(error){text('daily-quality','Unavailable');text('daily-chart-note',error.message);}
 }
 $('daily-county').addEventListener('change',loadSeries);$('daily-window').addEventListener('change',loadSeries);$('refresh').addEventListener('click',refreshFoundation);
 refreshFoundation();setInterval(refreshFoundation,60000);
})();
