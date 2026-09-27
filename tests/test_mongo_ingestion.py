"""Local-only ingestion tests. Every MongoClient is blocked or mocked."""
from collections import Counter
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from bson import BSON
import import_projects
from mongo_store import import_dataset, StoreError
from project_schema import MASTER, ValidationError, build_documents, load_dataset

ROOT = Path(__file__).resolve().parents[1]
STAMP = datetime(2026, 9, 27, tzinfo=timezone.utc)


class IngestionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.publication = load_dataset(ROOT / 'data/published' / MASTER)
        cls.master = json.loads(cls.publication['artifacts'][MASTER])

    def setUp(self):
        self.blocker = patch('pymongo.MongoClient', side_effect=AssertionError('Network forbidden'))
        self.client = self.blocker.start()
        self.addCleanup(self.blocker.stop)

    def mutated(self, mutate, rehash=True):
        publication = deepcopy(self.publication)
        master = json.loads(publication['artifacts'][MASTER])
        mutate(master)
        publication['artifacts'][MASTER] = json.dumps(master).encode()
        if rehash:
            receipt = json.loads(publication['receipt'])
            receipt['artifacts'][MASTER] = sha256(publication['artifacts'][MASTER]).hexdigest()
            publication['receipt'] = json.dumps(receipt).encode()
        return publication

    def test_all_records_lossless_and_bson_compatible(self):
        before = deepcopy(self.publication)
        documents, metadata = build_documents(self.publication, STAMP)
        self.assertEqual(len(documents), 78)
        self.assertEqual(len({p['_id'] for p in documents}), 78)
        for original, document in zip(self.master['projects'], documents):
            self.assertEqual(document['_id'], original['project_id'])
            self.assertEqual({k: v for k, v in document.items() if k not in ('_id', '_ingest')}, original)
            self.assertEqual(BSON(BSON.encode(document)).decode()['source_metadata'], original['source_metadata'])
        BSON.encode(metadata)
        self.assertEqual(self.publication, before)
        self.client.assert_not_called()

    def test_geometry_and_nulls_preserved(self):
        documents, _ = build_documents(self.publication, STAMP)
        self.assertEqual(Counter(p['geometry_status'] for p in documents),
                         {'VERIFIED': 15, 'ESTIMATED': 44, 'UNRESOLVED': 19})
        self.assertEqual(Counter(p['analysis_geometry']['type'] for p in documents if p['analysis_geometry']),
                         {'Point': 38, 'LineString': 21})
        for p in documents:
            if p['geometry_status'] == 'UNRESOLVED':
                self.assertIsNone(p['analysis_geometry'])
                self.assertIsNone(p['verified_geometry'])
                self.assertIsNone(p['estimated_geometry'])
            else:
                self.assertEqual(p['analysis_geometry'], p['verified_geometry'] or p['estimated_geometry'])

    def test_publication_metadata_and_determinism(self):
        first = build_documents(self.publication, STAMP)
        self.assertEqual(first, build_documents(self.publication, STAMP))
        later = build_documents(self.publication, STAMP + timedelta(seconds=1))
        for a, b in zip(first[0], later[0]):
            b['_ingest']['imported_at'] = STAMP
            self.assertEqual(a, b)
        later[1]['imported_at'] = STAMP
        self.assertEqual(first, later)
        metadata = first[1]
        digest = sha256(self.publication['artifacts'][MASTER]).hexdigest()
        self.assertEqual(metadata['_id'], 'sha256:' + digest)
        self.assertEqual(metadata['master_sha256'], digest)
        self.assertEqual(metadata['project_ids'], [p['project_id'] for p in self.master['projects']])
        self.assertEqual(metadata['project_count'], 78)
        self.assertEqual(metadata['publication_receipt'], json.loads(self.publication['receipt']))
        for key in ('dataset_version', 'pipeline_commit', 'generated_at'):
            self.assertEqual(metadata[key], self.master[key])

    def test_invalid_inputs_fail_before_client(self):
        cases = [
            self.mutated(lambda m: m['projects'].pop()),
            self.mutated(lambda m: m['projects'][1].update(project_id=m['projects'][0]['project_id'])),
            self.mutated(lambda m: m['projects'][0].pop('project_name')),
            self.mutated(lambda m: m['projects'][0].update(analysis_geometry=None)),
            self.mutated(lambda m: m['projects'][0].update(planned_start_year=3000)),
            self.mutated(lambda m: m['projects'][0].update(_ingest={})),
            self.mutated(lambda m: m.pop('pipeline_commit')),
            self.mutated(lambda m: m['projects'].__setitem__(0, [])),
            self.mutated(lambda m: m['projects'][0].update(extra=2**80)),
            self.mutated(lambda m: m['projects'][0].update(extra=float('nan'))),
            self.mutated(lambda m: m['projects'][0].update(extra='\ud800')),
            self.mutated(lambda m: m.update(total_projects=77)),
            self.mutated(lambda m: m.update(total_projects=77), rehash=False),
        ]
        for publication in cases:
            with self.subTest(case=cases.index(publication)):
                with self.assertRaises(ValidationError):
                    import_dataset(publication, STAMP)
        self.client.assert_not_called()

    def test_receipt_and_artifact_failures(self):
        cases = []
        for key in ('artifacts', 'pipeline_commit', 'imported_at'):
            p = deepcopy(self.publication)
            receipt = json.loads(p['receipt']); receipt.pop(key)
            p['receipt'] = json.dumps(receipt).encode(); cases.append(p)
        p = deepcopy(self.publication); p['artifacts'].pop('website_data.json'); cases.append(p)
        p = deepcopy(self.publication); p['receipt'] = b'{"artifacts":{},"artifacts":{}}'; cases.append(p)
        for p in cases:
            with self.assertRaises(ValidationError):
                import_dataset(p, STAMP)
        self.client.assert_not_called()

    def test_dry_run_without_credentials_or_connection(self):
        with patch.dict('os.environ', {}, clear=True), redirect_stdout(StringIO()) as output:
            self.assertEqual(import_projects.main(['--dry-run']), 0)
        self.assertIn('78 projects and 1 dataset metadata', output.getvalue())
        self.assertIn('BSON validation: PASS', output.getvalue())
        self.client.assert_not_called()

    def test_legacy_input_rejected(self):
        with self.assertRaises(ValidationError):
            load_dataset(ROOT / 'data/projects.json')

    def test_transaction_repeat_upsert_and_rollback(self):
        # An in-memory transactional fake exercises the callback, without a server.
        saved = {'projects': {'legacy-id': {'_id': 'legacy-id'}}, 'datasets': {}}
        client = MagicMock(); database = MagicMock(); session = MagicMock()
        client.__enter__.return_value = client
        client.__getitem__.return_value = database
        client.start_session.return_value.__enter__.return_value = session
        def bulk(operations, **kwargs):
            self.assertIs(kwargs['session'], session)
            for op in operations:
                self.assertTrue(op._upsert)
                self.assertEqual(op._filter, {'_id': op._doc['project_id']})
                saved['projects'][op._doc['_id']] = deepcopy(op._doc)
        def metadata(query, doc, **kwargs):
            self.assertTrue(kwargs['upsert'])
            self.assertIs(kwargs['session'], session)
            saved['datasets'][query['_id']] = deepcopy(doc)
        def transaction(callback, **kwargs):
            self.assertEqual(kwargs['read_concern'].level, 'snapshot')
            self.assertEqual(kwargs['write_concern'].document, {'w': 'majority'})
            before = deepcopy(saved)
            try: callback(session)
            except Exception:
                saved.clear(); saved.update(before); raise
        database.projects.bulk_write.side_effect = bulk
        database.datasets.replace_one.side_effect = metadata
        session.with_transaction.side_effect = transaction
        with patch('pymongo.MongoClient', return_value=client), patch.dict('os.environ', {'MONGODB_URI': 'mock-only', 'MONGODB_DB': 'gridlock'}):
            import_dataset(self.publication, STAMP)
            first = deepcopy(saved)
            import_dataset(self.publication, STAMP)
            self.assertEqual(saved, first)
            self.assertEqual(len(saved['projects']), 79)
            self.assertEqual(len(saved['datasets']), 1)
            self.assertEqual(saved['projects']['legacy-id'], {'_id': 'legacy-id'})
            database.datasets.replace_one.side_effect = RuntimeError('simulated failure')
            with self.assertRaises(StoreError):
                import_dataset(self.publication, STAMP + timedelta(seconds=1))
            self.assertEqual(saved, first)
        for collection in (database.projects, database.datasets):
            collection.delete_many.assert_not_called()
            collection.delete_one.assert_not_called()
            collection.drop.assert_not_called()


if __name__ == '__main__':
    unittest.main()
