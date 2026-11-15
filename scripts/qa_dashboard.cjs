// Local QA using Chrome's DevTools protocol, without browser package dependencies.
const fs = require('node:fs');
const assert = require('node:assert/strict');
(async()=>{
 const target=await fetch('http://127.0.0.1:9224/json/new?about:blank',{method:'PUT'}).then(r=>r.json());
 const ws=new WebSocket(target.webSocketDebuggerUrl),pending=new Map(),errors=[];let sequence=0;
 await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
 ws.addEventListener('message',event=>{const data=JSON.parse(event.data);if(data.method==='Runtime.exceptionThrown')errors.push(data.params.exceptionDetails.text);if(data.id&&pending.has(data.id)){const [resolve,reject]=pending.get(data.id);pending.delete(data.id);data.error?reject(data.error):resolve(data.result);}});
 const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,[resolve,reject]);ws.send(JSON.stringify({id,method,params}));});
 const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw new Error(result.exceptionDetails.text);return result.result.value;};
 await send('Runtime.enable');await send('Page.enable');
 await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
 await send('Page.navigate',{url:'http://127.0.0.1:8765/'});
 await evaluate(`new Promise((resolve,reject)=>{let attempts=0;const timer=setInterval(()=>{if(document.querySelectorAll('#map path').length===47&&document.querySelector('#count')?.textContent==='47'){clearInterval(timer);resolve(true);}else if(++attempts>100){clearInterval(timer);reject(new Error('Dashboard did not finish loading'));}},100);})`);
 assert.equal(await evaluate("document.querySelector('#mode').textContent"),'HISTORICAL REPLAY');
 assert.equal(await evaluate("document.querySelectorAll('#alert-list li').length"),0);
 await evaluate("document.querySelector('#search').value='Nairobi';document.querySelector('#search').dispatchEvent(new Event('input'));document.querySelector('#county-table button').click()");
 assert.equal(await evaluate("document.querySelector('#selected-county').textContent"),'Nairobi County');
 assert.equal(await evaluate("document.querySelectorAll('#county-table tr').length"),1);
 await evaluate("document.querySelector('#search').value='';document.querySelector('#search').dispatchEvent(new Event('input'));document.querySelector('path[data-county=Garissa]').dispatchEvent(new MouseEvent('click'))");
 assert.equal(await evaluate("document.querySelector('#selected-county').textContent"),'Garissa County');
 assert.equal(await evaluate("document.querySelectorAll('#county-table tr').length"),47);
 let screenshot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});fs.writeFileSync('runtime/dashboard-desktop.png',Buffer.from(screenshot.data,'base64'));
 await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
 assert.equal(await evaluate('document.documentElement.scrollWidth<=window.innerWidth'),true);
 screenshot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});fs.writeFileSync('runtime/dashboard-mobile.png',Buffer.from(screenshot.data,'base64'));
 assert.deepEqual(errors,[]);console.log('Browser QA passed: 47 polygons, search, selection, stale alert suppression, responsive width, no JS exceptions.');
 await send('Browser.close');ws.close();
})().catch(error=>{console.error(error);process.exit(1);});
