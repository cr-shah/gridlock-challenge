/* Single canonical publication boundary for all browser consumers. */
window.GridLockData = (() => {
  let pending;
  const load = () => pending ||= fetch('./data/published/import_receipt.json').then(r=>{if(!r.ok)throw Error('Import receipt unavailable');return r.json();}).then(receipt=>Promise.all(['gridlock_master_projects','website_data'].map(async name => {
    const r=await fetch(`./data/published/${name}.json`);if(!r.ok)throw Error('Canonical publication unavailable');const text=await r.text();const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text));const digest=Array.from(new Uint8Array(bytes),b=>b.toString(16).padStart(2,'0')).join('');if(digest!==receipt.artifacts[name+'.json'])throw Error('Publication integrity mismatch');return JSON.parse(text);
  }))).then(([master,web])=>{
    if(master.dataset_version!=='1.0.0'||master.total_projects!==master.projects.length)throw Error('Unsupported canonical publication');
    for(const k of ['dataset_version','pipeline_commit','generated_at'])if(!master[k]||master[k]!==web[k])throw Error('Mixed publication versions');
    const byId=new Map();
    for(const p of master.projects){
      if(!p.project_id||byId.has(p.project_id)||!['VERIFIED','ESTIMATED','UNRESOLVED'].includes(p.geometry_status))throw Error('Invalid canonical identity or status');
      const source=p.source_metadata||{};
      byId.set(p.project_id,{...p,...source,id:p.project_id,name:p.project_name,voltage_kv:p.voltage,geometry:p.analysis_geometry,geometry_type:p.analysis_geometry?.type,estimated_geometry:p.geometry_status==='ESTIMATED',has_geometry:!!p.analysis_geometry});
    }
    if(web.projects.length!==byId.size||new Set(web.projects.map(p=>p.id)).size!==byId.size)throw Error('Catalog mismatch');
    for(const p of web.projects){const q=byId.get(p.id);if(!q||p.name!==q.name||['planned_start_year','planned_end_year','in_service_year'].some(k=>p[k]!==q[k]))throw Error('Project metadata mismatch');}
    return {master,web,byId,projects:[...byId.values()]};
  }).catch(e=>{pending=null;throw e;});
  async function mode(name){
    if(!['verified','estimated'].includes(name))throw Error('Unsupported mode');
    const {master,web,byId,projects}=await load();const m=web.modes[name==='estimated'?'full':'verified'];
    const allowed=name==='verified'?['VERIFIED']:['VERIFIED','ESTIMATED'];
    const matches=m.matches.map(m=>{const a=byId.get(m.project_a_id),b=byId.get(m.project_b_id);if(!a||!b||![a,b].every(p=>allowed.includes(p.geometry_status)))throw Error('Invalid match reference');return {...m,project_a:a,project_b:b};});
    return {dataset:name,data_source:'canonical',dataset_version:master.dataset_version,pipeline_commit:master.pipeline_commit,generated_at:master.generated_at,projects:projects.filter(p=>allowed.includes(p.geometry_status)),matches,summary:m.summary};
  }
  return {load,mode};
})();
