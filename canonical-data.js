/* Single canonical publication boundary for all browser consumers. */
window.GridLockData = (() => {
  let pending;
  const load = () => pending ||= fetch('./data/published/import_receipt.json').then(r=>{if(!r.ok)throw Error('Import receipt unavailable');return r.json();}).then(receipt=>Promise.all(['gridlock_master_projects','website_data'].map(async name => {
    const r=await fetch(`./data/published/${name}.json`);if(!r.ok)throw Error('Canonical publication unavailable');const text=await r.text();const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text));const digest=Array.from(new Uint8Array(bytes),b=>b.toString(16).padStart(2,'0')).join('');if(digest!==receipt.artifacts[name+'.json'])throw Error('Publication integrity mismatch');return JSON.parse(text);
  }))).then(([master,web])=>{
    if(master.dataset_version!=='1.0.0'||master.total_projects!==master.projects.length)throw Error('Unsupported canonical publication');
    for(const k of ['dataset_version','pipeline_commit','generated_at'])if(!master[k]||master[k]!==web[k])throw Error('Mixed publication versions');
    const policy=web.opportunity_policy||{};
    if(policy.distance_km_lt!==40||policy.timeline_gap_years_lte!==2||policy.unknown_timing_eligible!==false)throw Error('Unsupported opportunity policy');
    const byId=new Map();
    for(const p of master.projects){
      if(!p.project_id||byId.has(p.project_id)||!['VERIFIED','ESTIMATED','UNRESOLVED'].includes(p.geometry_status))throw Error('Invalid canonical identity or status');
      const source=p.source_metadata||{};
      byId.set(p.project_id,{...p,...source,id:p.project_id,name:p.project_name,voltage_kv:p.voltage,geometry:p.analysis_geometry,geometry_type:p.analysis_geometry?.type,estimated_geometry:p.geometry_status==='ESTIMATED',has_geometry:!!p.analysis_geometry});
    }
    if(web.projects.length!==byId.size||new Set(web.projects.map(p=>p.id)).size!==byId.size)throw Error('Catalog mismatch');
    for(const p of web.projects){const q=byId.get(p.id);if(!q||p.name!==q.name||p.utility!==q.utility||p.geometry_status!==q.geometry_status||JSON.stringify(p.geometry)!==JSON.stringify(q.geometry)||['planned_start_year','planned_end_year','in_service_year'].some(k=>p[k]!==q[k]))throw Error('Project metadata mismatch');}
    return {master,web,byId,projects:[...byId.values()]};
  }).catch(e=>{pending=null;throw e;});
  async function mode(name){
    if(!['verified','estimated'].includes(name))throw Error('Unsupported mode');
    const {master,web,byId,projects}=await load();const m=web.modes[name==='estimated'?'full':'verified'];
    const allowed=name==='verified'?['VERIFIED']:['VERIFIED','ESTIMATED'];
    const ids=new Set(),pairs=new Set();
    const matches=m.matches.map(m=>{const a=byId.get(m.project_a_id),b=byId.get(m.project_b_id),pair=[m.project_a_id,m.project_b_id].sort().join('|');const points=[m.closest_point_a||m.closest_points?.a,m.closest_point_b||m.closest_points?.b];if(!a||!b||a.id===b.id||a.utility===b.utility||![a,b].every(p=>allowed.includes(p.geometry_status))||ids.has(m.match_id)||pairs.has(pair)||!Number.isFinite(m.distance_km)||m.distance_km<0||m.distance_km>=40||!Number.isInteger(m.timeline_gap_years)||m.timeline_gap_years<0||m.timeline_gap_years>2||points.some(p=>!p||!Number.isFinite(p.lat)||!Number.isFinite(p.lng)||p.lat<30||p.lat>36||p.lng< -86||p.lng> -78))throw Error('Invalid opportunity');ids.add(m.match_id);pairs.add(pair);return {...m,project_a:a,project_b:b};});
    const counts=projects.reduce((result,p)=>{result[p.geometry_status]=(result[p.geometry_status]||0)+1;return result;},{});
    return {dataset:name,data_source:'canonical',dataset_version:master.dataset_version,pipeline_commit:master.pipeline_commit,generated_at:master.generated_at,projects:projects.filter(p=>allowed.includes(p.geometry_status)),matches,summary:m.summary,catalog_total:projects.length,verified_count:counts.VERIFIED||0,estimated_count:counts.ESTIMATED||0,unresolved_count:counts.UNRESOLVED||0};
  }
  return {load,mode};
})();
