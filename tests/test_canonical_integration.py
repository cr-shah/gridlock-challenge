import copy
import json
import unittest
from collections import Counter
from pathlib import Path
from canonical_repository import load_publication
ROOT=Path(__file__).resolve().parents[1]
class CanonicalTests(unittest.TestCase):
 def test_snapshot_and_geometry_precedence(self):
  master,modes=load_publication(ROOT)
  self.assertEqual(len(master['projects']),78)
  self.assertEqual(Counter(p['utility'] for p in master['projects']),{'DESC':54,'GPC':24})
  self.assertEqual(Counter(p['geometry_status'] for p in master['projects']),{'VERIFIED':15,'ESTIMATED':44,'UNRESOLVED':19})
  for p in master['projects']:
   self.assertEqual(p['analysis_geometry'],p['verified_geometry'] or p['estimated_geometry'])
  self.assertEqual(sum(p['analysis_geometry'] is not None for p in master['projects']),59)
  self.assertEqual(len(modes['verified']['matches']),6)
  self.assertEqual(len(modes['estimated']['matches']),38)
 def test_matches_and_catalog_are_consistent(self):
  master,modes=load_publication(ROOT)
  original=copy.deepcopy(master)
  lookup={p['project_id']:p for p in master['projects']}
  for mode in modes.values():
   self.assertEqual(len(mode['projects']),78)
   for p in mode['projects']:
    q=lookup[p['id']]
    self.assertEqual(p['name'],q['project_name'])
    for k in ('planned_start_year','planned_end_year','in_service_year'):self.assertEqual(p[k],q[k])
   for m in mode['matches']:
    for side in ('a','b'):self.assertEqual(m['project_'+side]['id'],m['project_'+side+'_id'])
  self.assertEqual(master,original)
 def test_default_and_no_legacy_loaders(self):
  self.assertIn("loadDataset('estimated');",(ROOT/'radar.js').read_text())
  for name in ('canonical-data.js','analyst/core.py','project-explorer.js'):
   text=(ROOT/name).read_text()
   for path in ('data/projects.json','data/analysis.json','data/demo_analysis.json','data/verified_projects.json','data/estimated_analysis.json'):
    self.assertNotIn(path,text)
