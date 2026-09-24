/* Local production-build QA server. Instrumentation exists only in these test responses. */
const http = require('node:http')
const fs = require('node:fs')
const path = require('node:path')
const dist = path.resolve(__dirname, '../dist')
const port = 5175
function probe() {
  const mode = new URLSearchParams(location.search).get('landingQA')
  if (!mode) return
  const m = window.landingQA = { requested: 0, fired: 0, pending: 0, times: [], longTasks: [], shifts: [], errors: [] }
  // The page under test is inside an iframe in a runner window that may itself be occluded, and
  // an occluded document stops rendering on demand and throttles rAF - which is correct product
  // behaviour and useless in a harness. Pinned visible on the prototype, so the hidden-signal
  // check below can still shadow it on the document instance and test the real thing.
  for (const [key, value] of [['hidden', false], ['visibilityState', 'visible']]) {
    try { Object.defineProperty(Document.prototype, key, { configurable: true, get: () => value }) } catch {}
  }
  window.addEventListener('error', e => m.errors.push(e.message))
  m.phases=[]
  const phases=new MutationObserver(()=>{const root=document.querySelector('.landing-restored');if(!root)return;const phase=root.dataset.intro;if(m.phases.at(-1)?.phase!==phase){const slot=document.querySelector('.hero-visual'),r=slot?.getBoundingClientRect();m.phases.push({phase,at:performance.now(),ready:!!document.querySelector('[data-laptop-ready]'),x:r?.x,width:r?.width,transform:slot?getComputedStyle(slot).transform:null})}})
  phases.observe(document,{subtree:true,childList:true,attributes:true,attributeFilter:['data-intro']})
  const request = window.requestAnimationFrame.bind(window), cancel = window.cancelAnimationFrame.bind(window)
  const pending = new Map()
  window.requestAnimationFrame = callback => {
    m.requested++
    const fire = (key, time) => {
      const timer = pending.get(key)
      if (timer === undefined) return
      clearTimeout(timer); pending.delete(key); m.pending = pending.size
      m.fired++; m.times.push(time); callback(time)
    }
    const id = request(time => fire(id, time))
    // A timer floor under the frame clock. An occluded harness window is never painted, so the
    // browser stops issuing frames, and every scene on this page draws on demand and would
    // simply stall. Whichever clock arrives first wins, and a frame is only ever delivered once,
    // so a painted run behaves exactly as it did before this existed. It is a floor, not a
    // pump: nothing schedules a frame that the page did not ask for, which is what keeps the
    // idle-frame count below an honest measurement of whether anything is looping.
    pending.set(id, setTimeout(() => fire(id, performance.now()), 32)); m.pending = pending.size
    return id
  }
  window.cancelAnimationFrame = id => {
    const timer = pending.get(id)
    if (timer !== undefined) { clearTimeout(timer); pending.delete(id); m.pending = pending.size }
    cancel(id)
  }
  for (const [type, key] of [['longtask', 'longTasks'], ['layout-shift', 'shifts']]) {
    try { new PerformanceObserver(list => list.getEntries().forEach(e => m[key].push(e.toJSON()))).observe({ type, buffered: true }) } catch {}
  }
  let reduce = mode === 'reduced'
  const nativeMatch = window.matchMedia.bind(window), queries = []
  window.matchMedia = query => {
    if (!query.includes('prefers-reduced-motion')) return nativeMatch(query)
    const listeners = new Set()
    const evaluate = () => nativeMatch(query.replace(/\(prefers-reduced-motion: (reduce|no-preference)\)/g, (_, value) => (value === 'reduce') === reduce ? '(min-width: 0px)' : '(max-width: 0px)')).matches
    const native = nativeMatch(query)
    const entry = { media: query, get matches() { return evaluate() }, addEventListener: (_, fn) => listeners.add(fn), removeEventListener: (_, fn) => listeners.delete(fn) }
    native.addEventListener('change', () => listeners.forEach(fn => fn({ matches: evaluate() })))
    queries.push(() => listeners.forEach(fn => fn({ matches: evaluate() })))
    return entry
  }
  m.reduce = value => { reduce = value; queries.forEach(fn => fn()) }
  const getContext = HTMLCanvasElement.prototype.getContext
  HTMLCanvasElement.prototype.getContext = function(type, ...args) {
    if (mode === 'failure' && type.startsWith('webgl')) return null
    const context = getContext.call(this, type, ...args)
    if (type.startsWith('webgl') && context) m.gl = context
    return context
  }
}
function runner() {
 const button=document.querySelector('button'), output=document.querySelector('pre'), frame=document.querySelector('iframe')
 const wait=ms=>new Promise(r=>setTimeout(r,ms))
 const until=async fn=>{for(let i=0;i<300;i++){if(fn())return;await wait(50)}throw Error('Timed out waiting for page')}
 const results={viewports:[],resilience:{},performance:{}}; let win,doc,run=0
 const tick=async()=>{await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));await wait(50)}
 const go=async y=>{win.scrollTo(0,y);await tick()}
 const pose=()=>doc.querySelector('.landing-instrument')?.dataset.pose
 const canvases=()=>Array.from(doc.querySelectorAll('canvas')).map(el=>({...el.dataset}))
 const load=async(w,h,mode='normal',hash='')=>{
   frame.style.width=w+'px';frame.style.height=h+'px'
   await new Promise(r=>{frame.onload=r;frame.src='/?landingQA='+mode+'&run='+(++run)+hash})
   win=frame.contentWindow;doc=frame.contentDocument
   await until(()=>doc.querySelector('h1'));await doc.fonts.ready
   if(w>=1024&&h>=600&&mode==='normal'&&!hash)await until(()=>doc.querySelector('[data-laptop-ready]'))
   await until(()=>doc.querySelector('.landing-restored')?.dataset.intro==='settled')
   await wait(150)
 }
 const stepY=i=>{let r=doc.querySelector('[data-process-step="'+i+'"]').getBoundingClientRect();return win.scrollY+r.top+r.height/2-win.innerHeight/2}
 const collisions=()=>{
   const visual=doc.querySelector('.landing-instrument'), box=visual?.getBoundingClientRect()
   if(!box||box.bottom<76||box.top>win.innerHeight)return[]
   return Array.from(doc.querySelectorAll('.process-step h3,.process-step p,.results-heading h2,.results-heading p')).filter(n=>{const r=n.getBoundingClientRect();return r.bottom>76&&r.top<win.innerHeight&&Math.min(r.right,box.right)-Math.max(r.left,box.left)>4&&Math.min(r.bottom,box.bottom)-Math.max(r.top,box.top)>4}).map(n=>n.textContent)
 }
 button.onclick=async()=>{button.disabled=true;try{
   for(const [w,h] of [[1920,1080],[1440,900],[1366,768],[1024,768],[900,800],[390,844],[375,812],[1366,580]]){
     output.textContent='Checking '+w+' x '+h;await load(w,h)
     const rec={width:w,height:h,overflow:false,collisions:[],heroActionsFit:doc.querySelector('.hero-actions').getBoundingClientRect().bottom<h,brokenImages:[],errors:[]}
     const bottom=doc.querySelector('#results').getBoundingClientRect().bottom+win.scrollY
     for(let y=0;y<bottom;y+=180){await go(y);rec.overflow ||= doc.documentElement.scrollWidth>w;rec.collisions.push(...collisions())}
     rec.collisions=[...new Set(rec.collisions)];rec.errors=win.landingQA.errors
     rec.brokenImages=Array.from(doc.images).filter(im=>im.complete&&!im.naturalWidth).map(im=>im.src)
     rec.resources=win.performance.getEntriesByType('resource').filter(e=>/laptopScene|processScene|three.module|laptop.glb|pose-/.test(e.name)).map(e=>({name:e.name.split('/').pop(),bytes:e.transferSize,duration:e.duration}))
     rec.intro=win.landingQA.phases; rec.renderers=canvases();results.viewports.push(rec)
   }
   await load(1440,900)
   const heroCanvas=doc.querySelector('.hero-stage canvas'); const initializations=heroCanvas.dataset.initializations; await go(1200); await go(0); results.resilience.heroReturn={sameCanvas:heroCanvas===doc.querySelector('.hero-stage canvas'),initializationsBefore:initializations,initializationsAfter:heroCanvas.dataset.initializations,transform:getComputedStyle(doc.querySelector('.hero-visual')).transform,phase:doc.querySelector('.landing-restored').dataset.intro};
   const initial=win.landingQA.fired;await wait(700);results.performance.idleRaf=win.landingQA.fired-initial
   const laptopExt=heroCanvas.getContext('webgl2').getExtension('WEBGL_lose_context');laptopExt.loseContext();await wait(200)
   results.resilience.laptopContextLoss={fallback:!!doc.querySelector('.laptop-fallback')};laptopExt.restoreContext();await until(()=>doc.querySelector('[data-laptop-ready]'));results.resilience.laptopContextLoss.restored=true
   await go(stepY(3));await until(()=>doc.querySelector('.landing-instrument[data-ready]'));await wait(200)
   results.resilience.reverse=[]
   for(const i of [0,5,2,4,3,0,3]){await go(stepY(i));results.resilience.reverse.push({step:i,pose:pose()})}
   const listen=stepY(3),follow=stepY(4),samples=[]
   for(let y=listen;y<=follow;y+=12){await go(y);samples.push(Number(pose()))}
   results.resilience.adaptation={samples:samples.length,monotonic:samples.every((v,i)=>!i||v>=samples[i-1]),first:samples[0],last:samples.at(-1)}
   await go(stepY(4));await wait(200)
   results.performance.renderers=canvases();results.performance.longTasks=win.landingQA.longTasks;results.performance.cls=win.landingQA.shifts.filter(s=>!s.hadRecentInput).reduce((n,s)=>n+s.value,0)
   const measure=async()=>{const a=canvases();await wait(500);return {before:a,after:canvases(),pending:win.landingQA.pending}}
   results.performance.processIdle=await measure()
   let hidden=false;Object.defineProperty(win.document,'hidden',{configurable:true,get:()=>hidden});hidden=true;doc.dispatchEvent(new win.Event('visibilitychange'));await go(stepY(2));results.resilience.hiddenSignal=await measure();hidden=false;doc.dispatchEvent(new win.Event('visibilitychange'));await tick()
   const canvas=doc.querySelector('.landing-instrument canvas'), gl=canvas.getContext('webgl2'), ext=gl.getExtension('WEBGL_lose_context');ext.loseContext();await wait(200)
   results.resilience.contextLoss={fallback:!doc.querySelector('.landing-instrument[data-ready]')};ext.restoreContext();await until(()=>doc.querySelector('.landing-instrument[data-ready]'));results.resilience.contextLoss.restored=true
   await go(doc.body.scrollHeight);results.performance.offscreen=await measure()
   win.landingQA.reduce(true);await wait(150);results.resilience.liveReduced={canvas:doc.querySelectorAll('canvas').length,scroll:win.scrollY};win.landingQA.reduce(false);await go(stepY(3));await until(()=>doc.querySelector('.landing-instrument[data-ready]'));results.resilience.resumePose=pose()
   results.resilience.remount=[]
   for(let i=0;i<3;i++){await go(0);doc.querySelector('.hero-signin').click();await until(()=>!doc.querySelector('.landing-restored'));await wait(200);const rec={canvas:doc.querySelectorAll('canvas').length,pending:win.landingQA.pending};win.history.back();await until(()=>doc.querySelector('.landing-restored'));rec.returnPhase=doc.querySelector('.landing-restored').dataset.intro;await go(0);await until(()=>doc.querySelector('[data-laptop-ready]'));results.resilience.remount.push(rec)}
   await load(1440,900,'normal','#process-follow');await until(()=>doc.querySelector('.landing-instrument[data-ready]'));results.resilience.hash={pose:pose(),scroll:win.scrollY,resources:win.performance.getEntriesByType('resource').map(e=>e.name).filter(n=>n.includes('laptop'))}
   await load(1440,900,'reduced');results.resilience.initialReduced={canvas:doc.querySelectorAll('canvas').length,sceneLoaded:win.performance.getEntriesByType('resource').some(e=>/laptopScene|processScene|three.module|laptop.glb/.test(e.name))}
   await load(1440,900,'failure');await go(stepY(3));await wait(500);results.resilience.failure={laptopFallback:!!doc.querySelector('.laptop-fallback'),processFallback:!doc.querySelector('.landing-instrument[data-ready]'),headline:doc.querySelector('h1').textContent}
   results.legal=[]
   for(const [w,h] of [[1440,900],[390,844],[375,812]])for(const name of ['privacy','terms','cookies']){
     frame.style.width=w+'px';frame.style.height=h+'px';await new Promise(r=>{frame.onload=r;frame.src='/legal/'+name+'?landingQA=normal&run='+(++run)})
     const d=frame.contentDocument;await until(()=>d.querySelector('.legal-page'));await d.fonts.ready
     results.legal.push({page:name,width:w,height:h,overflow:d.documentElement.scrollWidth>w,dark:d.querySelector('.night-room')!==null,canvas:d.querySelectorAll('canvas').length,wordCount:d.querySelector('main').textContent.split(/\s+/).length,emDashes:d.body.textContent.includes(String.fromCharCode(8212)),navigation:d.querySelectorAll('nav[aria-label="Legal pages"] a').length})
   }
 }catch(e){results.error=e.stack}finally{output.textContent=JSON.stringify(results,null,2);await fetch('/__report',{method:'POST',body:JSON.stringify(results,null,2)});button.disabled=false}}
}
const page = `<!doctype html><html><head><title>Landing production QA</title><style>body{font:15px system-ui;margin:24px}button{padding:12px}iframe{display:block;border:1px solid #aaa;margin-top:20px}pre{white-space:pre-wrap}</style></head><body><h1>Landing production QA</h1><button>Run production checks</button><pre>Ready</pre><iframe title="Production landing under test"></iframe><script>(${runner.toString()})()</script></body></html>`
const server = http.createServer((req,res) => {
  const url = new URL(req.url,'http://127.0.0.1')
  if(url.pathname==='/__qa') {res.setHeader('content-type','text/html');return res.end(page)}
  if(url.pathname==='/__report'&&req.method==='POST') {
    let body='';req.on('data',c=>body+=c);req.on('end',()=>{fs.writeFileSync(path.join(require('node:os').tmpdir(),'intermind-thread-audit','restored-browser-report.json'),body);res.end('saved')});return
  }
  let file=path.resolve(dist,'.'+decodeURIComponent(url.pathname))
  if(!file.startsWith(dist+path.sep)&&file!==dist) {res.statusCode=403;return res.end()}
  if(!fs.existsSync(file)||fs.statSync(file).isDirectory()) file=path.join(dist,'index.html')
  const ext=path.extname(file)
  res.setHeader('content-type',({'.html':'text/html','.js':'application/javascript','.css':'text/css','.png':'image/png','.webp':'image/webp','.svg':'image/svg+xml','.woff2':'font/woff2'})[ext]||'application/octet-stream')
  if(ext==='.html') return res.end(fs.readFileSync(file,'utf8').replace('<head>',`<head><script>(${probe.toString()})()</script>`))
  fs.createReadStream(file).pipe(res)
})
server.listen(port,'127.0.0.1',()=>console.log(`Landing QA: http://127.0.0.1:${port}/__qa`))
