"""Read-only canonical project and saved-match repository."""
import hashlib
import json
from master_dataset import load_master, to_scoring_project
from publication_validation import validate_publication

def load_publication(root):
    folder=root/'data/published'
    receipt=json.loads((folder/'import_receipt.json').read_text())
    for filename,digest in receipt['artifacts'].items():
        if hashlib.sha256((folder/filename).read_bytes()).hexdigest()!=digest:
            raise ValueError('Canonical artifact integrity mismatch: '+filename)
    master=load_master(folder/'gridlock_master_projects.json')
    web=json.loads((folder/'website_data.json').read_text())
    validate_publication(master,web)
    if master['dataset_version']!='1.0.0': raise ValueError('Unsupported dataset version')
    for key in ('dataset_version','pipeline_commit','generated_at'):
        if not master.get(key) or web.get(key)!=master[key]: raise ValueError('Mixed publication metadata')
    projects={p['project_id']:{**to_scoring_project(p),'project_id':p['project_id'],'source_metadata':p['source_metadata']} for p in master['projects']}
    if len(web['projects'])!=len(projects) or len({p['id'] for p in web['projects']})!=len(projects): raise ValueError('Catalog mismatch')
    for p in web['projects']:
        q=projects.get(p['id'])
        if not q or any(p.get(k)!=q.get(k) for k in ('name','planned_start_year','planned_end_year','in_service_year','geometry_status','geometry')): raise ValueError('Published metadata mismatch')
    modes={}
    for name,source in [('verified','verified'),('estimated','full')]:
        allowed={'VERIFIED'} if name=='verified' else {'VERIFIED','ESTIMATED'}
        matches=[]
        for match in web['modes'][source]['matches']:
            a=projects.get(match['project_a_id']);b=projects.get(match['project_b_id'])
            if not a or not b or a['geometry_status'] not in allowed or b['geometry_status'] not in allowed: raise ValueError('Invalid match reference')
            matches.append({**match,'project_a':a,'project_b':b})
        modes[name]={'projects':list(projects.values()),'matches':matches}
    return master,modes
