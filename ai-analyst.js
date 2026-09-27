/* Read-only interpretation UI. No credentials, scoring, or geometry writes. */
(() => {
  function cleanText(value) {
    let text=String(value ?? '');
    for(let i=0;i<3;i++) {
      const doc=new DOMParser().parseFromString(text,'text/html');
      doc.querySelectorAll('script,style').forEach(n=>n.remove());
      doc.querySelectorAll('br').forEach(n=>n.replaceWith('\n'));
      text=doc.body.textContent || '';
    }
    return text;
  }
  function renderMarkdown(container,text) {
    function inline(node,value) {
      value.split(/(\*\*[^*]+\*\*)/g).forEach(part=>{
        if(part.startsWith('**')&&part.endsWith('**')) node.append(make('strong','',part.slice(2,-2)));
        else node.append(document.createTextNode(part));
      });
    }
    const lines=cleanText(text).split('\n'); let paragraph=[],list=null;
    function flush(){if(paragraph.length){const p=make('p');inline(p,paragraph.join(' '));container.append(p);paragraph=[];}}
    lines.forEach(line=>{
      if(!line.trim()){flush();list=null;return;}
      const heading=line.match(/^#{1,3}\s+(.+)/), item=line.match(/^(?:[-*•]|\d+\.)\s+(.+)/);
      if(heading){flush();list=null;const h=make('h4');inline(h,heading[1]);container.append(h);}
      else if(item){flush();if(!list){list=make('ul');container.append(list);}const li=make('li');inline(li,item[1]);list.append(li);}
      else {list=null;paragraph.push(line);}
    });flush();
  }
  const make=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=cleanText(text);return n;};
  let context={mode:'estimated',selection:null}, pending=false, history=[];
  const launch=make('button','ai-launch','✨ Ask GridLock'); launch.type='button';launch.setAttribute('aria-expanded','false');
  const panel=make('section','ai-panel');panel.id='aiPanel';panel.hidden=true;panel.setAttribute('role','dialog');panel.setAttribute('aria-label','GridLock AI Assistant');launch.setAttribute('aria-controls',panel.id);
  const header=make('header','ai-header');header.append(make('strong','','GridLock AI Assistant'));
  const close=make('button','','×');close.type='button';close.setAttribute('aria-label','Close AI Assistant');header.append(close);
  const status=make('p','ai-status','Checking AI availability…');status.setAttribute('role','status');
  const contextLabel=make('p','ai-context','Verified · no selection');
  const log=make('div','ai-messages');log.setAttribute('role','log');log.setAttribute('aria-live','polite');log.setAttribute('aria-label','Conversation');
  const form=make('form','ai-form'),input=make('textarea');input.rows=1;input.maxLength=2000;input.placeholder='Ask a question';input.setAttribute('aria-label','Ask a question');
  const sendButton=make('button','ai-send','↑');sendButton.type='submit';sendButton.setAttribute('aria-label','Send question');form.append(input,sendButton);
  panel.append(header,status,contextLabel,log,form);document.body.append(launch,panel);
  function setOpen(open){panel.hidden=!open;launch.setAttribute('aria-expanded',String(open));if(open)input.focus();else launch.focus();}
  launch.addEventListener('click',()=>setOpen(panel.hidden));close.addEventListener('click',()=>setOpen(false));
  panel.addEventListener('keydown',event=>{if(event.key==='Escape')setOpen(false);});
  function refreshContext(){
    contextLabel.textContent=`${context.mode.toUpperCase()} · ${context.selection ? `${context.selection.kind} ${context.selection.id}` : 'no selection'}`;

  }
  window.addEventListener('gridlock:context',event=>{context=event.detail;refreshContext();});
  function addMessage(text,role){const n=make('div',`ai-message ${role}`);renderMarkdown(n,text);log.append(n);log.scrollTop=log.scrollHeight;return n;}
  function citationNode(c,mode){
    const section=make('div','ai-citation');section.append(make('strong','',c.title));
    if(c.publication)section.append(make('p','',`Dataset ${c.publication.dataset_version} · pipeline ${c.publication.pipeline_commit.slice(0,8)}`));
    if(c.kind==='opportunity' && typeof window.gridlockFocusOpportunity==='function'){
      const b=make('button','','Show opportunity');b.type='button';b.addEventListener('click',()=>window.gridlockFocusOpportunity(c.key,mode));section.append(b);
    } else if(c.kind==='project') {
      const a=make('a','','Open project');a.href='./project-explorer.html?project='+encodeURIComponent(c.key);section.append(a);
    }
    c.sources.forEach(source=>{if(!/^https?:\/\//.test(source.url))return;const a=make('a','',source.label+(source.page ? ` · p. ${source.page}`:''));a.href=source.url;a.target='_blank';a.rel='noopener noreferrer';section.append(a);});return section;
  }
  function briefText(b){return [`${b.title} — ${b.opportunity}`,`Dataset: ${b.mode}`,`Utilities: ${b.utilities.join(' / ')}`,`Projects: ${b.projects.join(' ↔ ')}`,`Distance: ${b.distance_km} km`,`Tier: ${b.tier}`,`Geometry confidence: ${b.geometry_confidence.join(' / ')}`,b.recommendation,...b.evidence.map(e=>`${e.label}${e.page ? ' p. '+e.page:''}: ${e.url}`),'Based on existing GIS analysis and project evidence.'].join('\n\n');}
  function printBrief(b){
    let sheet=document.getElementById('aiPrintBrief');if(sheet)sheet.remove();sheet=make('article');sheet.id='aiPrintBrief';sheet.append(make('h1','',b.title),make('pre','',briefText(b)));document.body.append(sheet);window.print();
  }
  async function send(question,executive=false){
    if(pending || !question.trim())return;
    if(executive && context.selection?.kind!=='opportunity'){addMessage('Select an opportunity in Coordination Radar, then generate its executive brief.','assistant');return;}
    pending=true;sendButton.disabled=true;refreshContext();
    const snapshot=JSON.parse(JSON.stringify(context));
    addMessage(question,'user');input.value='';status.textContent='';
    const thinking=addMessage('GridLock AI is thinking…','thinking');thinking.setAttribute('role','status');log.setAttribute('aria-busy','true');
    try {
      const response=await fetch('/api/analyst',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question,...snapshot,history:history.slice(-4),brief:executive})});
      let result;try{result=await response.json();}catch{throw new Error('Start the AI backend with python3 -m analyst.server, then open port 8002.');}
      if(!response.ok)throw new Error(result.error || 'AI request failed.');
      const card=addMessage(result.text,'assistant');card.prepend(make('span','ai-response-mode',`AI-assisted interpretation · ${snapshot.mode.toUpperCase()}`));
      if(result.recommendation)card.append(make('p','',result.recommendation));

      if(result.citations.length){const evidence=make('details','ai-evidence');evidence.append(make('summary','','View sources'));result.citations.forEach(c=>evidence.append(citationNode(c,snapshot.mode)));card.append(evidence);}
      if(result.brief){const b=result.brief;const briefing=make('div','ai-brief-card');briefing.append(make('h3','',b.title),make('p','',`${b.distance_km} km · ${b.tier}`),make('p','',`${b.utilities.join(' ↔ ')} · ${b.mode.toUpperCase()}`),make('p','',`Geometry confidence: ${b.geometry_confidence.join(' / ')}`),make('p','',b.recommendation));
        const copy=make('button','','Copy briefing');copy.type='button';copy.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(briefText(b));copy.textContent='Copied';}catch{copy.textContent='Copy unavailable';}});
        const pdf=make('button','','Save as PDF');pdf.type='button';pdf.addEventListener('click',()=>printBrief(b));briefing.append(copy,pdf);card.append(briefing);
      }
      card.append(make('p','ai-disclaimer',result.disclaimer));
      history.push(question);status.textContent='';log.scrollTop=log.scrollHeight;
    }catch(error){addMessage(error.message,'error');status.textContent='No AI result generated. Check setup or retry.';}
    finally{thinking.remove();log.setAttribute('aria-busy','false');pending=false;sendButton.disabled=false;refreshContext();input.focus();}
  }
  form.addEventListener('submit',event=>{event.preventDefault();send(input.value);});
  input.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();send(input.value);}});
  fetch('/api/analyst/status').then(r=>{if(!r.ok)throw Error();return r.json();}).then(s=>{status.textContent=s.ready?'':'Setup required · configure .env using AI_ANALYST.md';}).catch(()=>{status.textContent='AI backend offline · run python3 -m analyst.server and open port 8002';});
  if(window.gridlockAnalystContext)context=window.gridlockAnalystContext;
  addMessage("Hi! How can I help with your projects?",'assistant');
  refreshContext();
})();
