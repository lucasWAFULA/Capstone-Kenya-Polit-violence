(()=>{
 'use strict';
 const $=id=>document.getElementById(id);
 const panel=document.createElement('section');panel.className='reporting-health';panel.setAttribute('aria-label','Reporting connection and freshness');
 for(const[id,label]of [['reporting-access','DATA ACCESS'],['reporting-checked','LAST ACCESS CHECK'],['reporting-recent','ACCESSIBLE RECENT RECORDS'],['reporting-synced','LAST REPORTING SYNC']]){const item=document.createElement('div'),title=document.createElement('small'),value=document.createElement('strong');title.textContent=label;value.id=id;value.textContent='Checking…';item.append(title,value);panel.append(item);}
 const note=document.createElement('p');note.id='reporting-notice';note.className='footnote';panel.append(note);$('notice').after(panel);
 const date=value=>value?new Date(value).toLocaleString():'Not yet run';
 async function refresh(){try{const response=await fetch('/v1/reporting/status',{cache:'no-store'});if(!response.ok)throw Error();const status=await response.json();
  $('reporting-access').textContent=status.check_stale?'Recheck needed':status.status==='access_delayed'?'Connected · access delayed':status.ready_for_recent_reporting?'Recent records accessible':status.api_connected?'Connected · recency unconfirmed':'Not verified';
  $('reporting-checked').textContent=date(status.checked_at);$('reporting-recent').textContent=status.recent_records_available==null?'Unknown':`${status.recent_records_available} in last 14 days`;
  $('reporting-synced').textContent=date(status.last_successful_sync_at);note.textContent=status.notice;
  const limit=status.access_restrictions?.date_recency;if(limit)note.textContent+=` Account delay: ${limit.quantity} ${limit.unit.toLowerCase()}; access cutoff ${limit.date}.`;
  note.append(document.createTextNode(' ACLED event releases are weekly; successful API login does not imply current incident coverage. '));const link=document.createElement('a');link.href='https://acleddata.com/myacled-faqs';link.textContent='ACLED access options ↗';note.append(link);
 }catch{note.textContent='Reporting access status unavailable. No live-reporting claim can be verified.';}}
 $('refresh').addEventListener('click',refresh);refresh();setInterval(refresh,60000);
})();
